"""领域词库：由外部 agent 生成、解析、持久化、随机抽样（抽样这一步绝不调用任何 LLM）。"""
from __future__ import annotations

import os
import random
import re
from pathlib import Path
from typing import Callable, List, Optional

from .ui import ui

# 序号也要兼容全角/半角括号形式：1. / 2、 / 3) / 4）/ （5）/ (6) ——
# 中文 LLM 常用全角，英文/ markdown 列表常用半角括号；(123) 前缀几乎
# 不会是真实术语，序号必须剥掉，否则 "(6) LAMB" 会原样混进词库；
# 小数点后跟数字时是真实术语（如 "0.5倍速"、"2.5D"），不能当序号剥掉；
# 叠层编号（如 "1、2、词"、"1)2) 词"）要求 ) 、 ）等不带数字保护，
# 否则第一层编号被保护挡下、整个编号残留词中，故仅对点号加 (?!\d)。
# 每次只剥一层：剥多层要交给 _clean_line 的不动点循环，否则 "- **词**（解释）"
# 会被一次性连开头的 "**" 一起当序号剥掉（"[-*•·]\s*" 可匹配零个空格，
# 连续星号被当成多个列表符号），成对装饰符的收尾符就成了残片
_BULLET = re.compile(
    r"^(?:\d+\s*[\.\．](?!\d)\s*|\d+\s*[、）)]\s*|（\d+）\s*|\(\d+\)\s*|\[\d+\]\s*|[-*•·]\s*)")

# 词形两端要剥掉的引号/书名号/装饰符（含中文成对括号，
# 否则 "「`词`," 之类会留下 '「`词' 残片混进词库；
# 点号也在其中：剥序号后可能残留 ". 词" 残片，如 "1.. 词"）
# \ufeff：外部 agent / Windows 编辑器常在行首带 BOM；不剥离的话
# "\ufeff词" 会原样混进词库，且 load_words 用 utf-8-sig 读取时又把
# 文件首个 BOM 剥掉，造成同一条词在保存与读取之间静默漂移；
# 仅剩 BOM 的行（或 "\ufeff#注释"）也会绕过空行/注释过滤
_EDGE_CHARS = "`*_^~'\"“”‘’「」『』《》〈〉【】〔〕〖〗.、 \ufeff"

