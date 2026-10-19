"""run_tui() 退出码回归测试：Ctrl+C 中断必须返回 130。

回归背景：run_tui() 原先先检查 worker.is_alive() 再检查 interrupted，
后台线程未能在 20s 超时内收尾时，用户按 Ctrl+C 会被误报成「全部轮次
执行失败」的退出码 1，与 README（130 = 被 Ctrl+C 中断）及无 TUI 路径
的退出码约定相反。
"""
from __future__ import annotations

import pytest

pytest.importorskip("textual")

from xuen import tui
from xuen.config import Config


class _FakeWorker:
    def __init__(self, alive: bool):
        self.alive = alive
        self.join_timeouts: list[float | None] = []

    def join(self, timeout=None):
        self.join_timeouts.append(timeout)

    def is_alive(self):
        return self.alive


def _run_tui(monkeypatch, *, interrupted, alive, exit_code=0):
    apps = []

    class FakeApp:
        def __init__(self, cfg, task, regen_words=False):
            self.interrupted = interrupted
            self.exit_code = exit_code
            self._worker = _FakeWorker(alive)
            apps.append(self)

        def run(self):
            pass

    monkeypatch.setattr(tui, "XuangenApp", FakeApp)
    code = tui.run_tui(Config(), "任务")
    assert apps[0]._worker.join_timeouts == [20]
    return code


def test_interrupted_returns_130_even_if_worker_still_alive(monkeypatch):
    assert _run_tui(monkeypatch, interrupted=True, alive=True) == 130


def test_interrupted_returns_130_after_worker_finished(monkeypatch):
    assert _run_tui(monkeypatch, interrupted=True, alive=False) == 130


def test_stuck_worker_without_interrupt_returns_1(monkeypatch):
    assert _run_tui(monkeypatch, interrupted=False, alive=True) == 1


def test_clean_worker_returns_recorded_exit_code(monkeypatch):
    assert _run_tui(monkeypatch, interrupted=False, alive=False,
                    exit_code=1) == 1
    assert _run_tui(monkeypatch, interrupted=False, alive=False) == 0
