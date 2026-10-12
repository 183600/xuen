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
from textual import events
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


class _InputBox(Input):
    """底部输入框：为空时按 q 退出；已有内容时 q 作为普通字符输入。

    Input 会消费可打印字符键（事件不会冒泡到 App 的 BINDINGS），
    因此必须在这里拦截，否则「按 q 退出」在输入框聚焦时永远不生效。
    """

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "q" and not self.value:
            event.stop()
            await self.app.action_quit()  # textual >= 1.0 起 action_quit 是协程，必须 await
            return
        await super()._on_key(event)


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
        self.app.post_finished()  # 先阻断新输入并丢弃无法再投递的排队内容
        self._log("─" * 12 + " 研究循环结束 " + "─" * 12, "bold green")
        self.section(SECTION_IDEA, idea)
        self.section(SECTION_ARTIFACT, artifact)
        self.app.post_status("已结束（按 q 或 Ctrl+C 退出）")


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
        self.loop_finished = False
        # 后台 _run_loop 线程失败时改写为非 0；必须在 __init__ 初始化，
        # 否则不走 run_tui() 的运行方式（测试、嵌入）会 AttributeError
        self.exit_code = 0
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
        yield _InputBox(
            placeholder="输入给 agent 的话，回车提交 —— 将在下次调用 agent 时带给 agent（空输入时按 q 退出）",
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
            # 记录失败退出码：run_tui() 最终把它作为进程退出码返回，
            # 否则配置错误等失败会被掩盖成「成功退出」。
            # 与 cli 无 TUI 路径的约定保持一致：int code（runner 的运行期
            # 失败 SystemExit(1)）按其值传递；字符串 code 是预检错误的
            # 日志消息，统一映射为 2（不能记 1，否则与「全部轮次失败」的
            # 退出码混淆，且同一失败在 TUI / 无 TUI 下退出码相反）。
            # SystemExit(0) / SystemExit(None) 是正常退出，不能误记为失败
            if isinstance(e.code, int):
                self.exit_code = e.code
                self.post_status(f"已退出（退出码 {e.code}）" if e.code else "已退出")
            elif e.code is None:
                self.exit_code = 0
                self.post_status("已退出")
            else:
                self.exit_code = 2
                self.sink.err(str(e.code))
                self.post_status(f"已退出：{e.code}")
        except KeyboardInterrupt as e:
            # runner 会向上传播 SIGINT；不捕获则退出码/状态栏丢失
            self.exit_code = 130
            self.sink.err(f"被中断：{e!r}")
            self.post_status("已中断（按 q 退出）")
        except Exception as e:  # 后台线程里的异常要打到界面上
            self.exit_code = 1
            self.sink.err(f"运行异常：{e!r}")
            self.post_status("异常结束（按 q 退出）")
        finally:
            self.post_finished()  # 异常路径也停止接收输入（finish() 路径下是幂等的）

    # ---- 线程 → 界面 的安全投递 ----
    def _safe_call_from_thread(self, fn) -> None:
        # app 退出后继续投递不仅会被丢弃，textual 内部已创建的回调协程
        # 也无处调度，产生 "coroutine was never awaited" RuntimeWarning
        if not self.is_running:
            return
        try:
            self.call_from_thread(fn)
        except Exception:
            pass  # 应用已在退出过程中，丢弃后台线程的界面更新

    def post_log(self, text: str, style: str = "") -> None:
        def _write() -> None:
            self.query_one("#log", RichLog).write(Text(text, style=style))
        self._safe_call_from_thread(_write)

    def post_section(self, name: str, content: str) -> None:
        # 显式映射：未知的区块名直接报错，不能静默写进产物区面板
        widget_id = {SECTION_IDEA: "#idea", SECTION_ARTIFACT: "#artifact"}[name]
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
        """停止接收新输入，并清空 loop 已经结束后来不及投递的队列。"""
        self.loop_finished = True
        dropped = self.drain_user_input()
        if dropped:
            self.post_log(
                f"研究循环已开始收尾，已丢弃 {len(dropped)} 条来不及投递的输入",
                "bold yellow",
            )

    # ---- 用户输入 ----
    def on_input_submitted(self, event: Input.Submitted) -> None:
        # 先清空输入框：内容残留在框里会让用户以为没提交成功，且输入框
        # 非空时按 q 会被当作普通字符输入而无法退出（纯空白提交也应清空）
        self.query_one("#user-input", Input).value = ""
        text = event.value.strip()
        if not text:
            return
        if self.loop_finished:
            self.query_one("#log", RichLog).write(
                Text("循环已结束，本次输入不会被投递", style="bold yellow")
            )
            return
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
    async def action_quit(self) -> None:  # textual >= 1.0 起是协程，覆盖时也必须 async
        self.stop_requested = True
        self.sink.stop_agent()
        self.exit()


def run_tui(cfg: Config, task: str, *, regen_words: bool = False) -> int:
    app = XuangenApp(cfg, task, regen_words)
    app.run()
    # 等后台 _run_loop 线程收尾：action_quit() 只设置了 stop_requested 并
    # 停掉 agent，worker 此刻可能仍在运行并即将改写 exit_code；不等它就把
    # 初始值 0 返回，失败会被掩盖成「成功退出」。agent 已被 stop_agent()
    # 终止，正常几秒之内线程就会退出；超时兜底防止极端情况下卡死进程。
    # 注意上限必须覆盖 agent 收尾的最坏耗时（超时回调里的 wait/join 合计
    # 可达 ~15s），否则正常退出会被误报为失败退出码 1
    worker = app._worker
    if worker is not None:
        worker.join(timeout=20)
        # join 超时时 exit_code 可能仍是初始的 0；不能把未干净收尾误报为成功
        if worker.is_alive():
            return 1
    return getattr(app, "exit_code", 0)
