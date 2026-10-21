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


def test_task_file_conflict_returns_2_not_raise(tmp_path, capsys):
    """位置参数与 --task-file 冲突：main() 必须返回 2，而不是让
    _resolve_task 的 SystemExit 外泄（main 的契约是返回 int）。"""
    rc = cli.main(["-c", EXAMPLE, "任务", "--task-file", str(tmp_path / "t")])
    assert rc == 2
    assert "不能同时使用" in capsys.readouterr().err


def test_huge_iterations_returns_2_not_traceback(capsys):
    """CLI 覆盖的巨大轮数必须在 _validate 阶段拒绝（range 无法表示）。"""
    rc = cli.main(["-c", EXAMPLE, "--iterations", "9" * 400, "任务"])
    assert rc == 2
    assert "iterations" in capsys.readouterr().err


def test_unreadable_task_file_returns_2_not_raise(tmp_path, capsys):
    """任务文件读不到：同样返回 2（错误信息已打印），不外泄 SystemExit。"""
    rc = cli.main(["-c", EXAMPLE, "--task-file", str(tmp_path / "missing")])
    assert rc == 2
    assert "无法读取任务文件" in capsys.readouterr().err


def test_surrogate_task_rejected_with_exit_2(capsys):
    """终端传入非法字节（surrogateescape 解出孤立代理字符）时给出退出码 2
    的明确错误，而不是把 UnicodeEncodeError 留到写状态文件/提示词时炸掉。"""
    rc = cli.main(["-c", EXAMPLE, "坏任务\udcff"])
    assert rc == 2
    assert "UTF-8" in capsys.readouterr().err


def test_invalid_utf8_at_task_prompt_returns_2(monkeypatch, capsys):
    """stdin 严格解码失败（管道里是非法 UTF-8）同样给退出码 2 的友好错误，
    不能让 UnicodeDecodeError 从 input() 外泄成 traceback。"""
    def bad_input(prompt=""):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    monkeypatch.setattr("builtins.input", bad_input)
    rc = cli.main(["-c", EXAMPLE])
    assert rc == 2
    assert "UTF-8" in capsys.readouterr().err


def test_missing_stdin_at_task_prompt_returns_2(monkeypatch, capsys):
    """无控制台解释器（sys.stdin is None）时 input() 抛 RuntimeError，
    不能外泄成 traceback：按「未提供任务」返回退出码 2。"""
    monkeypatch.setattr("sys.stdin", None)
    rc = cli.main(["-c", EXAMPLE])
    assert rc == 2
    assert "未提供任务" in capsys.readouterr().out
