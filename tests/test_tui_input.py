"""TUI 输入框行为测试：空输入按 q 退出、有内容时 q 是普通字符。

回归背景（textual 8.x 实测）：事件派发会沿 MRO 依次调用各层级的
_on_key —— stop() 只阻止冒泡，基类 Input._on_key 仍会被调用并把可打印
字符插入输入框；空输入按 q 退出时必须同时 prevent_default()，否则退出
前输入框里会留下一个 "q" 残字。
"""
import asyncio
import queue
from types import SimpleNamespace

import pytest

pytest.importorskip("textual")

from xuen import tui
from xuen.config import Config


def _scenario(press, checks):
    async def run():
        # Config() 默认没有 agent.command：后台 run() 会立刻以预检错误
        # SystemExit 结束（退出码 2），不会创建任何文件或拉起外部进程
        app = tui.XuangenApp(Config(), "任务")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.2)
            await pilot.press(*press)
            await pilot.pause(0.1)
            checks(app)

    asyncio.run(run())


def test_q_with_empty_input_quits_and_leaves_no_char():
    def checks(app):
        assert app.query_one("#user-input").value == ""
        assert not app.is_running

    _scenario(("q",), checks)


def test_q_with_text_is_plain_char_and_does_not_quit():
    def checks(app):
        assert app.query_one("#user-input").value == "aq"
        assert app.is_running

    _scenario(("a", "q"), checks)


def test_submit_racing_with_finish_does_not_leave_undelivered_input():
    """提交与收尾竞态：收尾先置位并清空队列后，晚到的 put 不能再滞留。

    回归：on_input_submitted 只在 put 前检查 loop_finished；若收尾恰好
    落在检查与 put 之间，输入会永久留在队列里（循环已结束，不会再有
    drain），用户却看到「已记录」。put 之后必须复查并自行清理。
    """
    from xuen import tui

    app = tui.XuangenApp(Config(), "任务")
    submitted = queue.Queue()

    class RaceQueue:
        def put(self, item):
            # 模拟 post_finished() 抢在 put 前完成：置位并清空（当时为空）
            app.loop_finished = True
            submitted.put(item)

        def get_nowait(self):
            return submitted.get_nowait()

    class FakeInput:
        value = ""

    class FakeLog:
        def __init__(self):
            self.lines = []

        def write(self, text):
            self.lines.append(str(text))

    log = FakeLog()
    widgets = {"#user-input": FakeInput(), "#log": log}

    def query_one(selector, *args):
        return widgets[selector]

    app._user_inputs = RaceQueue()
    app.query_one = query_one
    app.on_input_submitted(SimpleNamespace(value="hi"))
    assert submitted.empty()
    assert any("循环已结束" in line for line in log.lines)
