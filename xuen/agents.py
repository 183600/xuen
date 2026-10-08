"""外部 agent 执行器：通过 shell 命令调用 opencode / claude / aider 等外部 agent。

xuen 不再内置直连 LLM 的模式 —— 所有的"研究者思考"都由外部 agent 完成：
程序把任务/灵感词/当前状态拼成提示词交给外部 agent，agent 通过
workspace/write_section.py 直接写文件来"覆盖想法区 / 产物区"。
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional

from .procs import kill_process_tree, popen_kwargs
from .ui import ui

OutputCallback = Callable[[str], None]


def _default_on_output(line: str) -> None:
    ui.raw(line)


def _default_on_stderr(line: str) -> None:
    ui.dim("│ " + line.rstrip("\n"))


def _quote(prompt: str) -> str:
    if os.name == "nt":  # Windows cmd 的引号规则
        return subprocess.list2cmdline([prompt])
    return shlex.quote(prompt)


class ShellAgent:
    """通过 shell 命令调用外部 agent（opencode / claude / aider …）。

    命令模板占位符：
      "$prompt" / $prompt   —— 替换为 shell 转义后的整段提示词
      $prompt_file          —— 提示词写入 工作区/.prompt.md，替换为该文件路径

    on_output / on_stderr：每行输出的回调（默认打到终端；TUI 模式下注入到界面）。
    """

    def __init__(
        self,
        command: str,
        workspace: Path,
        timeout: float = 1800.0,
        on_output: Optional[OutputCallback] = None,
        on_stderr: Optional[OutputCallback] = None,
    ):
        self.template = command
        self.workspace = workspace
        self.timeout = timeout
        self.on_output = on_output or _default_on_output
        self.on_stderr = on_stderr or _default_on_stderr
        self._proc: Optional[subprocess.Popen] = None

    # 占位符必须是“完整词”：$prompt_out / $prompt_filex 之类只是以
    # 占位符为前缀的普通变量，不能被子串替换误伤
    _PLACEHOLDER_BOUNDARY = r"(?![A-Za-z0-9_])"

    def render_command(self, prompt: str) -> str:
        tpl = self.template
        if re.search(r"\$prompt_file" + self._PLACEHOLDER_BOUNDARY, tpl):
            pfile = self.workspace / ".prompt.md"
            pfile.write_text(prompt, encoding="utf-8")
            # 路径可能含空格：与 $prompt 一样做 shell 转义后再替换
            quoted_path = _quote(str(pfile.resolve()))
            tpl = re.sub(r"\$prompt_file" + self._PLACEHOLDER_BOUNDARY,
                         lambda m: quoted_path, tpl)
        quoted = _quote(prompt)
        # 先统一替换成哨兵再一次性换成 quoted，避免提示词内容里
        # 恰好含有 "$prompt" 时被二次替换、破坏 shell 引号结构
        sentinel = "\0XUEN_PROMPT\0"
        for ph in ('"$prompt"', "'$prompt'"):
            tpl = tpl.replace(ph, sentinel)
        tpl = re.sub(r"\$prompt" + self._PLACEHOLDER_BOUNDARY, sentinel, tpl)
        return tpl.replace(sentinel, quoted)

    def kill(self) -> None:
        """强制终止当前正在运行的外部 agent（TUI 退出 / 中断时使用）。"""
        proc = self._proc
        if proc is not None and proc.poll() is None:
            kill_process_tree(proc)

    def run(self, prompt: str) -> str:
        command = self.render_command(prompt)
        shown = command if len(command) <= 300 else command[:300] + " …"
        self.on_stderr(f"$ {shown}\n")

        proc = subprocess.Popen(
            command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            **popen_kwargs(),
        )
        self._proc = proc
        out: List[str] = []
        killed = {"flag": False}

        def pump(pipe, sink: List[str], cb: OutputCallback) -> None:
            try:
                for line in pipe:
                    sink.append(line)
                    try:
                        cb(line)
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        t_out = threading.Thread(target=pump, args=(proc.stdout, out, self.on_output), daemon=True)
        t_err = threading.Thread(target=pump, args=(proc.stderr, [], self.on_stderr), daemon=True)
        t_out.start()
        t_err.start()

        def _on_timeout() -> None:
            if proc.poll() is not None:
                return  # 进程已正常退出，避免竞态误报超时/误杀
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
            self._proc = None
        if killed["flag"]:
            # :g 避免小数秒（如 0.5）被 :.0f 四舍五入成「0s」
            self.on_stderr(f"外部 agent 超时（{self.timeout:g}s），已强制终止\n")
        elif proc.returncode:
            self.on_stderr(f"外部 agent 异常退出（退出码 {proc.returncode}），"
                           "本轮可能未更新区块\n")
        return "".join(out)
