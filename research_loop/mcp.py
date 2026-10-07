"""极简 MCP (Model Context Protocol) stdio 客户端：initialize / tools/list / tools/call。

direct 模式下，配置里的 MCP 服务器工具会被自动注入给模型；
shell 模式（外部 agent）不使用这部分。
"""
from __future__ import annotations

import itertools
import json
import os
import re
import subprocess
import threading
from concurrent.futures import Future
from typing import Any, Dict, List, Optional, Tuple

from .config import MCPServerConfig
from .ui import ui


class MCPError(RuntimeError):
    pass


class MCPToolError(RuntimeError):
    pass


def _safe_tool_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]", "_", name).strip("_") or "tool"
    return s[:64]


class MCPClient:
    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, cfg: MCPServerConfig):
        self.cfg = cfg
        self.name = cfg.name
        env = dict(os.environ)
        env.update(cfg.env)
        self.proc = subprocess.Popen(
            [cfg.command, *cfg.args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            env=env, cwd=cfg.cwd,
        )
        self._ids = itertools.count(1)
        self._pending: Dict[int, Future] = {}
        self._wlock = threading.Lock()
        self._clock = threading.Lock()  # 同一服务器的调用串行化
        threading.Thread(target=self._read_loop, daemon=True, name=f"mcp-{cfg.name}").start()
        threading.Thread(target=self._drain_stderr, daemon=True, name=f"mcp-{cfg.name}-err").start()

    # ---- 底层收发 ----
    def _send(self, obj: Dict) -> None:
        data = json.dumps(obj, ensure_ascii=False)
        with self._wlock:
            self.proc.stdin.write(data + "\n")
            self.proc.stdin.flush()

    def _read_loop(self) -> None:
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "id" in msg and ("result" in msg or "error" in msg):
                    fut = self._pending.pop(msg["id"], None)
                    if fut is not None:
                        if "error" in msg:
                            fut.set_exception(MCPError(f"{self.name}: {msg['error']}"))
                        else:
                            fut.set_result(msg["result"])
                elif "method" in msg and "id" in msg:
                    self._answer_server_request(msg)
                # 其余为通知，忽略
        except Exception:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(MCPError(f"{self.name}: 连接断开"))
            self._pending.clear()

    def _answer_server_request(self, msg: Dict) -> None:
        if msg.get("method") == "ping":
            self._send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
            return
        self._send({
            "jsonrpc": "2.0", "id": msg["id"],
            "error": {"code": -32601, "message": f"research-loop 不支持该服务端请求: {msg.get('method')}"},
        })

    def _drain_stderr(self) -> None:
        debug = bool(os.environ.get("RESEARCH_LOOP_DEBUG"))
        try:
            for line in self.proc.stderr:
                if debug and line.strip():
                    ui.dim(f"[mcp:{self.name}] {line.rstrip()}")
        except Exception:
            pass

    # ---- 协议 ----
    def request(self, method: str, params: Optional[Dict] = None, timeout: float = 30.0):
        rid = next(self._ids)
        fut: Future = Future()
        self._pending[rid] = fut
        try:
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        except Exception as e:
            self._pending.pop(rid, None)
            raise MCPError(f"{self.name}: 发送失败（{e}）") from e
        try:
            return fut.result(timeout=timeout)
        except MCPError:
            raise
        except Exception as e:
            raise MCPError(f"{self.name}: 请求 {method} 超时或失败（{e}）") from e

    def notify(self, method: str, params: Optional[Dict] = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def start(self) -> None:
        result = self.request(
            "initialize",
            {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "research-loop", "version": "0.1.0"},
            },
            timeout=30,
        )
        self.notify("notifications/initialized")
        server = (result or {}).get("serverInfo", {}).get("name", "?")
        ui.ok(f"MCP 服务器已连接: {self.name}（{server}）")

    def list_tools(self) -> List[Dict]:
        tools: List[Dict] = []
        cursor: Optional[str] = None
        while True:
            params: Dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor
            result = self.request("tools/list", params, timeout=60)
            tools.extend((result or {}).get("tools") or [])
            cursor = (result or {}).get("nextCursor")
            if not cursor:
                return tools

    def call(self, tool_name: str, arguments: Dict, timeout: Optional[float] = None) -> str:
        with self._clock:
            result = self.request(
                "tools/call",
                {"name": tool_name, "arguments": arguments or {}},
                timeout=timeout or self.cfg.call_timeout,
            )
        texts = [c.get("text", "") for c in (result or {}).get("content", []) if c.get("type") == "text"]
        text = "\n".join(t for t in texts if t).strip()
        if (result or {}).get("isError"):
            raise MCPToolError(text or f"MCP 工具 {tool_name} 返回错误")
        return text or "(无输出)"

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


class MCPManager:
    def __init__(self) -> None:
        self.clients: Dict[str, MCPClient] = {}
        self._by_tool: Dict[str, Tuple[MCPClient, str]] = {}

    def start_all(self, configs: List[MCPServerConfig]) -> None:
        for cfg in configs:
            try:
                client = MCPClient(cfg)
                client.start()
                self.clients[cfg.name] = client
            except Exception as e:
                ui.warn(f"MCP 服务器 {cfg.name} 启动失败，已跳过: {e}")

    def collect_tools(self) -> List[Dict]:
        """把所有 MCP 工具转成 OpenAI 工具定义（重名加 服务器名前缀）。"""
        schemas: List[Dict] = []
        taken = set()
        for server, client in self.clients.items():
            try:
                tools = client.list_tools()
            except Exception as e:
                ui.warn(f"MCP {server}: 获取工具列表失败（{e}）")
                continue
            for t in tools:
                real = t.get("name") or ""
                if not real:
                    continue
                exposed = _safe_tool_name(real)
                if exposed in taken:
                    exposed = _safe_tool_name(f"{server}__{real}")
                if exposed in taken:
                    continue
                taken.add(exposed)
                self._by_tool[exposed] = (client, real)
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": exposed,
                        "description": t.get("description") or f"MCP 工具（来自 {server}）",
                        "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
                    },
                })
                ui.dim(f"MCP 工具已注入: {exposed}（{server}）")
        return schemas

    def has(self, tool_name: str) -> bool:
        return tool_name in self._by_tool

    def call(self, tool_name: str, arguments: Dict) -> str:
        client, real = self._by_tool[tool_name]
        return client.call(real, arguments)

    def shutdown(self) -> None:
        for client in self.clients.values():
            client.close()
        self.clients.clear()
