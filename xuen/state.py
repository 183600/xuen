"""research.md（想法区 + 产物区）的维护，以及供外部 agent 使用的写入助手脚本。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

SECTION_IDEA = "IDEA"
SECTION_ARTIFACT = "ARTIFACT"

HELPER_NAME = "write_section.py"


def start_marker(name: str) -> str:
    return f"<!-- {name}:START -->"


def end_marker(name: str) -> str:
    return f"<!-- {name}:END -->"


def scaffold(task: str) -> str:
    return (
        f"# 玄 · {task}\n\n"
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


def get_section(text: str, name: str) -> str:
    """提取区块内容：只认「有效配对且不落其他区块内部」的标记。

    落在其他有效区块区间内的同名标记字面量是该区块的合法内容（见
    _section_spans / _strip_stray_markers），必须跳过，否则读出的内容会
    跨越相邻区块；END 先于 START / 缺 END 等标记错乱则视为区块缺失，
    返回空串（由 update_section_file 负责修复）。
    """
    s, e = start_marker(name), end_marker(name)
    for a, b in _section_spans(text):
        if text.startswith(s, a):
            return text[a + len(s): b - len(e)].strip("\n")
    return ""


def _section_spans(text: str) -> list:
    """所有有效区块（END 在 START 之后配对）的 (start, end) 区间，text 坐标。

    两类区块的标记必须按在文件中出现的全局位置顺序处理（不能按区块名
    一类一类地扫），否则「其他区块内容中的标记字面量」会被先扫的那类
    抢先配成假区块、把相邻区块整个吞掉；落在已确认区块区间内的标记
    只是该区块内容里的字面量（如产物区记录着写入协议），不参与配对。
    """
    marks = []  # (位置, 是否START, 区块名)
    for nm in (SECTION_IDEA, SECTION_ARTIFACT):
        sm, em = start_marker(nm), end_marker(nm)
        i = text.find(sm)
        while i >= 0:
            marks.append((i, True, nm))
            i = text.find(sm, i + 1)
        i = text.find(em)
        while i >= 0:
            marks.append((i, False, nm))
            i = text.find(em, i + 1)
    marks.sort(key=lambda m: m[0])
    spans = []
    for pos, is_start, nm in marks:
        if any(a <= pos < b for a, b in spans):
            continue  # 已确认区块内的标记字面量是内容，跳过
        if not is_start:
            continue  # 孤立 END
        em = end_marker(nm)
        b = text.find(em, pos + len(start_marker(nm)))
        if b < 0:
            continue  # 缺 END 的孤立 START
        spans.append((pos, b + len(em)))
    return spans


def _strip_stray_markers(segment: str, spans: list, seg_start: int,
                         s: str, e: str) -> str:
    """清除 segment 中「不落在任何有效区块区间内」的本区块标记字面量。

    spans / seg_start 均为原始 text 坐标。落在其他有效区块区间内的标记
    字面量是该区块的合法内容（如产物区记录了「请保留 <!-- IDEA:START -->」
    之类的写入协议），绝不能动——否则更新一个区块会悄悄删改另一个区块。
    """
    out = []
    pos = 0
    for a, b in sorted(spans):
        lo = max(a - seg_start, 0)
        hi = min(b - seg_start, len(segment))
        if lo > pos:
            out.append(segment[pos:lo].replace(s, "").replace(e, ""))
        if hi > max(pos, lo):
            out.append(segment[max(pos, lo):hi])
        pos = max(pos, hi)
    if pos < len(segment):
        out.append(segment[pos:].replace(s, "").replace(e, ""))
    return "".join(out)


def update_section_file(path: Path, name: str, content: str) -> Tuple[str, str]:
    """整体覆盖某个区块，返回 (旧内容, 新内容)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else scaffold("")
    old = get_section(text, name)

    s, e = start_marker(name), end_marker(name)
    # 新内容里只需剥掉本区块的 END 字面量：它会让 _section_spans 提前配对、
    # 区块被截断。本区块的 START 与另一区块的标记字面量写入后都落在有效
    # 区块区间内，是该区块的合法内容（如产物区记录着「请保留
    # <!-- IDEA:START -->」的写入协议），一律剥掉会悄悄删改区块内容
    new = content.strip().strip("\n").replace(e, "")
    body = "\n" + new + "\n"
    # 区块定位必须与 get_section/_section_spans 一致：跳过落在其他有效
    # 区块区间内的同名标记字面量，否则会替换到错误位置、破坏相邻区块
    spans = _section_spans(text)
    own = next(((a, b) for a, b in spans if text.startswith(s, a)), None)
    if own is not None:  # END 必须在 START 之后配对才算有效区块
        i_s, i_span_end = own
        # 区块内容若混入字面量标记，替换后区块外会留下孤立残留标记，
        # 因此前缀/后缀中本区块的孤立标记要清除；但落在其他有效区块
        # 区间内的标记字面量是该区块的内容，必须原样保留
        prefix = _strip_stray_markers(text[:i_s], spans, 0, s, e)
        suffix = _strip_stray_markers(text[i_span_end:], spans, i_span_end, s, e)
        text = prefix + s + body + e + suffix
    else:  # 标记缺失/错乱：清除该区块所有残留标记，再追加一对干净的。
        # 与 if 分支同理：落在其他有效区块区间内的标记字面量是该区块的
        # 合法内容，必须原样保留，不能全局 replace 误删
        text = _strip_stray_markers(text, spans, 0, s, e)
        text = text.rstrip("\n") + f"\n\n{s}{body}{e}\n"

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
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
import sys

STATE_FILE = __STATE_FILE__
NAMES = {"idea": "IDEA", "artifact": "ARTIFACT"}


def _spans(text):
    """所有有效区块（END 在 START 之后配对）的 (start, end) 区间。

    两类区块的标记必须按在文件中出现的全局位置顺序处理（否则其他区块
    内容里的标记字面量会被抢先配成假区块）；落在已确认区块区间内的标记
    只是该区块内容里的字面量，不参与配对。"""
    marks = []  # (位置, 是否START, 区块名)
    for nm in NAMES.values():
        sm = f"<!-- {nm}:START -->"
        em = f"<!-- {nm}:END -->"
        i = text.find(sm)
        while i >= 0:
            marks.append((i, True, nm))
            i = text.find(sm, i + 1)
        i = text.find(em)
        while i >= 0:
            marks.append((i, False, nm))
            i = text.find(em, i + 1)
    marks.sort(key=lambda m: m[0])
    spans = []
    for pos, is_start, nm in marks:
        if any(a <= pos < b for a, b in spans):
            continue  # 已确认区块内的标记字面量是内容，跳过
        if not is_start:
            continue  # 孤立 END
        sm = f"<!-- {nm}:START -->"
        em = f"<!-- {nm}:END -->"
        b = text.find(em, pos + len(sm))
        if b < 0:
            continue  # 缺 END 的孤立 START
        spans.append((pos, b + len(em)))
    return spans


def _strip_stray(segment, spans, seg_start, s, e):
    """清除 segment 中不落在任何有效区块内的标记字面量；
    落在其他有效区块区间内的是该区块的合法内容，必须保留。"""
    out = []
    pos = 0
    for a, b in sorted(spans):
        lo = max(a - seg_start, 0)
        hi = min(b - seg_start, len(segment))
        if lo > pos:
            out.append(segment[pos:lo].replace(s, "").replace(e, ""))
        if hi > max(pos, lo):
            out.append(segment[max(pos, lo):hi])
        pos = max(pos, hi)
    if pos < len(segment):
        out.append(segment[pos:].replace(s, "").replace(e, ""))
    return "".join(out)


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
    content = sys.stdin.read()
    name = NAMES[cmd]
    s, e = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    text = ""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            text = f.read()
    # 只剥本区块的 END 字面量（否则会提前配对、区块被截断）；本区块的
    # START 与另一区块的标记字面量落在有效区块区间内，是合法内容
    cleaned = content.strip().strip("\\n").replace(e, "")
    body = "\\n" + cleaned + "\\n"
    # 区块定位须跳过落在其他有效区块区间内的同名标记字面量（那是该区块
    # 的合法内容），否则会替换到错误位置、破坏相邻区块
    spans = _spans(text)
    own = next(((a, b) for a, b in spans if text.startswith(s, a)), None)
    if own is not None:  # END 必须在 START 之后配对才算有效区块
        i_s, i_span_end = own
        # 区块外孤立残留标记要清除；但其他有效区块区间内的标记字面量
        # 是该区块的合法内容，必须原样保留
        prefix = _strip_stray(text[:i_s], spans, 0, s, e)
        suffix = _strip_stray(text[i_span_end:], spans, i_span_end, s, e)
        text = prefix + s + body + e + suffix
    else:  # 标记缺失/错乱：清除该区块所有残留标记，再追加一对干净的。
        # 与 if 分支同理：落在其他有效区块区间内的标记字面量是该区块的
        # 合法内容，必须原样保留，不能全局 replace 误删
        text = _strip_stray(text, spans, 0, s, e)
        text = text.rstrip("\\n") + f"\\n\\n{s}{body}{e}\\n"
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, STATE_FILE)
    print(f"[write_section] 已覆盖 {cmd} 区（{len(content)} 字符）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def write_helper_script(workspace: Path, state_path: Path) -> Path:
    helper = workspace / HELPER_NAME
    # 用 repr() 生成路径字面量：r-string 拼接在路径含连续双引号 /
    # 换行（POSIX 合法）时会生成语法损坏的脚本，repr() 总能安全转义
    helper.write_text(
        HELPER_TEMPLATE.replace("__STATE_FILE__", repr(str(state_path.resolve()))),
        encoding="utf-8",
    )
    return helper
