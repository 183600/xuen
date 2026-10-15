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
_MAX_ESCAPE_TAIL = 16  # 末尾可能是「未写完的转义序列」的最大长度


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
        i = text.rfind("\x1b")
        if i != -1 and len(text) - i < _MAX_ESCAPE_TAIL:
            carry = text[i:]
            text = text[:i]
        out.write(_clean(text))
        out.flush()
    if carry:
        out.write(_clean(carry))
        out.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
