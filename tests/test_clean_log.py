"""CI 日志净化器的流式边界回归：跨 4KB 块的长转义序列不能漏成正文。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "clean_log.py"


def _run(data: bytes) -> bytes:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=data, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_long_osc_split_across_chunks_is_removed():
    prefix = b"x" * 4000
    data = prefix + b"\x1b]0;" + b"A" * 100 + b"\x07" + "tail\n".encode()
    assert _run(data) == prefix + "tail\n".encode()


def test_long_csi_split_across_chunks_is_removed():
    prefix = b"x" * 4000
    data = prefix + b"\x1b[" + b"1;" * 60 + b"31m" + b"done\n"
    assert _run(data) == prefix + b"done\n"


def test_incomplete_escape_at_eof_is_dropped():
    assert _run(b"ok\x1b[31") == b"ok"
    assert _run(b"ok\x1b]0;title") == b"ok"
    assert _run(b"ok\x1b") == b"ok"


def test_truncated_utf8_at_eof_is_replaced():
    assert _run("ok".encode() + b"\xe4\xb8") == "ok\ufffd".encode()


def test_osc_st_terminator_split_across_chunks_is_removed():
    prefix = b"x" * 4000
    osc = b"\x1b]0;" + b"A" * 91
    data = prefix + osc + b"\x1b\\" + b"tail\n"
    assert _run(data) == prefix + b"tail\n"


def test_malformed_osc_does_not_swallow_following_log():
    assert _run(b"a\x1b]junk\nb") == b"ajunk\nb"


def test_osc_split_right_after_introducer_is_removed():
    prefix = b"x" * 4094
    data = prefix + b"\x1b]0;" + b"A" * 100 + b"\x07" + b"tail\n"
    assert _run(data) == prefix + b"tail\n"


def test_invalid_escape_does_not_swallow_following_log():
    assert _run(b"a\x1bzlog\nb") == b"azlog\nb"
