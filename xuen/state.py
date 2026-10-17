"""research.md（想法区 + 产物区）的维护，以及供外部 agent 使用的写入助手脚本。"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Tuple

SECTION_IDEA = "IDEA"
SECTION_ARTIFACT = "ARTIFACT"

HELPER_NAME = "write_section.py"


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


def ensure_state_file(path: Path, task: str) -> str:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(scaffold(task), encoding="utf-8")
    return path.read_text(encoding="utf-8")


def _first_span(text: str, name: str) -> tuple[int, int] | None:
    """区块「当前会被读出」的区间：第一个有效同名区块，无则 None。"""
    s = start_marker(name)
    for a, b in _section_spans(text):
        if text.startswith(s, a):
            return (a, b)
    return None


def _first_section(text: str, name: str) -> str | None:
    """第一个有效区块的内容；无有效区块返回 None。

    None 与空串必须区分：区块缺失/损坏时 get_section 返回空串，而写入
    修复路径（_preserve_other_section）需要知道区块原本是否可读。
    换行符统一规整为 \n：状态文件若以 CRLF 保存（Windows 编辑 /
    git autocrlf），逐行残留的 \r 会进入区块上报与提示词，
    也让 update_section_file 返回的 old 带杂质。
    """
    span = _first_span(text, name)
    if span is None:
        return None
    a, b = span
    s, e = start_marker(name), end_marker(name)
    content = text[a + len(s): b - len(e)]
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    # 标记行允许带首尾空白/BOM（见 _SECTION_MARKER）；这些属于
    # 标记行本身，不能算进区块内容，否则读出的内容会混入杂质
    return content.strip(" \t\n\ufeff")


def get_section(text: str, name: str) -> str:
    """提取区块内容：只认「有效配对且不落其他区块内部」的标记。

    落在其他有效区块区间内的同名标记字面量是该区块的合法内容（见
    _section_spans / _strip_stray_markers），必须跳过，否则读出的内容会
    跨越相邻区块；END 先于 START / 缺 END 等标记错乱则视为区块缺失，
    返回空串（由 update_section_file 负责修复）。
    """
    content = _first_section(text, name)
    return "" if content is None else content


# 区块标记必须独占一行（允许行首/行尾空白）。同一行内出现的标记文本是
# 普通内容（例如说明写入协议），不能参与区块配对。
_SECTION_MARKER = re.compile(
    # \ufeff：部分 Windows 编辑器会在标记行写入 BOM；仍应识别为区块标记
    r"(?m)^[ \t\ufeff]*(<!-- (IDEA|ARTIFACT):(START|END) -->)[ \t\ufeff]*\r?$"
)


def _section_spans(text: str) -> list:
    """所有有效区块（END 在 START 之后配对）的 (start, end) 区间，text 坐标。

    一个区块不能完整吞掉另一区块：当真实 END 被删掉、而相邻区块内容里
    恰好有同名 END 标记时，若直接按位置配对，替换外层区块就会把相邻区块
    一起删除。因此这里先收集候选，再剔除「完整包含另一候选区块」的伪配对。
    """
    marks = [  # (标记开始, 标记结束, 区块名, 是否START)
        (m.start(1), m.end(1), m.group(2), m.group(3) == "START")
        for m in _SECTION_MARKER.finditer(text)
    ]
    marks.sort(key=lambda m: m[0])

    candidates = []  # (区块名, start, end)
    for pos, _, nm, is_start in marks:
        if not is_start:
            continue
        match = next((m for m in marks if m[0] > pos and m[2] == nm and not m[3]),
                     None)
        if match is not None:
            candidates.append((nm, pos, match[1]))

    # 同一个 START/END 之间的重复 START 只是内容字面量，不是嵌套区块
    candidates = [
        candidate for candidate in candidates
        if not any(
            other != candidate and other[0] == candidate[0]
            and other[1] < candidate[1] < other[2]
            for other in candidates
        )
    ]
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
    _preserve_other_section 仍须保护它的标记行，否则更新另一区块时会把
    它的内容整体清掉。
    """
    marks = [
        (m.start(1), m.end(1), m.group(2), m.group(3) == "START")
        for m in _SECTION_MARKER.finditer(text)
    ]
    marks.sort(key=lambda m: m[0])
    candidates = []
    for pos, _, nm, is_start in marks:
        if nm != name or not is_start:
            continue
        match = next((m for m in marks if m[0] > pos and m[2] == nm
                      and not m[3]), None)
        if match is not None:
            candidates.append((pos, match[1]))
    return [candidate for candidate in candidates
            if not any(other != candidate and other[0] < candidate[0] < other[1]
                       for other in candidates)]


