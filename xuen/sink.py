"""输出通道（sink）抽象：runner 不直接打印，所有展示都经 sink 上报。

- ConsoleSink：纯终端输出（--no-tui）
- TuiSink（tui.py 中实现）：驱动 TUI 界面

区块上报约定：name 为 "idea" / "artifact"；sink 负责以
[修改想法区]<写入想法区的内容> / [修改产物区]<写入产物区的内容> 的形式展示。
"""
from __future__ import annotations

from typing import List

from .ui import ui

SECTION_IDEA = "idea"
SECTION_ARTIFACT = "artifact"

SECTION_TAG = {
    SECTION_IDEA: "[修改想法区]",
    SECTION_ARTIFACT: "[修改产物区]",
}

SECTION_TITLE = {
    SECTION_IDEA: "修改想法区",
    SECTION_ARTIFACT: "修改产物区",
}


class Sink:
    """runner 的展示/交互接口。"""

    # ---- 普通消息 ----
    def info(self, text: str) -> None: raise NotImplementedError
    def ok(self, text: str) -> None: raise NotImplementedError
    def warn(self, text: str) -> None: raise NotImplementedError
    def err(self, text: str) -> None: raise NotImplementedError

    # ---- 循环事件 ----
    def round_header(self, index: int, label: str) -> None:
        """每一轮开始（label 为灵感词展示文本）。"""
        raise NotImplementedError

    # ---- 外部 agent 输出（逐行） ----
    def agent_output(self, line: str) -> None: raise NotImplementedError
    def agent_stderr(self, line: str) -> None: raise NotImplementedError

    # ---- 区块被覆盖后上报 ----
    def section(self, name: str, content: str) -> None: raise NotImplementedError

    # ---- 用户输入（底部输入框的内容，在下次调用 agent 时带给 agent） ----
    def drain_user_input(self) -> List[str]:
        return []

    # ---- 结束/停止 ----
    def finish(self, idea: str, artifact: str) -> None: pass

    def should_stop(self) -> bool:
        """外部（如 TUI 退出）请求停止循环。"""
        return False

    def stop_agent(self) -> None:
        """请求终止当前正在运行的外部 agent。runner 会注入 agent 引用。"""
        agent = getattr(self, "agent", None)
        if agent is not None:
            agent.kill()


class ConsoleSink(Sink):
    """纯终端输出（--no-tui 模式）。"""

    def info(self, text: str) -> None: ui.info(text)
    def ok(self, text: str) -> None: ui.ok(text)
    def warn(self, text: str) -> None: ui.warn(text)
    def err(self, text: str) -> None: ui.err(text)

    def round_header(self, index: int, label: str) -> None:
        ui.rule(f"第 {index} 轮 · 灵感词：{label}")

    def agent_output(self, line: str) -> None:
        ui.raw(line)

    def agent_stderr(self, line: str) -> None:
        ui.dim("│ " + line.rstrip("\n"))

    def section(self, name: str, content: str) -> None:
        tag = SECTION_TAG.get(name, f"[{name}]")
        ui.rule(SECTION_TITLE.get(name, name))
        ui.raw(f"{tag}\n{content}\n")

    def finish(self, idea: str, artifact: str) -> None:
        ui.rule("研究循环结束 · 最终状态")
        self.section(SECTION_IDEA, idea)
        self.section(SECTION_ARTIFACT, artifact)
