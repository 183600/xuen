"""direct 模式的内置工具：generate_idea / generate_artifact / run_shell（+ MCP 注入的工具）。"""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Dict, List

from . import state
from .config import Config
from .mcp import MCPManager, MCPToolError
from .procs import kill_process_tree, popen_kwargs
from .ui import ui


def _schema(name: str, description: str, parameters: Dict) -> Dict:
    return {"type": "function",
            "function": {"name": name, "description": description, "parameters": parameters}}


SCHEMA_GENERATE_IDEA = _schema(
    "generate_idea",
    "生成想法：用新内容【整体覆盖】状态文件 research.md 中的『想法区』。内容会持久化并实时展示给用户。",
    {"type": "object",
     "properties": {"content": {"type": "string", "description": "想法区的完整新内容（Markdown）"}},
     "required": ["content"]},
)

SCHEMA_GENERATE_ARTIFACT = _schema(
    "generate_artifact",
    "生成产物：用新内容【整体覆盖】状态文件 research.md 中的『产物区』"
    "（方案、伪代码、推导、实验设计、实验结果等）。内容会持久化并实时展示给用户。",
    {"type": "object",
     "properties": {"content": {"type": "string", "description": "产物区的完整新内容（Markdown/代码）"}},
     "required": ["content"]},
)

SCHEMA_RUN_SHELL = _schema(
    "run_shell",
    "在 shell 中执行命令并返回输出（stdout 与 stderr 合并）。默认工作目录为当前工作区。",
    {"type": "object",
     "properties": {
         "command": {"type": "string", "description": "要执行的命令"},
         "cwd": {"type": "string", "description": "工作目录（默认：工作区）"},
         "timeout": {"type": "integer", "description": "超时秒数（默认见配置）"},
     },
     "required": ["command"]},
)


class ToolBox:
    def __init__(self, cfg: Config, workspace: Path, state_path: Path, mcp: MCPManager):
        self.cfg = cfg
        self.workspace = workspace
        self.state_path = state_path
        self.mcp = mcp
        self._file_lock = threading.Lock()

        self.schemas: List[Dict] = [SCHEMA_GENERATE_IDEA, SCHEMA_GENERATE_ARTIFACT]
        if cfg.tools.shell:
            self.schemas.append(SCHEMA_RUN_SHELL)
        self.schemas.extend(mcp.collect_tools())

    # ------------------------------------------------------------------
    def execute(self, name: str, arguments: Dict) -> str:
        """执行一次工具调用，永不抛异常（错误以文本形式返回给模型）。"""
        try:
            if name == "generate_idea":
                return self._write(state.SECTION_IDEA, "想法区", arguments)
            if name == "generate_artifact":
                return self._write(state.SECTION_ARTIFACT, "产物区", arguments)
            if name == "run_shell":
                return self._run_shell(arguments)
            if self.mcp.has(name):
                return self._run_mcp(name, arguments)
            return f"错误：未知工具 {name}"
        except Exception as e:
            return f"工具执行异常 {type(e).__name__}: {e}"

    # ------------------------------------------------------------------
    def _write(self, section: str, label: str, arguments: Dict) -> str:
        content = (arguments.get("content") or "").strip()
        if not content:
            return "错误：content 为空"
        with self._file_lock:
            state.update_section_file(self.state_path, section, content)
        ui.rule(f"✍ {label} 已覆盖（已持久化到 {self.state_path.name}）")
        ui.raw(content + "\n")
        return f"{label}已整体覆盖并展示给用户（{len(content)} 字符）。"

    def _run_mcp(self, name: str, arguments: Dict) -> str:
        try:
            out = self.mcp.call(name, arguments)
        except MCPToolError as e:
            out = f"工具返回错误: {e}"
        except Exception as e:
            out = f"调用失败: {e}"
        for ln in out.splitlines():
            ui.stream_line(ln)
        return self._truncate(out)

    def _run_shell(self, arguments: Dict) -> str:
        command = (arguments.get("command") or "").strip()
        if not command:
            return "错误：command 为空"
        cwd = arguments.get("cwd") or str(self.workspace)
        timeout = int(arguments.get("timeout") or self.cfg.tools.shell_timeout)
        ui.shell(command)

        try:
            proc = subprocess.Popen(
                command, shell=True, cwd=cwd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                **popen_kwargs(),
            )
        except Exception as e:
            return f"启动失败: {e}"

        chunks: List[str] = []
        killed = {"flag": False}

        def _on_timeout() -> None:
            killed["flag"] = True
            kill_process_tree(proc)

        timer = threading.Timer(timeout, _on_timeout)
        timer.daemon = True
        timer.start()
        try:
            for line in proc.stdout:      # 实时上屏
                chunks.append(line)
                ui.stream_line(line)
            proc.wait()
        except KeyboardInterrupt:
            kill_process_tree(proc)
            raise
        finally:
            timer.cancel()

        output = "".join(chunks)
        if killed["flag"]:
            output += f"\n[xuangen] 命令超时（{timeout}s），已强制终止"
        elif proc.returncode not in (0, None):
            output += f"\n[xuangen] 退出码 {proc.returncode}"
        return self._truncate(output)

    def _truncate(self, text: str) -> str:
        limit = self.cfg.tools.max_tool_output
        if len(text) <= limit:
            return text or "(无输出)"
        keep = limit // 2
        return text[:keep] + f"\n…[输出共 {len(text)} 字符，超出部分已截断]…\n" + text[-keep:]
