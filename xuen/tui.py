"""TUI 界面（基于 textual）。

屏幕布局：
  ┌ 修改想法区 ┐  —— 想法区被覆盖后显示  [修改想法区]<写入想法区的内容>
  ├ 修改产物区 ┤  —— 产物区被覆盖后显示  [修改产物区]<写入产物区的内容>
  ├ 输出日志   ┤  —— 外部 agent 的 stdout/stderr 与循环消息（滚动）
  ├ 状态栏     ┤
  └ 输入框     ┘  —— 输入内容在下次调用 agent 时带给 agent

研究循环在后台线程运行，所有界面更新经 call_from_thread 投递。
"""
from __future__ import annotations

import queue
import threading
from typing import List, Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Input, RichLog, Static

from .config import Config
from .sink import SECTION_ARTIFACT, SECTION_IDEA, SECTION_TAG, SECTION_TITLE, Sink

_CSS = """
Screen {
    layout: vertical;
}
.section-box {
    height: 1fr;
    min-height: 6;
    border: round $primary;
}
.section-box > RichLog {
    height: 1fr;
    padding: 0 1;
    scrollbar-size: 1 1;
}
#log-box {
    height: 2fr;
    min-height: 8;
    border: round $secondary;
}
#log {
    height: 1fr;
    padding: 0 1;
    scrollbar-size: 1 1;
}
#status {
    height: 1;
    padding: 0 1;
    color: $text-muted;
    background: $surface;
}
#user-input {
    height: 3;
    border: round $accent;
}
"""

_LEVEL_STYLE = {"info": "cyan", "ok": "green", "warn": "yellow", "err": "red"}
_LEVEL_PREFIX = {"info": "· ", "ok": "✔ ", "warn": "⚠ ", "err": "✘ "}


class TuiSink(Sink):
    """把 runner 的展示事件投递给 TUI。"""

    def __init__(self, app: "XuangenApp"):
        self.app = app

    def _log(self, text: str, style: str = "") -> None:
        self.app.post_log(text, style)

    def info(self, text: str) -> None:
        self._log(_LEVEL_PREFIX["info"] + text, _LEVEL_STYLE["info"])

    def ok(self, text: str) -> None:
        self._log(_LEVEL_PREFIX["ok"] + text, _LEVEL_STYLE["ok"])

    def warn(self, text: str) -> None:
        self._log(_LEVEL_PREFIX["warn"] + text, _LEVEL_STYLE["warn"])

    def err(self, text: str) -> None:
        self._log(_LEVEL_PREFIX["err"] + text, _LEVEL_STYLE["err"])

    def round_header(self, index: int, label: str) -> None:
        title = f"第 {index} 轮 · 灵感词：{label}"
        self._log("─" * 12 + f" {title} " + "─" * 12, "bold magenta")
        self.app.post_status(f"进行中：{title}")

    def agent_output(self, line: str) -> None:
        self._log(line.rstrip("\n"))

    def agent_stderr(self, line: str) -> None:
        self._log(line.rstrip("\n"), "dim")

    def section(self, name: str, content: str) -> None:
        self.app.post_section(name, content)

    def drain_user_input(self) -> List[str]:
        return self.app.drain_user_input()

    def should_stop(self) -> bool:
        return self.app.stop_requested

    def finish(self, idea: str, artifact: str) -> None:
        self._log("─" * 12 + " 研究循环结束 " + "─" * 12, "bold green")
        self.section(SECTION_IDEA, idea)
        self.section(SECTION_ARTIFACT, artifact)
        self.app.post_status("已结束（按 q 或 Ctrl+C 退出）")
        self.app.post_finished()


class XuangenApp(App):
    """xuen TUI 主程序。"""

    CSS = _CSS
    TITLE = "xuen"
    SUB_TITLE = "随机灵感词 × 外部 agent 研究循环"
    BINDINGS = [("q", "quit", "退出"), ("ctrl+c", "quit", "退出")]

    def __init__(self, cfg: Config, task: str, regen_words: bool = False):
        super().__init__()
        self.cfg = cfg
        self.task_desc = task
        self.regen_words = regen_words
        self.sink = TuiSink(self)
        self._user_inputs: "queue.Queue[str]" = queue.Queue()
        self.stop_requested = False
        self._worker: Optional[threading.Thread] = None

    # ---- 布局 ----
    def compose(self) -> ComposeResult:
        with Vertical(id="idea-box", classes="section-box"):
            yield RichLog(id="idea", wrap=True, auto_scroll=True)
        with Vertical(id="artifact-box", classes="section-box"):
            yield RichLog(id="artifact", wrap=True, auto_scroll=True)
        with VerticalScroll(id="log-box"):
            yield RichLog(id="log", wrap=True, auto_scroll=True)
        yield Static("准备中……", id="status")
        yield Input(
            placeholder="输入给 agent 的话，回车提交 —— 将在下次调用 agent 时带给 agent",
            id="user-input",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#idea-box").border_title = SECTION_TITLE[SECTION_IDEA]
        self.query_one("#artifact-box").border_title = SECTION_TITLE[SECTION_ARTIFACT]
        self.query_one("#log-box").border_title = "输出日志"
        self.query_one("#user-input", Input).focus()
        self._worker = threading.Thread(target=self._run_loop, daemon=True)
        self._worker.start()

    def _run_loop(self) -> None:
        from .runner import run  # 延迟导入避免循环依赖

        try:
            run(self.cfg, self.task_desc, regen_words=self.regen_words, sink=self.sink)
        except SystemExit as e:
            self.sink.err(str(e))
            self.post_status(f"已退出：{e}")
        except Exception as e:  # 后台线程里的异常要打到界面上
            self.sink.err(f"运行异常：{e!r}")
            self.post_status("异常结束（按 q 退出）")

    # ---- 线程 → 界面 的安全投递 ----
    def _safe_call_from_thread(self, fn) -> None:
        try:
            self.call_from_thread(fn)
        except Exception:
            pass  # 应用已在退出过程中，丢弃后台线程的界面更新

    def post_log(self, text: str, style: str = "") -> None:
        def _write() -> None:
            self.query_one("#log", RichLog).write(Text(text, style=style))
        self._safe_call_from_thread(_write)

    def post_section(self, name: str, content: str) -> None:
        widget_id = "#idea" if name == SECTION_IDEA else "#artifact"
        tag = SECTION_TAG.get(name, f"[{name}]")

        def _update() -> None:
            view = self.query_one(widget_id, RichLog)
            view.clear()
            view.write(Text(tag, style="bold yellow"))
            view.write(Text(content))
        self._safe_call_from_thread(_update)

    def post_status(self, text: str) -> None:
        def _update() -> None:
            self.query_one("#status", Static).update(text)
        self._safe_call_from_thread(_update)

    def post_finished(self) -> None:
        pass  # 状态栏已提示；保持界面让用户回看

    # ---- 用户输入 ----
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self.query_one("#user-input", Input).value = ""
        self._user_inputs.put(text)
        log = self.query_one("#log", RichLog)
        log.write(Text(f"⌨ 已记录（下次调用 agent 时带给它）：{text}", style="bold blue"))

    def drain_user_input(self) -> List[str]:
        items: List[str] = []
        while True:
            try:
                items.append(self._user_inputs.get_nowait())
            except queue.Empty:
                break
        return items

    # ---- 退出 ----
    def action_quit(self) -> None:
        self.stop_requested = True
        self.sink.stop_agent()
        self.exit()


def run_tui(cfg: Config, task: str, *, regen_words: bool = False) -> int:
    app = XuangenApp(cfg, task, regen_words)
    app.run()
    return 0
