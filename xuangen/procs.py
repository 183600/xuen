"""跨平台进程工具。"""
from __future__ import annotations

import os
import signal
import subprocess

POSIX = os.name == "posix"


def popen_kwargs() -> dict:
    """POSIX 下新开进程组，便于整组 kill。"""
    return {"start_new_session": True} if POSIX else {}


def kill_process_tree(proc: subprocess.Popen) -> None:
    if POSIX:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass
