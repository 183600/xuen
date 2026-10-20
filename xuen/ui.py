"""终端输出（带可选 ANSI 颜色）。"""
from __future__ import annotations

import os
import sys

_CODES = {
    "dim": "\033[2m", "bold": "\033[1m", "reset": "\033[0m",
    "cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m",
    "magenta": "\033[35m", "red": "\033[31m", "blue": "\033[34m",
}


class UI:
    def __init__(self, color: bool = True):
        self.color = bool(color)
        if os.name == "nt":
            os.system("")  # 让 Windows 终端识别 ANSI 转义

    # ---- 基础 ----
    def _c(self, code: str, text: str) -> str:
        if not self.color:
            return str(text)
        return f"{_CODES[code]}{text}{_CODES['reset']}"

    def raw(self, text: str = "") -> None:
        # 无控制台解释器（Windows 的 pythonw / 嵌入环境）里 sys.stdout
        # 可能为 None；此时没有可写的终端，直接丢弃输出，不能让每次
        # 日志调用都以 AttributeError 炸掉整个研究循环。
        if sys.stdout is None:
            return
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except BrokenPipeError:
            # 下游已关闭（如 xuen --no-tui … | head）：静默丢弃后续输出。
            # 仅吞掉异常还不够：stdout 是缓冲流，解释器退出时会再次 flush，
            # 触发 Exception ignored 并把退出码改成 120。把底层 fd 重定向到
            # devnull 后，最终 flush 落到空设备，进程才能按真实结果退出。
            try:
                devnull = os.open(os.devnull, os.O_WRONLY)
                try:
                    os.dup2(devnull, sys.stdout.fileno())
                finally:
                    os.close(devnull)
            except (OSError, ValueError):
                pass

    def line(self, prefix: str, text: str, color: str) -> None:
        for ln in str(text).splitlines() or [""]:
            self.raw(self._c(color, prefix + ln) + "\n")

    def rule(self, title: str = "") -> None:
        width = 66
        if title:
            t = f" {title} "
            vis = sum(2 if ord(ch) > 127 else 1 for ch in t)
            pad = max(2, width - vis)
            left = "─" * (pad // 2)
            right = "─" * (pad - pad // 2)
            self.raw("\n" + self._c("cyan", f"{left}{t}{right}") + "\n")
        else:
            self.raw("\n" + self._c("cyan", "─" * width) + "\n")

    def banner(self) -> None:
        self.raw("\n" + self._c("bold", "⟡ xuen ⟡")
                 + self._c("dim", "  随机灵感词 × 人类研究者模拟\n"))

    def info(self, text: str) -> None: self.line("· ", text, "cyan")
    def ok(self, text: str) -> None: self.line("✔ ", text, "green")
    def warn(self, text: str) -> None: self.line("⚠ ", text, "yellow")
    def err(self, text: str) -> None: self.line("✘ ", text, "red")
    def dim(self, text: str) -> None: self.line("", text, "dim")
    def tool(self, text: str) -> None: self.line("⚙ ", text, "magenta")
    def shell(self, text: str) -> None: self.line("$ ", text, "yellow")

    # ---- 流式输出 ----
    def agent_chunk(self, text: str) -> None:
        self.raw(text)

    def agent_reasoning_chunk(self, text: str) -> None:
        self.raw(self._c("dim", text))

    def stream_line(self, line: str) -> None:
        if not line.endswith("\n"):
            line += "\n"
        self.raw(self._c("dim", line))


ui = UI()


def configure(color: bool = True) -> None:
    ui.color = bool(color)