# 成对装饰符：markdown 强调/代码（同字符成对，可叠 1~3 个）与中英文引号
# （开闭不同字符）。LLM 常把词形装饰后再跟解释，如 "- **术语**（解释）"；
# 此时收尾装饰符被 "（解释）" 挡在串尾之外，只剥两端的旧逻辑会留下
# "术语**（解释）" 残片混进词库（再被当作灵感词拼进提示词）。
# 强调对的收尾后仍可紧跟单词字符（markdown 里 "**C**语言" 是加粗 C 加
# "语言"），引号对则要求收尾后是空白/行尾/非单词字符，避免把
# "“x”与“y”" 这类连续引语误并成 "x与“y”"。
# 下划线单独处理：markdown 规定 "_" 不能在词中配对（CommonMark 的
# 左右侧翼规则），"_private_var" 是含下划线的术语而非斜体。若无此限制，
# 词中下划线会被当作收尾符吃掉（"_private_var" → "privatevar"），
# 而旧版只剥两端时恰好保留 "_private_var" 原形，属回归。
_EMPHASIS_PAIR = re.compile(r"^([*~`]{1,3})(?=\S)(.+?)\1")
_UNDERSCORE_PAIR = re.compile(r"^(_+)(?=\S)(.+?)\1(?=$|[^\w])")
_QUOTE_PAIRS = (
    ('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"),
    ("「", "」"), ("『", "』"), ("《", "》"), ("〈", "〉"),
    ("【", "】"), ("〔", "〕"), ("〖", "〗"),
)

# 词中任意位置的成对装饰符：只剥词头时，被连接词/空格隔开的第二组装饰
# （"**前置**和**后置**"、"“x”与“y”"）会把收尾符留给整行 rstrip 当边缘
# 字符剥掉、开头装饰符却留在词中（"前置和**后置"），残片随词库进入每轮
# 提示词。这里用非贪婪匹配找出所有完整成对（同字符、同数量）的装饰并连
# 配对一起剥；没有配对的词中符号（"2**10"、"C*代数"、"_private_var"）
# 不匹配、原样保留。单星号加 (?<!\w) 保护：词中的 a*b*c、C*代数与D*几何
# 是乘法/星号记号而非 markdown 斜体；成对的双星号/反引号等仍照剥。
_ANY_EMPHASIS_PAIR = re.compile(
    r"(?<![*~`])([*~`]{1,3})(?=\S)(.+?)\1(?![*~`])")
# 引号对内层要求首尾都是非空白字符（空引号 ""、纯空白引号不剥）。
# ASCII 单/双引号以回调再要求开引号不在 ASCII 字母数字之后：
# "don't"、"O'Reilly"、英寸号 6" 里的引号不是成对装饰。
_QUOTE_PAIR_RES = tuple(
    (open_ch, close_ch,
     re.compile(re.escape(open_ch) + r"(\S(?:.*?\S)?)" + re.escape(close_ch)))
    for open_ch, close_ch in _QUOTE_PAIRS)
_ASCII_WORD_CHAR = re.compile(r"[0-9A-Za-z]")
_WORD_CHAR = re.compile(r"\w")


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
        w = _ANY_EMPHASIS_PAIR.sub(_emph_repl, w)
        for open_ch, close_ch, rx in _QUOTE_PAIR_RES:
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
            if tail[:1].isalnum() or tail.startswith("_"):
                continue
            w = (rest[:end] + tail).strip()
            break
        else:
            stripped = _strip_pairs(w)
            if stripped == w:
                return w
            w = stripped


# 纯数字（含 "3.14" / "2.5" 这类小数，isdigit() 拦不住）不是词；
# 但 "0.5倍速"、"2.5D" 这类含非数字字符的术语必须保留，故用整串匹配。
# 小数点同时接受全角 ．：中文 LLM 输出 "３．１４" 时 \d 能匹配全角数字、
# 小数点却不能只认半角，否则全角小数会漏进词库（与 _BULLET 保持一致）
_PURE_NUMBER = re.compile(r"^[+-]?\d+(?:[.．]\d+)?$")

# 纯符号/装饰行（如 "///"、"()"、"[]"、"<>"、"——"、"…"）不是术语：
# 词必须至少含一个字母/数字/CJK 字符（[^\W_] 即 Unicode 字母与数字），
# 否则 markdown 分隔线/括号/省略号之类的残片会混进词库，
# 再被当作灵感词展示并拼进外部 agent 的提示词
_HAS_WORD_CHAR = re.compile(r"[^\W_]", re.UNICODE)


# 同一行里用分隔符列出的多个术语可能各自带装饰头/收尾（LLM 常写
# "**卷积**、**池化**、**全连接**"、"*fast*, *slow*"）或各自的序号
# （"1. 卷积、2. 池化、3. 全连接"）：只从整行词头 unwrap / 剥序号
# 会只处理第一段，后面段的收尾被 rstrip(_EDGE_CHARS) 剥掉、序号与
# 装饰头却留在词中（"卷积、2. **池化"），残片随词库进入每轮提示词。
# 按分隔符分段、逐段剥（分隔符与原有空白原样保留）。
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
        nxt = _unwrap_pair(_BULLET.sub("", nxt).strip())
        if nxt == core:
            return core
        core = nxt


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
            core = _clean_segment_head(core[1:])
        # 段尾同理：中段的装饰收尾/序号残片不在整行末尾，
        # 整行 rstrip 碰不到（"1. 卷积**、2. 池化" 的 "*"）
        core = core.rstrip(_EDGE_CHARS).strip()
        cleaned.append(lead + core + trail)
    # 中文编号 "1、卷积、2、池化" 的序号分隔符与术语分隔符同为 "、"：
    # 分段后序号单独成段（"2"），_clean_segment_head 无处可剥。纯数字段
    # 不是术语（与 _PURE_NUMBER 拒绝整行纯数字一致）；只要列表里还有
    # 其他词段，就把纯数字段连同紧邻的分隔符一起丢弃。整个列表都是
    # 纯数字时保持原样，交给 _PURE_NUMBER 统一裁决，不在这里清空。
    has_word = any(t.strip() and not _PURE_NUMBER.match(t.strip())
                   for t in cleaned)
    out = []
    i = 0
    while i < len(parts):
        t = cleaned[i // 2]
        if i % 2 == 0 and has_word and t.strip() and _PURE_NUMBER.match(
                t.strip()):
            # 丢弃序号段与其后的分隔符（"卷积；2、池化" 保留 "；"）；
            # 序号段在末尾（"卷积、2"）时改丢它前面的分隔符
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


def _clean_once(line: str) -> str | None:
    # 行首与剥序号后各 unwrap 一次：行首覆盖 "**词** 解释"、"「词」（解释）"；
    # 剥序号覆盖 "- **词** 解释"（装饰头在序号后面才露出来）。unwrap 必须在
    # 剥边缘字符之前：装饰符本身也是边缘字符，剥边缘会把成对装饰头连同
    # 后面的空白一起吃掉、只剩收尾符残片
    w = _unwrap_pair(line.strip())
    w = _unwrap_pair(_BULLET.sub("", w).strip())
    # 边缘字符逐个剥、每剥一个就再试一次成对装饰符：一次性 strip 会把
    # ".**词**（解释）" 的 "." 和装饰头 "**" 一起吃掉，收尾符失去配对留在
    # 串中（"词**（解释）"）；逐个剥则能在装饰头露头时连收尾一起剥掉
    while w and w[0] in _EDGE_CHARS:
        w = _unwrap_pair(w[1:])
    # 分隔符后面的词段同样可能是装饰头（见 _unwrap_segments 说明）
    w = _unwrap_segments(w)
    w = w.rstrip(_EDGE_CHARS).strip()
    if not w or len(w) > 60:
        return None
    if (w.startswith(("#", ">", "|", "=")) or _PURE_NUMBER.match(w)
            or not _HAS_WORD_CHAR.search(w)):
        return None
    if "://" in w:
        # URL 不是灵感词；若交给下面按 ':' 截断，会把 "http"/"https"
        # 这类协议名误收进词库。
        return None
    while "：" in w or ":" in w:  # "词：解释"/"词:解释" 只留词
        for sep in ("：", ":"):
            if sep in w:
                head, _, _ = w.partition(sep)
                head = head.strip()
                # 尾部为空（如 "术语："）时仍应保留词头；词头非法则尝试下一个
                # 分隔符（如 "term：subterm: 解释"），两者都截不出合法词头才丢
                if not head or len(head) > 30:
                    continue
                w = head
                break
        else:
            # 含冒号但任何分隔符都截不出合法词头：整行是解释性文字，丢弃
            return None
    # 尾部标点剥除后，可能露出此前被标点挡住的引号/反引号
    # （如 "「`词`," → "词`"），需再剥一次，否则残片混进词库
    w = w.rstrip(".。,，;；!！?？ ")
    w = w.strip(_EDGE_CHARS).strip()
    # 冒号截断后词形已变（如 "12: 解释" → "12"、"()：解释" → "()"），
    # 需复查拦截条件，否则纯数字 / 纯符号 / 以 # > | = 开头的残片
    # 会混进词库
    if not w or len(w) > 60:
        return None
    if (w.startswith(("#", ">", "|", "=")) or _PURE_NUMBER.match(w)
            or not _HAS_WORD_CHAR.search(w)):
        return None
    return w


def _clean_line(line: str) -> Optional[str]:
    """清洗到不动点：单次清洗剥掉边缘字符后可能暴露出新的序号/标点/分隔符
    （如 "「9、注意力」" 先剥引号、下一轮才露出 "9、"），只清洗一次会让
    generate_words_shell 保存的词与 load_words 再次清洗得到的词不一致
    （词表随保存-读取漂移），且带引号的编号词会残留序号混进词库。
    每次有效清洗都严格变短，故循环必然收敛。"""
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
    for ln in text.splitlines():
        w = _clean_line(ln)
        if not w:
            continue
        key = w.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(w)
    return out


def load_words(path: Path) -> List[str]:
    if not path.exists():
        return []
    # 复用 parse_word_lines：清洗无效行并按 casefold 去重，
    # 否则文件中的重复词会扭曲 random.sample 的抽样分布。
    # utf-8-sig 剥掉 UTF-8 BOM：Windows 编辑器保存的 words.txt 常带 BOM，
    # 否则首词会静默变成 "\ufeff词"，既污染词库又破坏大小写去重
    return parse_word_lines(path.read_text(encoding="utf-8-sig"))


def save_words(path: Path, wlist: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 原子替换：避免写入途中被 kill 或两个实例并发运行时得到撕裂的词库文件
    # tmp 名带 PID：两个 xuen 实例并发写同一 workspace 时不会互踩临时文件
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        tmp.write_text("\n".join(wlist) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        # 失败时清理临时文件，避免在工作区堆积 words.txt.<pid>.tmp 垃圾
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


def generate_words_shell(shell_agent, task: str, count: int, batch: int,
                         info: Callable[[str], None] = ui.info,
                         warn: Callable[[str], None] = ui.warn,
                         stop: Optional[Callable[[], bool]] = None) -> List[str]:
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
            "要求：每行一个词；不要编号、不要解释、不要输出任何多余内容；只输出词表本身。"
        )
        out = shell_agent.run(prompt) or ""
        # 超时/非零退出的输出是截断的半成品，不能直接解析；
        # 且同一 agent 命令大概率批批失败，继续只会空烧时间
        if (getattr(shell_agent, "timed_out", False)
                or getattr(shell_agent, "returncode", 0)):
            # 区分用户主动停止（如 TUI 按 q 杀掉 agent）：那不是失败，
            # 不应误报「执行失败」警告（与 runner 主循环的处理一致）
            if stop is not None and stop():
                break
            warn("词库生成批次执行失败（超时或非零退出），停止生成")
            break
        fresh = 0
        for w in parse_word_lines(out):
            key = w.casefold()
            if key not in seen:
                seen.add(key)
                wlist.append(w)
                fresh += 1
        if fresh == 0:
            warn("词表不再增长，提前结束收集")
            break
    return wlist[:count]
