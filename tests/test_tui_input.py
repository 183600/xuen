"""TUI 输入框行为测试：空输入按 q 退出、有内容时 q 是普通字符。

回归背景（textual 8.x 实测）：事件派发会沿 MRO 依次调用各层级的
_on_key —— stop() 只阻止冒泡，基类 Input._on_key 仍会被调用并把可打印
字符插入输入框；空输入按 q 退出时必须同时 prevent_default()，否则退出
前输入框里会留下一个 "q" 残字。
"""
import asyncio

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
