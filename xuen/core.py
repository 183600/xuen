"""核心功能模块：研究.md 状态文件的读写、区块定位、保护与更新逻辑。"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Tuple, List

from .atomic_io import atomic_write_text


def _atomic_write_text(path: Path, text: str, *, newline: str | None = None) -> None:
    """写入 UTF-8 文本并原子替换目标；任何中断都不留临时半成品。"""
    atomic_write_text(path, text, newline=newline)


def _first_span(text: str, name: str) -> tuple[int, int] | None:
    """区块「当前会被读出」的区间：第一个有效同名区块，无则 None。"""
    s = f"<!-- {name}:START -->"
    for a, b in _section_spans(text):
        if text.startswith(s, a):
            return (a, b)
    return None


def _normalize_newlines(text: str) -> str:
    """把 CRLF / CR 统一为 LF，供区块内容与读回文本使用。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_back_section(candidate: str, name: str) -> str | None:
    """按 get_section 的规则回读 candidate 中指定区块，供写盘后校验。
    
    返回 None 表示区块缺失或交叉失效（区别于写入空内容）。
    """
    s, e = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    back = next(
        (candidate[a + len(s): b - len(e)].strip("\r\n")
         for a, b in _section_spans(candidate)
         if candidate.startswith(s, a)),
        None,
    )
    return None if back is None else _normalize_newlines(back)


def _preserve_other_section(original: str, text: str, name: str) -> str:
    """保证另一类区块读出的内容与更新前（original）一致。
    
    更新一个区块只清除本区块的标记行；原先因与本区块标记「交叉配对」
    而失效的另一类区块残片，可能因此重新配对，抢在真实区块前面被读出，
    使另一区块读出的内容被悄悄改写。这里检出抢先配对的残片并清除其
    标记行（残片区间内的正文保留为自由文本），直到读出内容回到更新前。
    与 xuen.state._preserve_other_section 保持一致。"""
    other = "ARTIFACT" if name == "IDEA" else "IDEA"
    want = _first_section(original, other)
    if want is None:
        # 另一区块原本就不可读，没有需要保护的内容
        return text
    s, e = f"<!-- {other}:START -->", f"<!-- {other}:END -->"
    # 与 xuen.state._preserve_other_section 一致：按标记数限制轮数，
    # 固定 64 轮会静默放弃保护、改写另一区块。
    max_passes = min(text.count(s), 4096)
    if not max_passes:
        raise ValueError("状态文件另一区块已损坏，无法安全更新")
    for _ in range(max_passes):
        if _first_section(text, other) == want:
            return text
        shadow = _first_span(text, other)
        if shadow is None:
            raise ValueError("状态文件另一区块已损坏，无法安全更新")
        # 保护除抢先配对残片外的所有有效区块，只清除残片的标记行
        protected = [(a, b) for a, b in _section_spans(text) if (a, b) != shadow]
        # 真实区块也可能因交叉配对、当前不是「有效区块」；它的候选配对
        # 区间同样要保护，避免把真实区块的标记行一并清除
        # （与 xuen.state._preserve_other_section 保持一致）
        protected += [p for p in _paired_spans(text, other) if p != shadow]
        text = _strip_stray(text, protected, 0, s, e)
    raise ValueError("状态文件区块标记嵌套过深，无法安全更新")


@contextmanager
def _locked():
    """与 xuen.state.update_section_file 使用同一个 sidecar 锁，
    防止两个 agent/进程并发读-改-写时互相覆盖他人的更新。"""
    os.makedirs(os.path.dirname(Path(__file__).parent / "workspace/research.md"), exist_ok=True)
    state_file = Path(__file__).parent / "workspace" / "research.md"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file + ".lock", "a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            if not lock.read(1):
                lock.write(b"\\0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def sanitize_section_content(content: str) -> str:
    """区块内容写入 update_section_file 时会得到的规整形态。
    
    与本区块 END 一样，任何独成一行的区块标记都会参与 _section_spans
    配对：若作为内容原样写入，会被当成真实区块边界，导致相邻区块内容
    被截断甚至覆盖。行内提及不受影响；仅清除独占一行的标记。
    剥离标记行后，首/尾行可能残留空白或 BOM（如内容以标记行开头、
    紧随其后的正文行带缩进）：get_section/_first_section 读出时同样
    会剥掉这些字符，因此必须用本函数规整后再比较，否则含标记字面量的
    区块在落盘规整后永远比较不相等。
    """
    return "\n".join(
        line for line in re.split(r"\r\n|\r|\n",
                                  content.strip(" \t\r\n\ufeff"))
        if not re.match(r"(?m)(?<=<!-- (IDEA|ARTIFACT):(START|END) -->)[ \t\ufeff]*", line)
    ).strip(" \t\n\ufeff")
