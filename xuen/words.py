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
# 分隔符后跟数字时是真实术语（如 "0.5倍速"、"2.5D"），不能当序号剥掉
_BULLET = re.compile(
    r"^(?:\d+\s*[\.\)、）](?!\d)\s*|（\d+）\s*|\(\d+\)\s*|[-*•·]\s*)+")

# 词形两端要剥掉的引号/书名号/装饰符（含中文成对括号，
# 否则 "「`词`," 之类会留下 '「`词' 残片混进词库）
_EDGE_CHARS = "`*_^~'\"“”‘’「」『』《》〈〉【】〔〕〖〗 "

# 纯数字（含 "3.14" / "2.5" 这类小数，isdigit() 拦不住）不是词；
# 但 "0.5倍速"、"2.5D" 这类含非数字字符的术语必须保留，故用整串匹配
_PURE_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def _clean_line(line: str) -> Optional[str]:
    w = _BULLET.sub("", line.strip()).strip()
    w = w.strip(_EDGE_CHARS).strip()
    if not w or len(w) > 60:
        return None
    if w.startswith(("#", ">", "|", "=")) or _PURE_NUMBER.match(w):
        return None
    if "://" in w:
        # URL 不是灵感词；若交给下面按 ':' 截断，会把 "http"/"https"
        # 这类协议名误收进词库。
        return None
    for sep in ("：", ":"):  # "词：解释"/"词:解释" 只留词
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
        if "：" in w or ":" in w:
            return None
    # 尾部标点剥除后，可能露出此前被标点挡住的引号/反引号
    # （如 "「`词`," → "词`"），需再剥一次，否则残片混进词库
    w = w.rstrip(".。,，;；!！?？ ")
    w = w.strip(_EDGE_CHARS).strip()
    # 冒号截断后词形已变（如 "12: 解释" → "12"），需复查拦截条件，
    # 否则纯数字 / 以 # > | = 开头的残片会混进词库
    if not w or len(w) > 60:
        return None
    if w.startswith(("#", ">", "|", "=")) or _PURE_NUMBER.match(w):
        return None
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
    # 否则文件中的重复词会扭曲 random.sample 的抽样分布
    return parse_word_lines(path.read_text(encoding="utf-8"))


def save_words(path: Path, wlist: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 原子替换：避免写入途中被 kill 或两个实例并发运行时得到撕裂的词库文件
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(wlist) + "\n", encoding="utf-8")
    os.replace(tmp, path)


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
