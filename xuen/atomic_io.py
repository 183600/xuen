"""原子写文件的小工具。

状态文件、词库和轮次守卫的元数据都采用同一套写法：先写同目录下带
PID 的临时文件，再用 ``os.replace`` 发布。这样读端永远看不到半截内容，
并发实例也不会互相覆盖临时文件；写入或发布被中断时会清掉半成品。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def atomic_write_text(path: Path, text: str, *,
                      newline: Optional[str] = None) -> None:
    """把 UTF-8 文本原子写入 ``path``。

    ``newline`` 会原样传给 ``open``：传 ``""`` 可保留文本自带的换行符
    （用于读写用户可编辑的状态文件），默认 ``None`` 则按平台转换。
    """
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
