"""领域词库：由外部 agent 生成、解析、持久化、随机抽样。

抽样只使用 random.sample，不调用任何 LLM。
"""
from __future__ import annotations

import os
import random
import re
from pathlib import Path
from typing import Callable, List, Optional

from .ui import ui

_CJK_NUMERALS = "一二三四五六七八九十百千万亿零〇两"
_NUMERAL_MARKS = "①-⑳⓪⑴-⒇⒈-⒛㈠-㈩㊀-㊉"
_BULLET = re.compile(
    r"^(?:\d+\s*[\.\．](?!\d)\s*"
    r"|\d+\s*[、）)]\s*"
    r"|（\d+）\s*"
    r"|\(\d+\)\s*"
    r"|\[\d+\]\s*"
    r"|[-*•·](?!\d)\s*"
    r"|[" + _CJK_NUMERALS + r"]+\s*[、）)]\s*"
    r"|（[" + _CJK_NUMERALS + r"]+）\s*"
    r"|[" + _NUMERAL_MARKS + r"]\s*)"
)
_EDGE_CHARS = "`*_^~'\"“”‘’「」『』《》〈〉【】〔〕〖〗.、 \ufeff"


def _is_dot_term(w: str) -> bool:
    """词首的点是否是术语本身的一部分（如 ".NET" / ".env" / ".gitignore"）。

    点通常只是列表/装饰残留（".**词**"、".「术语」"、"." * N），必须剥掉；
    但点后紧跟 ASCII 字母/下划线时它是域名、文件名、框架名的语义前缀。
    只认字母/下划线：".5" 仍是残片（点后是数字），继续按非词拒绝。
    """
    return (len(w) > 1 and w[0] == '.'
            and w[1].isascii() and (w[1].isalpha() or w[1] == '_'))


def _strip_leading_edges(w: str) -> str:
    """逐个剥词首边缘字符，但保留语义前导点（见 _is_dot_term）。

    不能直接用 lstrip(_EDGE_CHARS)：它会把 "..NET" 的点一起吃掉；
    逐个剥离能在剥到 ".NET" 时停下。
    """
    while w and w[0] in _EDGE_CHARS:
        if _is_dot_term(w):
            break
        w = w[1:]
    return w


