#!/usr/bin/env python3
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

STATE_FILE = '/home/runner/work/xuen/xuen/ws2/research.md'
SCAFFOLD = '# 玄 · \n\n> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。\n\n<!-- IDEA:START -->\n（暂无）\n<!-- IDEA:END -->\n\n<!-- ARTIFACT:START -->\n（暂无）\n<!-- ARTIFACT:END -->\n'
NAMES = {"idea": "IDEA", "artifact": "ARTIFACT"}


_SECTION_MARKER_RE = re.compile(
    # ﻿：部分 Windows 编辑器会在标记行写入 BOM；仍应识别为区块标记
    r"(?m)^[ \t\ufeff]*(<!-- (IDEA|ARTIFACT):(START|END) -->)[ \t\ufeff]*\r?$"
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
        r"(?m)^[ \t\ufeff]*(?:" + re.escape(s) + "|" + re.escape(e) + r")[ \t\ufeff]*\r?$"
    )

    def clean(seg):
        # 只删除独占整行的标记，行内提及的标记文本是普通内容，必须保留
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
    return content.replace("\r\n", "\n").replace("\r", "\n").strip(" \t\n\ufeff")


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
            cleaned = "\n".join(
                line for line in content.strip().strip("\n").splitlines()
                if not _SECTION_MARKER_RE.match(line)
            ).strip(" \t\n\ufeff")
            body = "\n" + cleaned + "\n"
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
                    (candidate[a + len(s): b - len(e)].strip("\n")
                     for a, b in _spans(candidate) if candidate.startswith(s, a)),
                    None,
                )
                if back != cleaned:
                    # 与模块实现一致：舍弃刚插入的区块（prefix/suffix 已按
                    # 原有有效区块清好），把新区块放到文件开头
                    candidate = f"{s}{body}{e}\n\n" + (prefix + suffix).lstrip("\n")
                text = candidate
            else:  # 标记缺失/错乱：清除该区块所有残留标记，再追加一对干净的。
                # 与 if 分支同理：落在其他有效区块区间内的标记字面量是该区块的
                # 合法内容，必须原样保留，不能全局 replace 误删
                text = _strip_stray(text, spans, 0, s, e)
                candidate = text.rstrip("\n") + f"\n\n{s}{body}{e}\n"
                back = next(
                    (candidate[a + len(s): b - len(e)].strip("\n")
                     for a, b in _spans(candidate) if candidate.startswith(s, a)),
                    None,
                )
                if back != cleaned:
                    # 极端场景：其他有效区块内部「受保护」的同名孤立 START
                    # （本身无配对 END，是损坏残留）会抢先与新追加的 END
                    # 交叉配对。与模块实现一致：不再二次清除（交叉失效会
                    # 误删另一区块区间内的合法正文），直接把新区块放到
                    # 文件开头：START 在前必与自身 END 配对
                    candidate = f"{s}{body}{e}\n\n" + text.lstrip("\n")
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
