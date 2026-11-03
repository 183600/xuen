"""research.md（想法区 + 产物区）的维护，以及供外部 agent 使用的写入助手脚本。"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Tuple, List

from .atomic_io import atomic_write_text
from .core import (
    _atomic_write_text, _first_span, _first_section, _normalize_newlines,
    _read_back_section, _section_marks, _section_spans, _paired_spans,
    _strip_stray, _strip_stray_markers, _preserve_other_section, _section_marker_regex,
    _SECTION_MARKER_RE, _drop_nested_starts, _paired_spans
)

SECTION_IDEA = "IDEA"
SECTION_ARTIFACT = "ARTIFACT"
HELPER_NAME = "write_section.py"

def _atomic_write_text(path: Path, text: str, *, newline=None) -> None:
    """写入 UTF-8 文本并原子替换目标；任何中断都不留临时半成品。"""
    atomic_write_text(path, text, newline=newline)

def start_marker(name: str) -> str:
    return f"<!-- {name}:START -->"

def end_marker(name: str) -> str:
    return f"<!-- {name}:END -->"

def scaffold(task: str) -> str:
    # 标题必须保持单行：任务文本若引入换行，可能被误写成区块标记并污染解析
    title_task = task.replace("\r", " ").replace("\n", " ")
    return (
        f"# 玄 · {title_task}\n\n"
        "> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，"
        "每次写入会整体覆盖对应区块。编辑时请保留标记行。\n\n"
        f"{start_marker(SECTION_IDEA)}\n（暂无）\n{end_marker(SECTION_IDEA)}\n\n"
        f"{start_marker(SECTION_ARTIFACT)}\n（暂无）\n{end_marker(SECTION_ARTIFACT)}\n"
    )

def read_state_file(path: Path) -> str:
    """严格读取状态文件；非法 UTF-8 时按替换符降级并立即回写修复。
    
    与 update_section_file / 写入助手同一口径：非法 UTF-8（外部编辑器按
    本地编码保存 / agent 写盘事故）按替换符降级读取，并把坏字节变
    U+FFFD 后原子回写。所有读取路径（启动预检、守卫、研究循环的提示词/
    展示）共用本函数，一个坏字节才不会让某条路径把整份状态当成空/缺失：
    提示词里区块变「（空）」会让 agent 丢掉全部跨轮上下文，守卫则会把
    整轮产物当 skipped 丢弃。
    文件不存在等 OSError 原样抛出，由调用方决定是建 scaffold 还是按
    空状态降级。加锁后重读：若并发实例/写入助手已修复，直接复用其结果。
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        with _locked_state(path):
            try:
                return path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # newline="" 保留原始 CRLF/CR 字节：Path.read_text 会做通用
                # 换行转换，回写时把整个文件的混合行尾悄悄改成 LF（POSIX）
                # 或 CRLF（Windows），与 update_section_file 已修复的同类
                # 问题一致。返回值仍按普通读取路径规整为 \n，调用方看到的
                # 文本语义不变。
                raw_text = _read_replacing_errors(path)
                text = _normalize_newlines(raw_text)
                # 写盘失败或中断时由 _atomic_write_text 清掉半成品临时
                # 文件；OSError 照常抛给调用方（此时目录不可写，helper
                # 也建不出来）。
                _atomic_write_text(path, raw_text, newline="")
                return text

def ensure_state_file(path: Path, task: str) -> str:
    # 初始化也必须与 update_section_file / 写入助手共用锁：exists() 与
    # 实际写入之间若另一个实例已创建并更新了状态，裸写 scaffold 会把
    # 对方的研究进度整份覆盖掉。锁内只补建缺失文件，已存在时绝不重写。
    with _locked_state(path):
        if not path.exists():
            _atomic_write_text(path, scaffold(task))
    return read_state_file(path)

def _first_span(text: str, name: str) -> tuple[int, int] | None:
    s = start_marker(name)
    for a, b in _section_spans(text):
        if text.startswith(s, a):
            return (a, b)
    return None