def _strip_stray_markers(segment: str, spans: list, seg_start: int,
                         s: str, e: str) -> str:
    """清除 segment 中「不落在任何有效区块区间内」的本区块标记字面量。

    spans / seg_start 均为原始 text 坐标。落在其他有效区块区间内的标记
    字面量是该区块的合法内容（如产物区记录了「请保留 <!-- IDEA:START -->」
    之类的写入协议），绝不能动——否则更新一个区块会悄悄删改另一个区块。
    """
    # 只匹配「本区块」（s/e 传入的区块）的标记：更新一个区块时不应删改散
    # 落在自由文本里的另一类区块标记字面量（那是其他区块的内容/残留）
    own_marker = re.compile(
        r"(?m)^[ \t\ufeff]*(?:" + re.escape(s) + "|" + re.escape(e) + r")[ \t\ufeff]*\r?$"
    )

    def clean(seg: str) -> str:
        # 只删除独占整行的标记；行内提及的标记文本是普通内容，必须保留
        return "\n".join(l for l in seg.split("\n")
                         if not own_marker.match(l))

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
    而失效的另一类区块残片，可能因此重新配对，抢在真实区块前面被
    get_section 读出，使另一区块读出的内容被悄悄改写。这里检出抢先
    配对的残片并清除其标记行（残片区间内的正文保留为自由文本），
    直到另一区块读出的内容回到更新前。
    """
    other = SECTION_ARTIFACT if name == SECTION_IDEA else SECTION_IDEA
    want = _first_section(original, other)
    if want is None:
        # 另一区块原本就不可读（缺失/损坏），没有需要保护的内容；
        # 修复过程中若它变得可读，属于顺带修复，不应回退
        return text
    s, e = start_marker(other), end_marker(other)
    for _ in range(64):
        if _first_section(text, other) == want:
            return text
        shadow = _first_span(text, other)
        if shadow is None:
            # 真实区块（want 的来源）始终有效且受保护，理论上不会走到
            return text
        # 保护除抢先配对残片外的所有有效区块（含真实区块与本轮更新的
        # 区块），只清除残片的标记行，绝不改动它们的正文
        protected = [(a, b) for a, b in _section_spans(text) if (a, b) != shadow]
        # 真实区块也可能因与更新的区块交叉配对、当前不是「有效区块」；
        # 它的候选配对区间同样要保护，否则上面的清除会把真实区块的标记
        # 行一并删掉，另一区块读出的内容从 want 变成空。
        # 重复 START 过滤保证这些候选区间不会覆盖 shadow 的标记行
        protected += [p for p in _paired_spans(text, other) if p != shadow]
        text = _strip_stray_markers(text, protected, 0, s, e)
    return text


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
    剥离标记行后，首/尾行可能残留空白或 BOM（如内容以标记行开头，
    紧随其后的正文行带缩进）：get_section/_first_section 读出时同样
    会剥掉这些字符，这里必须用同一套规整，否则返回的新内容与文件
    实际可读内容不一致，回读校验也失去意义。
    比较「区块内容是否相同」的调用方（如轮次守卫的心跳/还原判定）
    必须用本函数规整后再比较，否则含标记字面量的区块在落盘规整后
    永远比较不相等。
    """
    return "\n".join(
        line for line in content.strip().strip("\n").splitlines()
        if not _SECTION_MARKER.match(line)
    ).strip(" \t\n\ufeff")