_EMPHASIS_PAIR = re.compile(r"^([*~`]{1,3})(?=\S)(.+?)\1")
_UNDERSCORE_PAIR = re.compile(r"^(_+)(?=\S)(.+?)\1(?=$|[^\w])")
_UNDERSCORE_CLOSE = re.compile(r"_(?=$|[^\w])")
_QUOTE_PAIRS = (
    ('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("「", "」"),
    ("『", "』"), ("《", "》"), ("〈", "〉"), ("【", "】"), ("〔", "〕"),
    ("〖", "〗"),
)
_ANY_EMPHASIS_PAIR = re.compile(r"(?<![*~`])([*~`]{1,3})(?=\S)(.+?)\1(?![*~`])")


def _quote_pair_re(open_ch: str, close_ch: str) -> "re.Pattern":
    content = (r"(\S(?:[^" + re.escape(close_ch) + r"]*[^\s"
               + re.escape(close_ch) + r"])?)")
    return re.compile(re.escape(open_ch) + content + re.escape(close_ch))


_QUOTE_PAIR_RES = tuple(
    (open_ch, close_ch, _quote_pair_re(open_ch, close_ch))
    for open_ch, close_ch in _QUOTE_PAIRS
)
_EMPHASIS_CHARS = frozenset("*~`")
_ASCII_WORD_CHAR = re.compile(r"[0-9A-Za-z]")
_WORD_CHAR = re.compile(r"\w")
_PAIR_OPENERS = frozenset("*~`_" + "".join(open_ch for open_ch, _ in _QUOTE_PAIRS))
_PAIR_PARTICIPANTS = frozenset(
    "*~`_" + "".join(close_ch for _, close_ch in _QUOTE_PAIRS)
)


def _emph_repl(m: "re.Match") -> str:
    if (m.group(1) == "*" and m.start() > 0
            and _WORD_CHAR.match(m.string[m.start() - 1])):
        return m.group(0)
    return m.group(2)


def _quote_repl(m: "re.Match", open_ch: str) -> str:
    if (open_ch in "\"'" and m.start() > 0
            and _ASCII_WORD_CHAR.match(m.string[m.start() - 1])):
        return m.group(0)
    return m.group(1)


def _strip_pairs(w: str) -> str:
    """剥掉词中任意位置完整成对的装饰符（循环到不动点）。"""
    changed = True
    while changed:
        before = w
        if not _EMPHASIS_CHARS.isdisjoint(w):
            w = _ANY_EMPHASIS_PAIR.sub(_emph_repl, w)
        for open_ch, close_ch, rx in _QUOTE_PAIR_RES:
            if open_ch not in w or close_ch not in w:
                continue
            w = rx.sub(lambda m, _open=open_ch: _quote_repl(m, _open), w)
        changed = w != before
    return w


def _unwrap_pair(w: str) -> str:
    """剥掉成对装饰符：先剥词头（含被后续解释挡住的收尾符），
    再剥词中任意位置的完整成对（_strip_pairs）。

    循环处理嵌套（如 "「**术语**（解释）」"）；每次至少剥掉两个装饰符、
    严格变短，必然收敛。收尾符找不到配对时原样返回（如 "*args"、
    "C*代数"、"_private_var" 这类词中符号），交给后续的边缘字符剥离。
    """
    while True:
        m = _EMPHASIS_PAIR.match(w)
        if m:
            w = (m.group(2) + w[m.end():]).strip()
            continue
        m = None
        if w.startswith('_') and _UNDERSCORE_CLOSE.search(w):
            m = _UNDERSCORE_PAIR.match(w)
        if m:
            w = (m.group(2) + w[m.end():]).strip()
            continue
        for open_ch, close_ch in _QUOTE_PAIRS:
            if not w.startswith(open_ch):
                continue
            rest = w[len(open_ch):]
            if not rest or rest[0].isspace():
                continue
            end = rest.find(close_ch)
            if end < 0:
                continue
            tail = rest[end + len(close_ch):]
            if tail[:1].isalnum() or tail.startswith('_'):
                continue
            w = (rest[:end] + tail).strip()
            break
        else:
            stripped = _strip_pairs(w)
            if stripped == w:
                return w
            w = stripped


_PURE_NUMBER = re.compile(r"^[+-]?\d+(?:[.．]\d+)?$")
_CJK_INDEX = re.compile("^[" + _CJK_NUMERALS + "]+$")


def _is_plain_index(t: str) -> bool:
    """词段是否只是整数/汉字数字序号（小数除外）。

    "_PURE_NUMBER" 也会匹配 "3.14" / "2.5"：混在术语列表里的真实小数
    术语不能被当序号丢弃（"卷积、3.14、池化" -> "卷积、池化"），
    "3.14、2.718" 这类纯小数列表同样是真实术语列表，不能被整行丢弃
    规则误伤。因此段级与整行判定统一排除含小数点的值。
    """
    t = t.strip()
    if not t:
        return False
    if _CJK_INDEX.match(t):
        return True
    return bool(_PURE_NUMBER.match(t)) and "." not in t and "．" not in t


_HAS_WORD_CHAR = re.compile(r"[^\W_]", re.UNICODE)
_SEGMENT_SEP = re.compile(r"([、,，;；])")

def _clean_segment_head(core: str) -> str:
    """剥掉词段开头的成对装饰与序号/列表符号（不动点循环）。

    顺序与 _clean_once 一致：先按成对装饰剥（"**词**" -> "词"），再剥
    序号（"2. **词**" -> "**词**" -> "词"），反复到不动点。顺序反过来
    会让 _BULLET 的列表符先吃掉装饰头的一个 "*"（"**词**" -> "*词**"，
    收尾符失去配对成为残片）。
    """
    while True:
        nxt = _unwrap_pair(core)
        nxt = _unwrap_pair(_BULLET.sub('', nxt).strip())
        if nxt == core:
            return core
        core = nxt


def _is_list_index_sep(parts: List[str], i: int) -> bool:
    """序号段（parts[i]，纯数字或汉字数字）的相邻分隔符是否把它标记为列表序号。

    "1、卷积" 的中文顿号与 "1, 卷积" 的 ", "（分隔符后跟空白）是列表
    排版；而 "1,2-丙二醇"、"2,4-D" 里紧贴数字的 ASCII 逗号/分号是术语
    内部的连接符——列表序号极少这样写（常见写法 "1. " / "1) " / "1、"
    已由 _BULLET 与顿号规则处理），按序号丢弃会把术语悄悄截成另一个词。
    """
    if i + 1 < len(parts):
        sep, after = (parts[i + 1], parts[i + 2])
    else:
        sep, after = (parts[i - 1], parts[i])
    if sep in "、；，":
        return True
    return sep in ",;" and after[:1].isspace()


def _unwrap_segments(w: str) -> str:
    """对分隔符分开的每一段分别剥词头装饰/序号并清理两端。"""
    parts = _SEGMENT_SEP.split(w)
    cleaned = []
    for i in range(0, len(parts), 2):
        part = parts[i]
        core = part.strip()
        if not core:
            cleaned.append(part)
            continue
        lead = part[:len(part) - len(part.lstrip())]
        trail = part[len(part.rstrip()):]
        core = _clean_segment_head(core)
        while core and core[0] in _EDGE_CHARS:
            if _is_dot_term(core):
                break
            core = _clean_segment_head(core[1:])
        core = core.rstrip(_EDGE_CHARS).strip()
        cleaned.append(lead + core + trail)
    is_index = [_is_plain_index(t) for t in cleaned]
    has_word = any(t.strip() and not idx
                   for t, idx in zip(cleaned, is_index))
    index_only = all(idx for t, idx in zip(cleaned, is_index) if t.strip())
    list_format = all(
        _is_list_index_sep(parts, i)
        for i in range(0, len(parts), 2)
        if cleaned[i // 2].strip()
    )
    if not has_word and index_only and list_format:
        return ""
    out = []
    i = 0
    while i < len(parts):
        t = cleaned[i // 2]
        if i % 2 == 0 and has_word and is_index[i // 2]:
            if not _is_list_index_sep(parts, i):
                out.append(t)
                i += 1
                continue
            if i + 1 < len(parts):
                i += 2
            else:
                if out:
                    out.pop()
                i += 1
            continue
        out.append(t if i % 2 == 0 else parts[i])
        i += 1
    return "".join(out)


def _is_invalid_word(w: str) -> bool:
    """词是否为空、过长或明显不是术语（标题符/序号/无文字字符）。"""
    return (
        not w or len(w) > 60
        or w.startswith(("#", ">", "|", "="))
        or _is_plain_index(w)
        or _HAS_WORD_CHAR.search(w) is None
    )


def _clean_once(line: str) -> str | None:
    w = _unwrap_pair(line.strip())
    w = _unwrap_pair(_BULLET.sub("", w).strip())
    while w and w[0] in _EDGE_CHARS:
        if _is_dot_term(w):
            break
        rest = w[1:]
        if _PAIR_OPENERS.isdisjoint(rest) or _PAIR_PARTICIPANTS.isdisjoint(rest):
            w = _strip_leading_edges(w)
            break
        w = _unwrap_pair(rest)
    w = _unwrap_segments(w)
    w = w.rstrip(_EDGE_CHARS).strip()
    if _is_invalid_word(w):
        return None
    if "://" in w or "：//" in w:
        return None
    while "：" in w or ":" in w:
        for sep in ("：", ":"):
            if sep in w:
                head, _, _ = w.partition(sep)
                head = head.strip()
                if not head or len(head) > 30:
                    continue
                w = head
                break
        else:
            return None
    w = w.rstrip(".。,，;；!！?？ ")
    w = _strip_leading_edges(w).rstrip(_EDGE_CHARS).strip()
    if _is_invalid_word(w):
        return None
    return w


_MAX_CLEAN_LEN = 256
_LINE_SPLIT = re.compile(r"\r\n|\r|\n")


def _clean_line(line: str) -> Optional[str]:
    """清洗到不动点：单次清洗剥掉边缘字符后可能暴露出新的序号/标点/分隔符
    （如 "「9、注意力」" 先剥引号、下一轮才露出 "9、"），只清洗一次会让
    generate_words_shell 保存的词与 load_words 再次清洗得到的词不一致
    （词表随保存-读取漂移），且带引号的编号词会残留序号混进词库。
    每次有效清洗都严格变短，故循环必然收敛。"""
    if len(line) > _MAX_CLEAN_LEN:
        return None
    w = line
    for _ in range(64):
        nxt = _clean_once(w)
        if nxt is None:
            return None
        if nxt == w:
            return w
        w = nxt
    return w


def parse_word_lines(text: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for line in _LINE_SPLIT.split(text):
        word = _clean_line(line)
        if not word:
            continue
        key = word.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(word)
    return out


def load_words(path: Path) -> List[str]:
    if not path.exists():
        return []
    return parse_word_lines(path.read_text(encoding="utf-8-sig"))


def save_words(path: Path, wlist: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        tmp.write_text("\n".join(wlist) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        # 不止 OSError：写盘被 Ctrl+C / SystemExit 中断时同样要清掉
        # 带 PID 的半成品临时文件（与 state / rounds 的原子写口径一致），
        # 否则中断一次就在工作区留下一个只增不减的垃圾文件
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def sample_words(wlist: List[str], n: int) -> List[str]:
    """纯随机抽样，不调用 LLM。"""
    if n <= 0 or not wlist:
        return []
    return random.sample(wlist, min(n, len(wlist)))


def generate_words_shell(
    shell_agent,
    task: str,
    count: int,
    batch: int,
    info: Callable[[str], None] = ui.info,
    warn: Callable[[str], None] = ui.warn,
    stop: Optional[Callable[[], bool]] = None,
) -> List[str]:
    """通过外部 agent（如 opencode）分批生成领域词库。

    stop：可选的停止回调（如 TUI 按 q）。当前批次的 agent 会被外部
    kill，但若不检查停止标志，循环仍会为剩余批次继续拉起新 agent 进程。
    """
    wlist: List[str] = []
    seen = set()
    max_batches = max(2, count // max(batch, 1) + 3)
    for i in range(max_batches):
        if len(wlist) >= count:
            break
        if stop is not None and stop():
            info("收到停止请求，中断词库生成")
            break
        ask = min(batch, count - len(wlist) + 20)
        info(f"通过外部 agent 生成词库 {len(wlist)}/{count}（第 {i + 1} 批）")
        prompt = (
            f"请为研究方向「{task}」列出 {ask} 个紧密相关的术语/关键词。\n"
            "要求：每行一个词；不要编号、不要解释、不要输出任何多余内容；"
            "只输出词表本身。"
        )
        out = shell_agent.run(prompt) or ""
        if (getattr(shell_agent, "timed_out", False)
                or getattr(shell_agent, "returncode", 0)):
            if stop is not None and stop():
                break
            warn("词库生成批次执行失败（超时或非零退出），停止生成")
            break
        fresh = 0
        for word in parse_word_lines(out):
            key = word.casefold()
            if key not in seen:
                seen.add(key)
                wlist.append(word)
                fresh += 1
        if fresh == 0:
            warn("词表不再增长，提前结束收集")
            break
    return wlist[:count]
