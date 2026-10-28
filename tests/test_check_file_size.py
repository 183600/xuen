"""scripts/check_file_size.py 的小测试：红线、边界与生成物排除。"""
from __future__ import annotations

from pathlib import Path

from scripts import check_file_size


def _write(path: Path, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n" * lines, encoding="utf-8")


def test_file_at_limit_passes(tmp_path):
    _write(tmp_path / "ok.py", check_file_size.MAX_LINES)
    assert check_file_size.find_oversized(tmp_path) == []
    assert check_file_size.main([str(tmp_path)]) == 0


def test_file_over_limit_is_reported(tmp_path, capsys):
    _write(tmp_path / "big.py", check_file_size.MAX_LINES + 1)
    offenders = check_file_size.find_oversized(tmp_path)
    assert [(str(rel), lines) for rel, lines in offenders] == [
        ("big.py", check_file_size.MAX_LINES + 1)]

    assert check_file_size.main([str(tmp_path)]) != 0
    out = capsys.readouterr().out
    assert "big.py" in out
    assert str(check_file_size.MAX_LINES + 1) in out


def test_generated_files_are_excluded(tmp_path):
    _write(tmp_path / "pkg.generated.big.py", check_file_size.MAX_LINES + 1)
    _write(tmp_path / "pkg.generated" / "big.py", check_file_size.MAX_LINES + 1)
    _write(tmp_path / "pkg.generated_dir" / "big.py", 1)
    _write(tmp_path / "small.py", 1)
    assert check_file_size.find_oversized(tmp_path) == []
    assert check_file_size.main([str(tmp_path)]) == 0


def test_cache_and_virtualenv_dirs_are_excluded(tmp_path):
    _write(tmp_path / ".venv" / "big.py", check_file_size.MAX_LINES + 1)
    _write(tmp_path / "__pycache__" / "big.py", check_file_size.MAX_LINES + 1)
    _write(tmp_path / "build" / "big.py", check_file_size.MAX_LINES + 1)
    assert check_file_size.find_oversized(tmp_path) == []


def test_custom_limit_is_honored(tmp_path):
    _write(tmp_path / "medium.py", 10)
    assert check_file_size.find_oversized(tmp_path, max_lines=10) == []
    assert check_file_size.find_oversized(tmp_path, max_lines=9) == [
        (Path("medium.py"), 10)]