def _normalize_newlines(text: str) -> str:
    """把 CRLF / CR 统一为 LF，供区块内容与读回文本使用。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")

def _read_replacing_errors(path: Path) -> str:
    """按 UTF-8 读取，坏字节降级为替换符；保留原始换行便于原样回写。"""
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()

def get_section(text: str, name: str) -> str:
    """提取区块内容：只认「有效配对且不落其他区块内部」的标记。
    
    落在其他有效区块区间内的同名标记字面量是该区块的合法内容（见
    _section_spans / _strip_stray_markers），必须跳过，否则读出的内容会
    跨越相邻区块；END 先于 START / 缺 END 等标记错乱则视为区块缺失，
    返回空串（由 update_section_file 负责修复）。
    """
    content = _first_section(text, name)
    return "" if content is None else content

def _section_spans(text: str) -> list:
    """所有有效区块（END 在 START 之后配对）的 (start, end) 区间，text 坐标。
    
    一个区块不能完整吞掉另一区块：当真实 END 被删掉、而相邻区块内容里
    恰好有同名 END 标记时，若直接按位置配对，替换外层区块就会把相邻区块
    一起删除。因此这里先收集候选，再剔除「完整包含另一候选区块」的伪配对。
    """
    marks = _section_marks(text)
    candidates = []  # (区块名, start, end)
    for pos, _, nm, is_start in marks:
        if not is_start:
            continue
        match = next((m for m in marks if m[0] > pos and m[2] == nm and not m[3]),
                     None)
        if match is not None:
            candidates.append((nm, pos, match[1]))

    candidates = _drop_nested_starts(candidates)
    # 区块不允许包含另一个完整区块：这通常说明外层候选的 END 落在相邻
    # 区块内容里（典型场景是外层真实 END 被删除），优先保留内层的真实
    # 相邻区块。若内层同名区块在外层候选之外（此前或此后）已有一个完整
    # 候选，内层标记则只是内容中独立成行的字面量，保留外层。
    invalid = set()
    for i, candidate in enumerate(candidates):
        for j, other in enumerate(candidates):
            if candidate[0] == other[0]:
                continue
            if candidate[1] < other[1] and other[2] <= candidate[2]:
                inner_elsewhere = any(
                    prior != other and prior[0] == other[0]
                    and (prior[2] <= candidate[1]
                         or prior[1] >= candidate[2])
                    for prior in candidates
                )
                invalid.add(j if inner_elsewhere else i)
            elif candidate[1] < other[1] < candidate[2] < other[2]:
                # 两类区块交叉嵌套，无法判断哪个 END 可信，均拒绝后走修复路径
                invalid.update((i, j))
    return sorted((a, b) for i, (_, a, b) in enumerate(candidates)
                  if i not in invalid)


def _paired_spans(text: str, name: str) -> list:
    """指定区块名的候选配对区间（START 配其后第一个同名 END）。
    
    与 _section_spans 的配对规则一致（含重复 START 过滤），但不做跨区块
    的交叉剔除：真实区块可能因与另一区块交叉配对而暂时失效，
    _preserve_other_section 仍须保护它的标记行。
    """
    marks = _section_marks(text)
    candidates = []
    for pos, _, nm, is_start in marks:
        if nm != name or not is_start:
            continue
        match = next((m for m in marks if m[0] > pos and m[2] == nm and not m[3]),
                     None)
        if match is not None:
            candidates.append((nm, pos, match[1]))

    return [(a, b) for _, a, b in _drop_nested_starts(candidates)]


def _strip_stray_markers(segment: str, spans: list, seg_start: int,
                          s: str, e: str) -> str:
    """清除 segment 中「不落在任何有效区块区间内」的标记字面量。
    
    spans / seg_start 均为原始 text 坐标。落在其他有效区块区间内的标记
    字面量是该区块的合法内容，必须保留。"""
    # 与 xuen.state._strip_stray_markers 一致：只匹配本区块（s/e 传入的
    # 区块）的标记，不能误删自由文本中另一类区块的标记字面量
    own_marker = re.compile(
        r"[ \t\ufeff]*(?:" + re.escape(s) + "|" + re.escape(e) + r")[ \t\ufeff]*"
    )

    def clean(seg: str) -> str:
        # 只删除独占整行的标记；行内提及的标记文本是普通内容，必须保留。
        # 按 CR/LF/CRLF 拆分并逐行保留原有行尾，与 xuen.state 一致：
        # CR-only 文件里的孤立标记同样会被清掉。
        parts = re.split(r"(\r\n|\r|\n)", seg)
        out = []
        final_removed_without_ending = False
        for i in range(0, len(parts), 2):
            line = parts[i]
            ending = parts[i + 1] if i + 1 < len(parts) else ""
            if own_marker.fullmatch(line):
                if not ending and i == len(parts) - 1:
                    final_removed_without_ending = True
                continue
            out.append(line)
            out.append(ending)
        cleaned = "".join(out)
        if final_removed_without_ending and cleaned.endswith(
                ("\r\n", "\r", "\n")):
            cleaned = cleaned[:-2] if cleaned.endswith("\r\n") else cleaned[:-1]
        return cleaned

    out = []
    pos = 0
    for a, b in sorted(spans):
        lo = max(a - seg_start, 0)
        hi = min(b - seg_start, len(segment))
        if lo > pos:
            out.append(clean(segment[pos:lo]))
        if hi > max(pos, lo):
            out.append(segment[max(pos, lo):hi])
        pos = max(pos, hi)
    if pos < len(segment):
        out.append(clean(segment[pos:]))
    return "".join(out)


def _preserve_other_section(original: str, text: str, name: str) -> str:
    """保证另一类区块读出的内容与更新前（original）一致。
    
    更新一个区块只清除本区块的标记行；原先因与本区块标记「交叉配对」
    而失效的另一类区块残片，可能因此重新配对，抢在真实区块前面被读出，
    使另一区块读出的内容被悄悄改写。这里检出抢先配对的残片并清除其
    标记行（残片区间内的正文保留为自由文本），直到读出内容回到更新前。
    与 xuen.state._preserve_other_section 保持一致。"""
    other = SECTION_ARTIFACT if name == SECTION_IDEA else SECTION_IDEA
    want = _first_section(original, other)
    if want is None:
        # 另一区块原本就不可读（缺失/损坏），没有需要保护的内容；
        # 修复过程中若它变得可读，属于顺带修复，不应回退
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
        # 真实区块也可能因与更新的区块交叉配对、当前不是「有效区块」；
        # 它的候选配对区间同样要保护，避免把真实区块的标记行一并清除
        # （与 xuen.state._preserve_other_section 保持一致）
        protected += [p for p in _paired_spans(text, other) if p != shadow]
        text = _strip_stray(text, protected, 0, s, e)
    raise ValueError("状态文件区块标记嵌套过深，无法安全更新")


@contextmanager
def _locked_state(path: Path) -> Iterator[None]:
    """跨进程串行化 research.md 的读-改-写。
    
    os.replace 只能保证单个写入不撕裂文件，不能防止两个进程同时基于旧
    内容修改后互相覆盖。内部更新与生成的 write_section.py 使用同一个
    sidecar 锁文件，保证两种入口不会丢更新。锁文件独立于数据文件，因此
    Windows 的强制锁也不会与 os.replace 冲突。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with open(lock_path, "a+b") as lock:
        if os.name == "nt":
            import msvcrt
            # msvcrt 的锁操作针对当前文件位置；空文件锁定会报参数错误
            lock.seek(0)
            if not lock.read(1):
                lock.write(b"\0")
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
        if not _SECTION_MARKER_RE.match(line)
    ).strip(" \t\n\ufeff")


def _read_back_section(candidate: str, name: str) -> str | None:
    """按 get_section 的规则回读 candidate 中指定区块，供写盘后校验。
    
    返回 None 表示区块缺失或交叉失效（区别于写入空内容）。
    """
    s, e = start_marker(name), end_marker(name)
    back = next(
        (candidate[a + len(s): b - len(e)].strip("\r\n")
         for a, b in _section_spans(candidate)
         if candidate.startswith(s, a)),
        None,
    )
    return None if back is None else _normalize_newlines(back)
