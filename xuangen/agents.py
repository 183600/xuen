"""Agent 执行器：DirectAgent（直连 LLM 工具循环）与 ShellAgent（外部 agent 命令）。"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

from .config import Config
from .llm import LLMClient
from .procs import kill_process_tree, popen_kwargs
from .tools import ToolBox
from .ui import ui


class DirectAgent:
    """直连 LLM：思考实时流式输出；同一消息里的多个工具调用并行执行。"""

    def __init__(self, llm: LLMClient, toolbox: ToolBox, cfg: Config):
        self.llm = llm
        self.toolbox = toolbox
        self.max_steps = max(1, cfg.agent.max_steps)

    def run_round(self, history: List[Dict], round_message: str) -> List[Dict]:
        messages = history + [{"role": "user", "content": round_message}]
        exhausted = True
        for step in range(1, self.max_steps + 1):
            ui.rule(f"研究者思考 · 第 {step} 步")
            msg = self.llm.chat(
                messages,
                tools=self.toolbox.schemas,
                on_text=ui.agent_chunk,
                on_reasoning=ui.agent_reasoning_chunk,
            )
            ui.raw("\n")
            messages.append(msg)

            calls = msg.get("tool_calls") or []
            if not calls:
                exhausted = False
                if not (msg.get("content") or "").strip():
                    ui.warn("模型返回了空消息，本轮提前结束")
                break

            # 并行执行同一条消息里的全部工具调用，按原顺序回填结果
            with ThreadPoolExecutor(max_workers=len(calls)) as pool:
                futures = [pool.submit(self._exec_tool_call, tc) for tc in calls]
                results = [f.result() for f in futures]
            for tc, result in zip(calls, results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })
        if exhausted:
            ui.warn(f"已达到单轮最大步数 {self.max_steps}，强制进入下一轮")
        return messages

    def _exec_tool_call(self, tc: Dict) -> str:
        fn = tc.get("function") or {}
        name = fn.get("name", "?")
        try:
            arguments = json.loads(fn.get("arguments") or "{}")
            if not isinstance(arguments, dict):
                arguments = {"value": arguments}
        except json.JSONDecodeError as e:
            return f"参数 JSON 解析失败: {e}"
        brief = json.dumps(arguments, ensure_ascii=False)
        ui.tool(f"{name}({brief if len(brief) <= 200 else brief[:200] + '…'})")
        return self.toolbox.execute(name, arguments)


def _quote(prompt: str) -> str:
    if os.name == "nt":  # Windows cmd 的引号规则
        return subprocess.list2cmdline([prompt])
    return shlex.quote(prompt)


class ShellAgent:
    """通过 shell 命令调用外部 agent（opencode / claude / aider …）。

    命令模板占位符：
      "$prompt" / $prompt   —— 替换为 shell 转义后的整段提示词
      $prompt_file          —— 提示词写入 工作区/.prompt.md，替换为该文件路径
    """

    def __init__(self, command: str, workspace: Path, timeout: float = 1800.0):
        self.template = command
        self.workspace = workspace
        self.timeout = timeout

    def render_command(self, prompt: str) -> str:
        tpl = self.template
        if "$prompt_file" in tpl:
            pfile = self.workspace / ".prompt.md"
            pfile.write_text(prompt, encoding="utf-8")
            tpl = tpl.replace("$prompt_file", str(pfile.resolve()))
        quoted = _quote(prompt)
        if '"$prompt"' in tpl:
            return tpl.replace('"$prompt"', quoted)
        if "'$prompt'" in tpl:
            return tpl.replace("'$prompt'", quoted)
        return tpl.replace("$prompt", quoted)

    def run(self, prompt: str) -> str:
        command = self.render_command(prompt)
        ui.rule("外部 agent")
        shown = command if len(command) <= 300 else command[:300] + " …"
        ui.dim(f"$ {shown}")

        proc = subprocess.Popen(
            command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            **popen_kwargs(),
        )
        out: List[str] = []
        err: List[str] = []
        killed = {"flag": False}

        def pump(pipe, sink: List[str], echo: bool) -> None:
            try:
                for line in pipe:
                    sink.append(line)
                    if echo:
                        ui.raw(line)              # agent 输出原样上屏
                    else:
                        ui.dim("│ " + line.rstrip("\n"))
            except Exception:
                pass

        t_out = threading.Thread(target=pump, args=(proc.stdout, out, True), daemon=True)
        t_err = threading.Thread(target=pump, args=(proc.stderr, err, False), daemon=True)
        t_out.start()
        t_err.start()

        def _on_timeout() -> None:
            killed["flag"] = True
            kill_process_tree(proc)

        timer = threading.Timer(self.timeout, _on_timeout)
        timer.daemon = True
        timer.start()
        try:
            proc.wait()
        except KeyboardInterrupt:
            kill_process_tree(proc)
            raise
        finally:
            timer.cancel()
            t_out.join(timeout=5)
            t_err.join(timeout=5)
        if killed["flag"]:
            ui.warn(f"外部 agent 超时（{self.timeout:.0f}s），已强制终止")
        return "".join(out)