def update_section_file(path: Path, name: str, content: str) -> Tuple[str, str]:
    """整体覆盖某个区块，返回 (旧内容, 新内容)。"""
    with _locked_state(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        original = path.read_text(encoding="utf-8") if path.exists() else scaffold("")
        text = original
        old = get_section(text, name)

        s, e = start_marker(name), end_marker(name)
        new = sanitize_section_content(content)
        body = "\n" + new + "\n"
        # 区块定位必须与 get_section/_section_spans 一致：跳过落在其他有效
        # 区块区间内的同名标记字面量，否则会替换到错误位置、破坏相邻区块
        spans = _section_spans(text)
        own = next(((a, b) for a, b in spans if text.startswith(s, a)), None)
        if own is not None:  # END 必须在 START 之后配对才算有效区块
            i_s, i_span_end = own
            # 区块内容若混入字面量标记，替换后区块外会留下孤立残留标记，
            # 因此前缀/后缀中本区块的孤立标记要清除；但落在其他有效区块
            # 区间内的标记字面量是该区块的内容，必须原样保留。
            # 重复的同名区块（第二对同样的 START/END）不能算「其他区块」：
            # 它永远不会被读取/更新，保护它的标记会让死数据永久残留
            other_spans = [(a, b) for a, b in spans if not text.startswith(s, a)]
            prefix = _strip_stray_markers(text[:i_s], other_spans, 0, s, e)
            suffix = _strip_stray_markers(text[i_span_end:], other_spans,
                                           i_span_end, s, e)
            candidate = prefix + s + body + e + suffix
            # 与 else 分支同理必须回读校验：其他有效区块内部「受保护」的
            # 同名孤立 START 会抢先与新写入的 END 交叉配对，导致刚写入的
            # 区块立即读不出来、且相邻区块一并失效。校验失败则在文件开头
            # 重建干净的区块（见下），绝不整段清除本区块标记。
            back = next(
                (candidate[a + len(s): b - len(e)].strip("\n")
                 for a, b in _section_spans(candidate)
                 if candidate.startswith(s, a)),
                None,
            )
            if back != new:
                # 不回退到「清除本区块所有标记再重建」：回读校验失败时本区块
                # 与另一区块会交叉失效，此时清除本区块标记会把另一区块区间
                # 内的合法正文也当成游离标记删掉。舍弃刚插入的区块
                # （prefix/suffix 已按原有有效区块清好），把新区块放到文件
                # 开头即可 —— 新写入的 START 在前，必与紧随其后的自身 END
                # 配对，留在后面的同名字面量标记不再能抢先配对
                candidate = f"{s}{body}{e}\n\n" + (prefix + suffix).lstrip("\n")
            text = candidate
        else:  # 标记缺失/错乱：清除该区块所有残留标记，再补一对干净的。
            # 与 if 分支同理：落在其他有效区块区间内的标记字面量是该区块的
            # 合法内容，必须原样保留，不能全局 replace 误删
            text = _strip_stray_markers(text, spans, 0, s, e)
            block = f"{s}{body}{e}"
            # 新区块插到另一区块的所有同名标记之前，而不是追加到文件末尾：
            # 若放末尾，另一区块内容里独立成行的同名 START 会把新区块的
            # END「抢走」交叉配对，使另一区块整块失效；_preserve_other_section
            # 只能清除另一区块自己的标记，无法修复被抢走的 END
            other = SECTION_ARTIFACT if name == SECTION_IDEA else SECTION_IDEA
            anchor = next((m.start(1) for m in _SECTION_MARKER.finditer(text)
                           if m.group(2) == other and m.group(3) == "START"),
                          None)
            if anchor is not None:
                line_start = text.rfind("\n", 0, anchor) + 1
                candidate = text[:line_start] + block + "\n\n" + text[line_start:]
            else:
                candidate = text.rstrip("\n") + f"\n\n{block}\n"
            # 回读校验必须用 None 哨兵：get_section 在区块缺失/交叉失效时
            # 返回 ''，与「写入空内容」无法区分，会漏掉需要修复的场景
            back = next(
                (candidate[a + len(s): b - len(e)].strip("\n")
                 for a, b in _section_spans(candidate)
                 if candidate.startswith(s, a)),
                None,
            )
            if back != new:
                # 极端场景：其他有效区块内部「受保护」的同名孤立 START（本身
                # 无配对 END，是损坏残留）会抢先与新插入的 END 交叉配对，
                # 导致新区块永远读不出来、且每次写入都追加出死数据。此时
                # 不再二次清除（交叉失效会误删另一区块区间内的合法正文），
                # 直接把新区块放到文件开头：START 在前必与自身 END 配对。
                # text 已在分支开头清过一次本区块的游离标记，无需重复清除
                candidate = f"{block}\n\n" + text.lstrip("\n")
            text = candidate

        # 清除本区块标记后，另一类区块原先失效的残片可能重新配对并抢先
        # 被读出；写盘前校验另一区块读出的内容未被本次更新悄悄改写
        text = _preserve_other_section(original, text, name)

        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            # 写入/替换失败时清掉半成品临时文件，避免在工作区残留垃圾。
            # 目标文件仍保持写入前状态，因此旧数据不会被破坏。
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return old, new


# ----------------------------------------------------------------
# 生成到工作区的独立小脚本：shell 模式下外部 agent 用它直接写文件，
# 从而实现「生成想法 / 生成产物」这两个工具（覆盖对应区块）。
# ----------------------------------------------------------------
HELPER_TEMPLATE = '''#!/usr/bin/env python3
"""xuen 区块写入助手（供外部 agent 通过 shell 调用）。

用法:
  cat new.md | python write_section.py idea       # 用 stdin 内容覆盖『想法区』
  cat new.md | python write_section.py artifact   # 用 stdin 内容覆盖『产物区』
  python write_section.py show                    # 打印整个状态文件
"""
import os
import re
import sys
from contextlib import contextmanager

try:
    # Windows 控制台常使用本地代码页（如 GBK）；xuen 的状态文件固定为 UTF-8，
    # show 子命令若按 locale 编码输出会出现乱码或 UnicodeEncodeError。
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

STATE_FILE = __STATE_FILE__
SCAFFOLD = __SCAFFOLD__
NAMES = {"idea": "IDEA", "artifact": "ARTIFACT"}


_SECTION_MARKER_RE = re.compile(
    # \ufeff：部分 Windows 编辑器会在标记行写入 BOM；仍应识别为区块标记
    r"(?m)^[ \\t\\ufeff]*(<!-- (IDEA|ARTIFACT):(START|END) -->)[ \\t\\ufeff]*\\r?$"
)


def _spans(text):
    """所有有效区块（END 在 START 之后配对）的 (start, end) 区间。

    标记必须独占一行；区块不能完整吞掉另一区块，否则损坏的外层 END 会
    与相邻区块内容中的字面量错误配对，并把相邻区块一起覆盖。"""
    marks = [
        (m.start(1), m.end(1), m.group(2), m.group(3) == "START")
        for m in _SECTION_MARKER_RE.finditer(text)
    ]
    marks.sort(key=lambda m: m[0])
    candidates = []
    for pos, _, nm, is_start in marks:
        if not is_start:
            continue
        match = next((m for m in marks if m[0] > pos and m[2] == nm and not m[3]),
                     None)
        if match is not None:
            candidates.append((nm, pos, match[1]))
    candidates = [
        candidate for candidate in candidates
        if not any(
            other != candidate and other[0] == candidate[0]
            and other[1] < candidate[1] < other[2]
            for other in candidates
        )
    ]
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
                invalid.update((i, j))
    return sorted((a, b) for i, (_, a, b) in enumerate(candidates)
                  if i not in invalid)


def _strip_stray(segment, spans, seg_start, s, e):
    """清除 segment 中不落在任何有效区块内的标记字面量；
    落在其他有效区块区间内的是该区块的合法内容，必须保留。"""
    # 与 xuen.state._strip_stray_markers 一致：只匹配本区块（s/e 传入的
    # 区块）的标记，不能误删自由文本中另一类区块的标记字面量
    own_marker = re.compile(
        r"(?m)^[ \\t\\ufeff]*(?:" + re.escape(s) + "|" + re.escape(e) + r")[ \\t\\ufeff]*\\r?$"
    )

    def clean(seg):
        # 只删除独占整行的标记，行内提及的标记文本是普通内容，必须保留
        return "\\n".join(l for l in seg.split("\\n")
                         if not own_marker.match(l))

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


def _paired_spans(text, name):
    """指定区块名的候选配对区间（START 配其后第一个同名 END）。

    与 _spans 的配对规则一致（含重复 START 过滤），但不做跨区块的交叉
    剔除：真实区块可能因与另一区块交叉配对而暂时失效，
    _preserve_other_section 仍须保护它的标记行。
    与 xuen.state._paired_spans 保持一致。"""
    marks = [
        (m.start(1), m.end(1), m.group(2), m.group(3) == "START")
        for m in _SECTION_MARKER_RE.finditer(text)
    ]
    marks.sort(key=lambda m: m[0])
    candidates = []
    for pos, _, nm, is_start in marks:
        if nm != name or not is_start:
            continue
        match = next((m for m in marks if m[0] > pos and m[2] == nm
                      and not m[3]), None)
        if match is not None:
            candidates.append((pos, match[1]))
    return [candidate for candidate in candidates
            if not any(other != candidate and other[0] < candidate[0] < other[1]
                       for other in candidates)]


def _first_span(text, name):
    """区块「当前会被读出」的区间：第一个有效同名区块，无则 None。"""
    s = f"<!-- {name}:START -->"
    for a, b in _spans(text):
        if text.startswith(s, a):
            return (a, b)
    return None


def _first_section(text, name):
    """第一个有效区块的内容；无有效区块返回 None（与空内容区分）。"""
    span = _first_span(text, name)
    if span is None:
        return None
    a, b = span
    s, e = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    content = text[a + len(s):b - len(e)]
    return content.replace("\\r\\n", "\\n").replace("\\r", "\\n").strip(" \\t\\n\\ufeff")


def _preserve_other_section(original, text, name):
    """保证另一类区块读出的内容与更新前（original）一致。

    更新一个区块只清除本区块的标记行；原先因与本区块标记「交叉配对」
    而失效的另一类区块残片，可能因此重新配对，抢在真实区块前面被读出，
    使另一区块读出的内容被悄悄改写。这里检出抢先配对的残片并清除其
    标记行（残片区间内的正文保留为自由文本），直到读出内容回到更新前。
    与 xuen.state._preserve_other_section 保持一致。"""
    other = "ARTIFACT" if name == "IDEA" else "IDEA"
    want = _first_section(original, other)
    if want is None:
        # 另一区块原本就不可读，没有需要保护的内容；若修复后变得可读，
        # 属于顺带修复，不应回退
        return text
    s, e = f"<!-- {other}:START -->", f"<!-- {other}:END -->"
    for _ in range(64):
        if _first_section(text, other) == want:
            return text
        shadow = _first_span(text, other)
        if shadow is None:
            # 真实区块始终有效且受保护，理论上不会走到
            return text
        # 保护除抢先配对残片外的所有有效区块，只清除残片的标记行
        protected = [(a, b) for a, b in _spans(text) if (a, b) != shadow]
        # 真实区块也可能因交叉配对、当前不是「有效区块」；它的候选配对
        # 区间同样要保护，避免把真实区块的标记行一并清除
        # （与 xuen.state._preserve_other_section 保持一致）
        protected += [p for p in _paired_spans(text, other) if p != shadow]
        text = _strip_stray(text, protected, 0, s, e)
    return text


@contextmanager
def _locked():
    """与 xuen.state.update_section_file 使用同一个 sidecar 锁，
    防止两个 agent/进程并发读-改-写时互相覆盖他人的更新。"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE + ".lock", "a+b") as lock:
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


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not argv or argv[0].lower() in ("help", "h"):
        print(__doc__.strip())
        return 0
    cmd = argv[0].lower()
    if cmd == "show":
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                sys.stdout.write(f.read())
        except OSError as e:
            print(f"状态文件读取失败：{e}", file=sys.stderr)
            return 1
        return 0
    if cmd not in NAMES:
        print(f"未知区块 {cmd!r}，可用: idea / artifact / show", file=sys.stderr)
        return 2
    name = NAMES[cmd]
    try:
        # stdin 固定按 UTF-8 解码：sys.stdin.read() 在本地代码页控制台
        # （典型为中文 Windows 的 GBK）会无法接收 UTF-8 管道内容。
        # errors="replace" 保证坏输入也只是降级为替换符，而非整段 traceback。
        content = sys.stdin.buffer.read().decode("utf-8", "replace")
        with _locked():
            s, e = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, encoding="utf-8") as f:
                    text = f.read()
            else:
                # 状态文件在运行过程中被删除时，与 xuen.state.update_section_file
                # 保持一致：从完整 scaffold 恢复，而不是只追加一个孤立区块
                text = SCAFFOLD
            original = text  # 更新前的文本（_preserve_other_section 比对用）
            # 与本区块 END 一样，任何独成一行的区块标记都会参与 _spans 配对：
            # 若作为内容原样写入，会被当成真实区块边界，导致相邻区块被截断
            # 甚至覆盖。行内提及不受影响；仅清除独占一行的标记。
            # 与 xuen.state.update_section_file 保持一致：剥掉标记行后首/尾行
            # 残留的空白/BOM 也要一并规整（get_section 读出时同样会剥掉），
            # 否则落盘内容与读取结果不一致
            cleaned = "\\n".join(
                line for line in content.strip().strip("\\n").splitlines()
                if not _SECTION_MARKER_RE.match(line)
            ).strip(" \\t\\n\\ufeff")
            body = "\\n" + cleaned + "\\n"
            # 区块定位须跳过落在其他有效区块区间内的同名标记字面量（那是该区块
            # 的合法内容），否则会替换到错误位置、破坏相邻区块
            spans = _spans(text)
            own = next(((a, b) for a, b in spans if text.startswith(s, a)), None)
            if own is not None:  # END 必须在 START 之后配对才算有效区块
                i_s, i_span_end = own
                # 区块外孤立残留标记要清除；但其他有效区块区间内的标记字面量
                # 是该区块的合法内容，必须原样保留。重复的同名区块不算「其他
                # 区块」：保护它的标记会让永远读不到/更新不到的死数据残留
                other = [(a, b) for a, b in spans if not text.startswith(s, a)]
                prefix = _strip_stray(text[:i_s], other, 0, s, e)
                suffix = _strip_stray(text[i_span_end:], other, i_span_end, s, e)
                candidate = prefix + s + body + e + suffix
                # 与 else 分支同理必须回读校验：其他有效区块内部「受保护」的
                # 同名孤立 START 会抢先与新写入的 END 交叉配对，导致刚写入的
                # 区块立即读不出来、且相邻区块一并失效。
                back = next(
                    (candidate[a + len(s): b - len(e)].strip("\\n")
                     for a, b in _spans(candidate) if candidate.startswith(s, a)),
                    None,
                )
                if back != cleaned:
                    # 与模块实现一致：舍弃刚插入的区块（prefix/suffix 已按
                    # 原有有效区块清好），把新区块放到文件开头
                    candidate = f"{s}{body}{e}\\n\\n" + (prefix + suffix).lstrip("\\n")
                text = candidate
            else:  # 标记缺失/错乱：清除该区块所有残留标记，再补一对干净的。
                # 与 if 分支同理：落在其他有效区块区间内的标记字面量是该区块的
                # 合法内容，必须原样保留，不能全局 replace 误删
                text = _strip_stray(text, spans, 0, s, e)
                block = s + body + e
                # 与模块实现一致：新区块插到另一区块的所有同名标记之前，
                # 避免另一区块内容里的孤立同名 START 抢走新区块的 END
                other = "ARTIFACT" if name == "IDEA" else "IDEA"
                anchor = next(
                    (m.start(1) for m in _SECTION_MARKER_RE.finditer(text)
                     if m.group(2) == other and m.group(3) == "START"),
                    None,
                )
                if anchor is not None:
                    line_start = text.rfind("\\n", 0, anchor) + 1
                    candidate = text[:line_start] + block + "\\n\\n" + text[line_start:]
                else:
                    candidate = text.rstrip("\\n") + "\\n\\n" + block + "\\n"
                back = next(
                    (candidate[a + len(s): b - len(e)].strip("\\n")
                     for a, b in _spans(candidate) if candidate.startswith(s, a)),
                    None,
                )
                if back != cleaned:
                    # 极端场景：其他有效区块内部「受保护」的同名孤立 START
                    # （本身无配对 END，是损坏残留）会抢先与新插入的 END
                    # 交叉配对。与模块实现一致：不再二次清除（交叉失效会
                    # 误删另一区块区间内的合法正文），直接把新区块放到
                    # 文件开头：START 在前必与自身 END 配对
                    candidate = block + "\\n\\n" + text.lstrip("\\n")
                text = candidate
            # 与 xuen.state.update_section_file 一致：清除本区块标记后，
            # 另一类区块原先失效的残片可能重新配对并抢先被读出；写盘前
            # 校验另一区块读出的内容未被本次更新悄悄改写
            text = _preserve_other_section(original, text, name)
            tmp = STATE_FILE + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(text)
                os.replace(tmp, STATE_FILE)
            except OSError:
                # 与 xuen.state.update_section_file 一致：写入/替换失败时
                # 清理半成品临时文件，避免外部 agent 重复调用后堆积垃圾。
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
    except (OSError, UnicodeDecodeError) as exc:
        print(f"状态文件写入失败：{exc}", file=sys.stderr)
        return 1
    print(f"[write_section] 已覆盖 {cmd} 区（{len(content)} 字符）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def write_helper_script(workspace: Path, state_path: Path) -> Path:
    helper = workspace / HELPER_NAME
    # 用 repr() 生成路径字面量：r-string 拼接在路径含连续双引号 /
    # 换行（POSIX 合法）时会生成语法损坏的脚本，repr() 总能安全转义
    content = (
        HELPER_TEMPLATE
        .replace("__SCAFFOLD__", repr(scaffold("")))
        .replace("__STATE_FILE__", repr(str(state_path.resolve())))
    )
    # 原子替换：写入途中被 kill 时不会留下语法损坏的半成品脚本，
    # 否则外部 agent 执行 write_section.py 会直接 SyntaxError
    tmp = helper.with_name(f"{helper.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, helper)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return helper
