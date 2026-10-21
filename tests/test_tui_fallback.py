"""TUI 依赖缺失时的降级路径。

README 承诺「textual 装不上/不在真实终端时自动降级为纯终端输出」。
这里在真实终端条件下强制让 TUI 导入失败，确认程序打印提示并继续用
无 TUI 的 runner，而不是退出或 traceback。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _FakeTTY:
    def __init__(self) -> None:
        self.written = []

    def isatty(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self.written.append(text)
        return len(text)

    def flush(self) -> None:
        pass


def test_missing_textual_falls_back_to_terminal(monkeypatch, tmp_path):
    from xuen import cli, runner

    fake_out = _FakeTTY()
    monkeypatch.setattr(cli.sys, "stdin", _FakeTTY())
    monkeypatch.setattr(cli.sys, "stdout", fake_out)

    def no_textual():
        raise ImportError("No module named 'textual'")

    monkeypatch.setattr(cli, "_load_tui", no_textual)

    called = []

    def fake_run(cfg, task, regen_words=False):
        called.append((cfg, task, regen_words))

    monkeypatch.setattr(runner, "run", fake_run)

    rc = cli.main([
        "测试任务",
        "-c", str(ROOT / "config.example.yaml"),
        "--workspace", str(tmp_path / "ws"),
        "--iterations", "1",
    ])
    assert rc == 0
    assert len(called) == 1
    assert called[0][1] == "测试任务"
    assert "未安装 textual" in "".join(fake_out.written)
