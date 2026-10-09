"""领域词库：由外部 agent 生成、解析、持久化、随机抽样（抽样这一步绝不调用任何 LLM）。"""
from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Callable, List, Optional

from .ui import ui

# 序号也要兼容全角形式：1. / 2、 / 3) / 4）/ （5）—— 中文 LLM 常用后者
_BULLET = re.compile(
    r"^(?:\d{1,3}\s*[\.\)、）]\s*|（\d{1,3}）\s*|[-*•·]\s*)+")


def _clean_line(line: str) -> Optional[str]:
    w = _BULLET.sub("", line.strip()).strip()
    w = w.strip("`*_^~'\"“”‘’ ").strip()
    if not w or len(w) > 60:
        return None
    if w.startswith(("#", ">", "|", "=")) or w.isdigit():
        return None
    for sep in ("：", ":"):  # "词：解释"/"词:解释" 只留词
        if sep in w:
            head, _, tail = w.partition(sep)
            head = head.strip()
            if not head or len(head) > 30 or not tail.strip():
                return None
            w = head
            break
    w = w.rstrip(".。,，;；!！?？ ")
    if not w or len(w) > 60:
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
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def save_words(path: Path, wlist: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(wlist) + "\n", encoding="utf-8")


def sample_words(wlist: List[str], n: int) -> List[str]:
    """纯随机抽样，不调用 LLM。"""
    if n <= 0 or not wlist:
        return []
    return random.sample(wlist, min(n, len(wlist)))


def generate_words_shell(shell_agent, task: str, count: int, batch: int,
                         info: Callable[[str], None] = ui.info,
                         warn: Callable[[str], None] = ui.warn) -> List[str]:
    """通过外部 agent（如 opencode）分批生成领域词库。"""
    wlist: List[str] = []
    seen = set()
    max_batches = max(2, count // max(batch, 1) + 3)
    for i in range(max_batches):
        if len(wlist) >= count:
            break
        ask = min(batch, count - len(wlist) + 20)
        info(f"通过外部 agent 生成词库 {len(wlist)}/{count}（第 {i + 1} 批）")
        prompt = (
            f"请为研究方向「{task}」列出 {ask} 个紧密相关的术语/关键词。\n"
            "要求：每行一个词；不要编号、不要解释、不要输出任何多余内容；只输出词表本身。"
        )
        out = shell_agent.run(prompt) or ""
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
