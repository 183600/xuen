"""CLI 交互式任务输入的 Ctrl+C / EOF 语义测试。

回归背景：_resolve_task 曾把 EOFError 与 KeyboardInterrupt 一并吞成
「未提供任务」的空任务，交互提示处按 Ctrl+C 会得到退出码 2 与一句
误导性的「未提供任务」，与 README 的退出码约定（130 = 被 Ctrl+C
中断）矛盾，也把真正的中断信号静默吞掉。两者必须区分：
- KeyboardInterrupt（Ctrl+C）→ 按中断处理，退出码 130；
- EOFError（stdin 被关闭 / 管道读完）→ 仍按「未提供任务」退出码 2。
"""
from pathlib import Path

import pytest

from xuen import cli

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = str(ROOT / "config.example.yaml")


def _raise(exc):
    def fake_input(prompt=""):
        raise exc
    return fake_input


def test_ctrl_c_at_task_prompt_returns_130(monkeypatch, capsys):
    """交互提示处 Ctrl+C 必须按退出码约定返回 130，而不是「未提供任务」。"""
    monkeypatch.setattr("builtins.input", _raise(KeyboardInterrupt))
    rc = cli.main(["-c", EXAMPLE])
    out = capsys.readouterr()
    assert rc == 130
    assert "未提供任务" not in out.out + out.err


def test_eof_at_task_prompt_still_returns_2(monkeypatch, capsys):
    """stdin 关闭/管道结束（EOF）不是中断：保持「未提供任务」的退出码 2。"""
    monkeypatch.setattr("builtins.input", _raise(EOFError))
    rc = cli.main(["-c", EXAMPLE])
    assert rc == 2


def test_existing_task_never_prompts(monkeypatch):
    """已有任务（位置参数）时不得触碰 stdin：管道里没有输入也不受影响。"""
    def boom(prompt=""):
        pytest.fail("已有任务时不应再询问输入")
    monkeypatch.setattr("builtins.input", boom)
    args = cli.build_parser().parse_args(["设计一个新的优化器"])
    assert cli._resolve_task(args) == "设计一个新的优化器"
