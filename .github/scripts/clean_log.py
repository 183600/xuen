#!/usr/bin/env python3
"""clean_log.py —— CI 日志净化器：把子进程输出清理成适合 Actions 日志的纯文本。

解决「Continuous Loop 日志乱码」的三类来源：
1. ANSI 转义序列（颜色 / 光标控制 / OSC 标题 / 隐藏光标等）；
2. 除 \\n、\\t 之外的控制字符（含 \\r 进度刷新、DEL、其它 C0 控制符）；
3. 非 UTF-8 字节 —— 按 U+FFFD（�）替换，而不是原样打进日志变成乱码。

流式处理（4KB 分块 + 增量解码），可直接挂在长命令的管道上，例如：

    opencode run "..." 2>&1 | python3 .github/scripts/clean_log.py

跨块边界的多字节 UTF-8 字符由增量解码器处理；跨块边界的 ANSI
转义序列由尾部携带（carry）缓冲处理，不会被撕成乱码。
"""
from __future__ import annotations

import codecs
import re
import sys

# ANSI/VT 转义序列：CSI（如 \x1b[31m、\x1b[2J、\x1b[?25l）、
# OSC（如 \x1b]0;title\x07）、以及其余两字节短转义（如 \x1bM）
_ANSI = re.compile(
    "\x1b(?:"
    r"\[[0-9;?]*[ -/]*[@-~]"
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|[@-Z\\-_]"
    ")"
)

_KEEP = ("\n", "\t")


def _incomplete_escape_start(text: str) -> int:
    """返回末尾「未写完的转义序列」的起始下标；没有则返回 -1。

    不能只按固定长度回溯：OSC 标题/CSI 参数可能任意长（跨多个 4KB 块），
    固定 16 字符的尾巴会把超长序列的半截漏成正文。这里用一个小状态机
    扫完整块，只在块尾停在转义序列中间时把从序列起点到块尾的内容留给
    下一块。含换行的 OSC/CSI 视为损坏而非跨块续写（否则一条没有结束符
    的转义可能吞掉后面的全部日志）。
    """
    i = 0
    n = len(text)
    seq_start = -1
    # 0=ground 1=ESC 2=CSI 3=OSC 4=其它字符串（DCS/SOS/PM/APC）
    state = 0
    while i < n:
        ch = text[i]
        if state == 0:
            if ch == "\x1b":
                seq_start = i
                state = 1
            i += 1
        elif state == 1:
            if ch == "[":
                state = 2
            elif ch == "]":
                state = 3
            elif ch in "PX^_":
                state = 4
            elif ch == "\x1b":
                # 前一个 ESC 没有合法后继：把它当作损坏的短转义，重新开始
                seq_start = i
            else:
                state = 0
            i += 1
        elif state == 2:
            o = ord(ch)
            if ch == "\x1b":
                seq_start = i
                state = 1
            elif o < 0x20 or o == 0x7f:
                # 控制字符出现在 CSI 中间：损坏，放弃续写
                state = 0
            elif 0x40 <= o <= 0x7e:
                state = 0
            i += 1
        else:
            if state == 3 and ch == "\x07":
                state = 0
                i += 1
            elif ch == "\x1b":
                if i + 1 < n:
                    if text[i + 1] == "\\":
                        state = 0
                        i += 2
                    else:
                        # ESC 中止字符串序列，本身开启新的转义
                        seq_start = i
                        state = 1
                        i += 1
                else:
                    i += 1
            elif ch in "\n\r":
                # 字符串序列里出现换行：按损坏处理，不能让半截 OSC
                # 把后续日志全部吞掉
                state = 0
                i += 1
            else:
                i += 1
    return -1 if state == 0 else seq_start


def _clean(text: str) -> str:
    """剥掉 ANSI 转义，再移除其余不可打印字符（换行/制表符保留）。"""
    text = _ANSI.sub("", text)
    return "".join(
        ch for ch in text if ch in _KEEP or (" " <= ch != "\x7f")
    )


def main() -> int:
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    carry = ""
    out = sys.stdout
    while True:
        chunk = sys.stdin.buffer.read(4096)
        if not chunk:
            break
        text = carry + decoder.decode(chunk)
        carry = ""
        # 块尾若是被截断的转义序列，留到下一块拼接后再匹配，
        # 避免半截 \x1b[... 漏进日志
        i = _incomplete_escape_start(text)
        if i != -1:
            carry = text[i:]
            text = text[:i]
        out.write(_clean(text))
        out.flush()
    # 冲掉增量解码器里残留的不完整 UTF-8 字节（替换成 U+FFFD）；
    # carry 里是没写完的转义序列，按「半截转义不进日志」直接丢弃。
    out.write(_clean(decoder.decode(b"", final=True)))
    out.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
