"""轮次守卫（round guard）：每轮快照、候选/最佳分离、自动验证与评分。

背景：xuen 的研究循环里，外部 agent 每轮【整体覆盖】想法区/产物区，
下一轮无条件继承最新状态——一旦某轮产出了更差的方案，更好的前一轮
结果就被静默覆盖丢失。本模块在不改变循环主体的前提下加一道守卫：

  每轮结束
    │
    ├─ 无改动 → 记「心跳」，不产生候选
    ├─ 有改动 → 快照为候选 cand-<id>.md（候选 ≠ 最佳，绝不直接当最佳用）
    │            │
    │            ├─ 结构损坏（区块标记缺失）→ 直接拒绝，还原最佳
    │            ├─ 验证方式 rounds.verify：
    │            │    auto  → 有可运行测试套件就跑测试；否则用兜底评分者
    │            │             （rounds.fallback = user / ai）
    │            │    tests → 只跑测试（pytest → make → npm → go 级联）；
    │            │             没有套件/跑不起来 → 候选挂起，等待用户评分
    │            │    user  → 用户在 rounds/verdicts.txt 里评分（>= 阈值采纳）
    │            │    ai    → 复用外部 agent 当评审员打分（>= 阈值采纳）
    │            │    off   → 不验证，快照照存、最新即最佳
    │            │
    │            ├─ 通过（测试全绿 / 评分 >= rounds.adopt_score）→ 晋升为最佳
    │            │    best.md / best.json 更新（前进式，不改写历史记录）
    │            └─ 失败 / 挂起 → 把 research.md 还原为当前最佳
    │                 —— 下一轮【永远从最佳出发】，更差的候选无法污染后续轮次
    │
    └─ 所有事件追加进 rounds/history.jsonl（审计用，只增不改）

用户评分协议（非交互，兼容 CI / 后台循环）：
  在 <workspace>/rounds/verdicts.txt 里追加一行：
      <候选id> <0-10 分> [评语]
  例如： 20261017-031037-r5 8 想法区更有深度，产物区伪代码可落地
  守卫在每轮开始/结束时会应用待决评分：给旧候选补分并达到阈值时，
  该候选会被「前进式」晋升为最佳并写回 research.md（等价于回滚到它，
  但不改写任何历史记录）；低于阈值则记为拒绝。

所有守卫操作都遵循「失败一律降级、绝不阻断研究循环」：守卫自身异常
（目录不可写、评审员崩了、评分解析不出……）最多丢弃当轮守卫结论，
循环照常进行，最佳状态不会被破坏。
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import state
from .agents import ShellAgent
from .config import Config
from .procs import kill_process_tree, popen_kwargs
from .sink import Sink

VERIFY_MODES = ("auto", "tests", "user", "ai", "off")
FALLBACK_SCORERS = ("user", "ai")

HISTORY_NAME = "history.jsonl"
BEST_MD_NAME = "best.md"
BEST_JSON_NAME = "best.json"
VERDICTS_NAME = "verdicts.txt"
CAND_PREFIX = "cand-"

# 评分解析：兼容中英文、全半角冒号；取【最后一次】出现的分数
# （评审员被要求把「评分: N」放在输出最后一行，但容错取最后匹配）
# 英文模式不分大小写：AI 评审员可能输出 "score"/"Score"/"SCORE"
_SCORE_PATTERNS = (
    re.compile(r"评\s*分\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)"),
    # 前置负向断言：score 不能粘在英文单词尾部（「prescore: 3」「underscore:
    # 3」里的 score 只是单词后缀，不是评分标签）；空格 / 行首 / 下划线等
    # 非字母前缀（overall_score: 5）照常匹配
    re.compile(r"(?<![A-Za-z])score\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)",
               re.IGNORECASE),
)


# ----------------------------------------------------------------------
# 小工具
def _atomic_write(path: Path, text: str) -> None:
    """tmp + os.replace 原子写：读端永远不会看到半截文件。

    tmp 名带 PID：同一 workspace 并发运行两个 xuen 实例时，固定名 .tmp
    会被两边交错写入（各自截断后各自覆盖），os.replace 随后把撕裂内容
    发布成有效的 best.json / best.md——元数据解析失败、还原源内容碎裂。
    words.txt / write_section.py 的写入早已按 PID 隔离（见
    words.save_words / state.write_helper_script），守卫的原子写同理。
    """
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _valid_round(value: object) -> bool:
    """round 是否为可安全参与比较/写盘的整数（bool 不算：JSON true 会解析
    成 True，`True > 0` 虽不报错但语义错误）。best.json 的加载校验、历史
    恢复与补评采纳必须用同一口径，避免「一处拒绝、另一处照写」的裂缝。"""
    return isinstance(value, int) and not isinstance(value, bool)


_CID_RE = re.compile(r"[A-Za-z0-9_-]+\Z")


def _valid_cid(value: object) -> bool:
    """候选 id 是否可安全拼进快照文件名 `rounds/cand-<id>.md`。

    生成侧（_snapshot_candidate / 基线）只会产出 [0-9A-Za-z_-]，但
    best.json / history.jsonl / verdicts.txt 可能被外部编辑或由外部 agent
    写入：id 是合法 JSON 字符串却含 NUL 或路径分隔符时，拼出的路径会让
    read_text 抛 ValueError（embedded null byte）、或在 Windows 上把读取
    带出 rounds 目录。凡不满足安全字符集的 id 一律按损坏元数据处理
    （best.json 走 _recover_best 恢复、事件无法归属候选则跳过），绝不用
    它拼路径——守卫的降级原则要求损坏文件最多丢一次恢复机会，不能把
    整个守卫炸掉（start() 抛出的 ValueError 会让 runner 永久禁用守卫）。
    """
    return isinstance(value, str) and _CID_RE.match(value) is not None


def _valid_best(data: object) -> bool:
    """best.json 的最小字段校验：id 为可作文件名的安全字符串、round 为真整数。

    只校验下游会直接使用/比较的字段：round 参与 `best.get("round", 0) > 0`
    比较（字符串会让 finish() 抛 TypeError、汇总整段丢失），id 用于展示、
    事件关联并拼候选快照路径（见 _valid_cid）；score 允许 None（基线与
    「解析不出」的历史）或有限数值。NaN/inf 会让评分比较失效，超出
    float 范围的巨大整数会在 `:g` 格式化时抛 OverflowError，二者都必须
    按损坏元数据处理，交给 _recover_best 修复。
    """
    if not isinstance(data, dict):
        return False
    if not _valid_cid(data.get("id")):
        return False
    if not _valid_round(data.get("round")):
        return False
    score = data.get("score")
    if score is not None:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return False
        try:
            finite = math.isfinite(float(score))
        except (OverflowError, ValueError):
            return False
        if not finite:
            return False
    return True


def parse_score(text: str) -> Optional[float]:
    """从评审输出里解析 0-10 分；解析不出返回 None（调用方按挂起处理）。"""
    if not text:
        return None
    best: Tuple[int, float] = None  # type: ignore[assignment]
    for pat in _SCORE_PATTERNS:
        for m in pat.finditer(text):
            try:
                v = float(m.group(1))
            except ValueError:
                continue
            if best is None or m.start() >= best[0]:
                best = (m.start(), v)
    if best is None:
        return None
    return max(0.0, min(10.0, best[1]))


def _readable_section(text: str, name: str) -> Optional[str]:
    """区块的「结构可读」内容：缺文件 / 标记损坏返回 None，内容为空返回 ""。

    区分 None 与 ""：state.get_section 把「区块缺失」与「内容为空」都读成
    ""，还原时直接比较会把「文件损坏但最佳区块也为空」误判成「无需还原」，
    research.md 的标记就永远修不回来；必须先看结构是否可读。

    内容按写入规整形态返回（见 state.sanitize_section_content）：还原 /
    补评写回时 update_section_file 会剥掉内容里独占一行的区块标记字面量，
    比较时必须用同一形态，否则含标记字面量的最佳内容与磁盘上规整后的
    内容永远不相等——每轮都会误判为「仍有差异」并重复还原。

    注意与 state.get_section 的区分：后者返回原样内容，供展示 / 提示词
    使用；本函数服务于「比较后可能写回」的守卫判定。
    """
    if not text:
        return None
    content = state._first_section(text, name)
    if content is None:
        return None
    return state.sanitize_section_content(content)


def _structure_intact(text: str) -> bool:
    """两个区块的标记是否都能安全读出（见 state._first_section）。

    候选内容进入最佳前的最后一道结构闸门：快照落盘后可能被外部截断 /
    篡改（写盘中途崩溃、用户误编辑、并发实例），而读取路径
    （_adopt / _apply_user_verdicts）必须在写盘前重新校验——损坏内容
    绝不能进 best.md，否则下一次还原会把空区块写回 research.md，静默
    丢掉当前最佳（候选/最佳分离与「结构损坏不得进最佳」的核心不变量）。
    """
    if not text:
        return False
    return (state._first_section(text, state.SECTION_IDEA) is not None
            and state._first_section(text, state.SECTION_ARTIFACT) is not None)


@dataclass
class SuiteResult:
    """一次测试套件运行的结果。available=False 表示套件没有可用的验证
    结论（运行时缺命令、pytest 未收集到测试等），与「跑了但失败」
    （ok=False）必须区分：前者不能给候选下结论，只能转兜底评分或挂起。
    stopped=True 表示运行被用户主动停止（TUI 按 q / Ctrl+C）：套件
    已被整组终止、没有验证结论，调用方不能再拉起兜底评审。"""
    available: bool
    ok: bool = False
    reason: str = ""
    detail: str = ""
    stopped: bool = False


@dataclass
class Verdict:
    """候选的验证结论。result: adopted / rejected / pending。"""
    verifier: str            # tests / user / ai / none / guard
    result: str
    score: Optional[float] = None
    reason: str = ""
    comment: str = ""        # 评审员评语（AI 评分时可能拿到）


# ----------------------------------------------------------------------
# 测试套件探测与运行（能自动验证的跑测试）
def _find_spec(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


# 递归探测 pytest 文件时跳过的目录：虚拟环境/依赖缓存里常有第三方测试，
# 按它们探测会误判「本仓库有测试套件」，随后 pytest 从仓库根收集这些文件，
# 既慢又可能因第三方测试失败而拒绝所有候选。
_PYTEST_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", ".tox", ".nox", ".venv", "venv", ".env",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "site-packages", "build", "dist", "CVS", "_darcs",
    "{arch}",
})

# Makefile 里真正的 test 目标。`test: VAR=...`（含 export/private/override
# 等修饰）是 target-specific 变量赋值，不定义可执行目标：make test 会以
# 退出码 2 报「No rule to make target」，若按测试套件处理会把候选误判成
# 测试失败，连 auto 模式的兜底评分也会被跳过。
# 目标名里的字符：反斜杠转义的冒号 / 井号 / 空格属于名字本身
# （`foo\:bar test:`、`test foo\#bar:` 都能正常执行 test）；未转义的
# 分号会开始同行命令、井号是注释，不能算目标名。`test` 之后的目标名可以
# 含未转义等号（`test foo=bar:` 同时定义 test 与 foo=bar）；但 `test = x:`
# 这类紧跟 test 的赋值形式仍不是目标，见 _MAKE_TEST_TARGET 的负向前瞻。
_MAKE_VAR_UNIT = r"(?:\$\([^()\r\n]*\)|\$\{[^{}\r\n]*\})"
_MAKE_TARGET_WORD = (
    r"(?:" + _MAKE_VAR_UNIT
    + r"|[^:\s#;\\]|\\(?:[^\s]|[ \t]+(?![ \t])))+")
# 逻辑行内的词分隔：空白，或反斜杠续行。make 把续行与周围空白压成一个
# 空格（`test \` + `foo:` 与 `test foo:` 等价、`test\` + `:` 与 `test :`
# 等价），目标列表跨续行时同样要能识别 test；续行进入词内部则拆成两个
# 词（`te\` + `st:` 是目标 te 与 st），与加空格的行为一致。
_MAKE_SEP = r"(?:[ \t]|\\\r?\n)"
# test 之前的目标名不能含未转义的 %：`foo% test:` 会被 make 当成
# 「mixed implicit and normal rules」直接报错；test 之后的 % 则是
# GNU make 容忍的旧写法（make test 仍可执行），不能一并拒绝。
_MAKE_TARGET_WORD_BEFORE_TEST = (
    r"(?:" + _MAKE_VAR_UNIT
    + r"|[^:=\s#;\\%]|\\(?:[^\s=]|[ \t]+(?![ \t])))+")
# 行首的 export/unexport 只有在本行还是字面文本时才是导出指令；
# `$(T) export test:` 这类变量展开出的 export 是普通目标名，make 仍会
# 定义 test。展开后再判断会在目标列表里误删可运行套件。
_MAKE_EXPORT_DIRECTIVE = re.compile(r"^[ \t]*(?:export|unexport)(?:[ \t]|$)")

_MAKE_TEST_TARGET = re.compile(
    # 一行可以声明多个目标（`foo test:` / `test test2:`），test 不必是
    # 第一个；只认目标列表里的精确 test，`test-unit` / `test%` 不算。
    # 注释行由 (?!#) 挑掉；`;` 后的同行命令不属于目标列表。
    r"(?m)^(?!\t)[ \t]*(?!#)"
    # 行首 export/unexport 是导出指令而不是规则头：make 把整行当变量名
    # 列表（`export test:` 导出变量 test、`export foo test:` 导出 foo 与
    # test），不定义任何目标，`make test` 以退出码 2 失败——探测命中会把
    # 候选误判成测试失败。仅出现在目标列表中间时（`foo export test:`）
    # 仍是普通目标名，照常放行。
    r"(?!(?:export|unexport)" + _MAKE_SEP + r"+)"
    r"(?:" + _MAKE_TARGET_WORD_BEFORE_TEST + _MAKE_SEP + r"+)*test"
    # test 后第一个词若是 ?= / += / != / := / ::= 等赋值/空变量名写法，
    # 整行不是目标规则；后续词可以含 =（`test foo=bar:` 是合法目标名）。
    r"(?!" + _MAKE_SEP + r"+(?:[+?!]?=|:*=))"
    r"(?:" + _MAKE_SEP + r"+" + _MAKE_TARGET_WORD + r")*"
    # GNU make 4.3 的 grouped target 用 `&:` 分隔，且不要求 & 前有空白
    # （`test&:` 与 `test &:` 都定义可执行的 test 目标）；`test& :` 则是
    # 名为 test& 的普通目标，不能命中。
    + _MAKE_SEP + r"*(?:&)?:"
    # 分隔符后的冒号、赋值形态（test:::、test: :x、test: X=1、
    # test: = x）不能在这里用负向前瞻跳过：文件里另有合法 test 目标时，
    # make 仍可能因这些行在读取阶段报错。改由 _make_rule_header_is_valid
    # 判定，target-specific 变量赋值在 _make_defines_test_target 中跳过，
    # 其余非法规则头直接拒绝整个套件。
)


def _make_unescaped_colon(text: str, start: int) -> int:
    """返回 start 后第一个不在 $(...)/${...} 内、未被转义的冒号下标。

    Make 的变量引用内部可以带冒号（如 ${X:--x}），它不是规则分隔符；
    反斜杠转义的冒号（a\\:b）也只是文件名的一部分。注释/同行命令起点
    （# / ;）之后的内容不再属于规则头，扫到即停止并返回 -1。
    """
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch in "#;":
            return -1
        if ch == "$" and i + 1 < n and text[i + 1] in "({":
            opener = text[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 1
            j = i + 2
            while j < n and depth:
                cj = text[j]
                if cj == "\\":
                    j += 2
                    continue
                if cj == opener:
                    depth += 1
                elif cj == closer:
                    depth -= 1
                j += 1
            i = j
            continue
        if ch == ":":
            return i
        i += 1
    return -1


# GNU make 的变量名可含除空白、:、#、=、; 之外的字符（/ % + @ ! ^ & * 等
# 都是合法的 target-specific 变量名）；只允许 [A-Za-z0-9_.-] 会把
# `test: X/Y=1` 这类「只有变量赋值、没有可执行 test 目标」的 Makefile
# 误判成有测试套件。反斜杠转义的下一个字符属于名字本身。
_MAKE_VAR_NAME_UNIT = r"(?:\\.|[^\s:#=;])+"
_MAKE_TARGET_SPECIFIC_ASSIGNMENT = re.compile(
    r"(?:(?:export|private|override)[ \t]+)*"
    r"(?:" + _MAKE_VAR_NAME_UNIT + r"[ \t]*)?(?:[+?]?=|:*=|!=)"
)


_MAKE_NAMED_TARGET_ASSIGNMENT = re.compile(
    r"(?:(?:export|private|override)[ \t]+)*"
    + _MAKE_VAR_NAME_UNIT + r"[ \t]*(?:[+?]?=|::=|:=|!=)")


def _make_rule_is_target_specific(line: str, colon: int) -> bool:
    """规则头是否是 target-specific 变量赋值（test: X=1 / test::X=1）。

    这类行不定义可执行目标，但也不是语法错误：同一个 test 目标可以在
    别处定义，make 仍会执行它。探测必须跳过而不是据此拒绝整个套件。

    变量名必须非空且赋值运算符合法：`test: = x`、`test:::= x` 等会让
    make 报 empty variable name / target pattern 错误，不能当成可跳过
    的 target-specific 赋值。
    """
    start = colon + 1
    if start < len(line) and line[start] == ":":
        start += 1
    return _MAKE_NAMED_TARGET_ASSIGNMENT.match(
        line[start:].lstrip(" \t")) is not None


def _make_target_specific_assignment(text: str) -> bool:
    """规则头分隔符后是否是 target-specific 变量赋值（test::X=1 等）。

    双冒号紧贴分隔符时（test::X=1），正则里的赋值排除模式只看到第一个
    冒号后的 `:X=1`，匹配不到 `X=`；但 make 仍把它当作目标的变量赋值，
    不定义可执行目标，`make test` 以「No rule to make target」失败。
    这里从分隔符之后（含跳过双冒号）重新判断，且只认行首的赋值，避免
    把普通前置依赖 `test::foo bar=1`（foo 是依赖、bar=1 只是文件名）
    误判成赋值。
    """
    return _MAKE_TARGET_SPECIFIC_ASSIGNMENT.match(text.lstrip(" \t")) is not None


def _make_rule_header_is_valid(line: str, colon: int) -> bool:
    """检查已命中 test 目标的规则头里的第二个冒号是否合法。

    普通规则里前置依赖不能再出现未转义冒号（test: a:b / test: dep: x
    都会让 make 报 target pattern contains no '%'）；唯一例外是静态模式
    规则 test: %.o: %.c——第二个冒号前必须恰好是一个含未转义 % 的
    target-pattern（test: foo bar: dep 会报 multiple target patterns）。
    变量引用可能展开出 %，静态检查无法确定，沿用原来的探测口径。
    """
    start = colon + 1
    if start < len(line) and line[start] == ":":
        start += 1
    # target-specific 赋值可能使用 := / ::=，其冒号会被误当成静态模式
    # 规则的第二个冒号；变量名里又允许 %（如 `test: X%Y:=1`），不能靠
    # 「第二个冒号前有 %」放行。先按赋值语义识别，这类行不是可执行规则。
    if _make_target_specific_assignment(line[start:]):
        return False
    second = _make_unescaped_colon(line, start)
    if second < 0:
        return True
    target_pattern = line[start:second].strip()
    if not target_pattern:
        return False
    # 空白只在【未转义】时才是多个 target pattern（make 报 multiple
    # target patterns）；反斜杠转义的空格属于文件名本身，如
    # `test: foo%bar\ baz: dep` 是合法的静态模式规则。变量引用可能
    # 展开出 %，静态检查无法确定，沿用原来的探测口径放行。
    i = 0
    has_percent = False
    while i < len(target_pattern):
        ch = target_pattern[i]
        if ch == "\\":
            i += 2
            continue
        if ch.isspace():
            return False
        if ch == "%":
            has_percent = True
        i += 1
    return has_percent or "$" in target_pattern


def _make_has_escaped_semicolon(text: str) -> bool:
    """目标列表里是否有反斜杠转义的分号（目标名的一部分）。"""
    i = 0
    while i < len(text):
        if text[i] == "\\":
            if i + 1 < len(text) and text[i + 1] == ";":
                return True
            i += 2
            continue
        i += 1
    return False


def _make_has_recipe_separator(rest: str) -> bool:
    """规则头剩余部分是否有未转义、未进注释的同行命令分隔符 ;。"""
    i = 0
    while i < len(rest):
        ch = rest[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "#":
            return False
        if ch == ";":
            return True
        i += 1
    return False


def _make_grouped_target_has_recipe(text: str, line: str, colon: int,
                                    line_end: int) -> bool:
    """grouped target（test&:）必须带 recipe，否则 make 直接报错。"""
    if colon < 1 or line[colon - 1] != "&":
        return True
    if _make_has_recipe_separator(line[colon + 1:]):
        return True
    pos = line_end + 1 if line_end < len(text) else len(text)
    while pos < len(text):
        end = text.find("\n", pos)
        if end < 0:
            end = len(text)
        nxt = text[pos:end]
        stripped = nxt.strip()
        if not stripped or stripped.startswith("#"):
            pos = end + 1
            continue
        return nxt.startswith("\t")
    return False


def _make_logical_line_end(text: str, start: int) -> int:
    """返回从 start 开始的逻辑行末尾（跳过反斜杠续行）。"""
    pos = start
    while True:
        end = text.find("\n", pos)
        if end < 0:
            return len(text)
        i = end - 1
        if i >= pos and text[i] == "\r":
            i -= 1
        count = 0
        while i >= pos and text[i] == "\\":
            count += 1
            i -= 1
        if count % 2 == 0:
            return end
        pos = end + 1


def _make_continues_recipe_line(text: str, start: int) -> bool:
    """start 所在行是否是上一 recipe 物理行的续行。

    非 recipe 续行已由 _make_join_continuations 合并，不会再产生新行首；
    剩下的只有 recipe 续行。必须按反斜杠个数奇偶判断：`\\` 是转义的
    反斜杠，不续行，后面的 test: 仍是真实目标。
    """
    if start < 2 or text[start - 1] != "\n":
        return False
    end = start - 1
    if end > 0 and text[end - 1] == "\r":
        end -= 1
    count = 0
    while end > 0 and text[end - 1] == "\\":
        count += 1
        end -= 1
    return count % 2 == 1


def _make_has_mixed_target_colon_style(text: str) -> bool:
    """任一目标是否同时以 : 和 :: 定义（make 会直接停止解析）。

    GNU make 对每个具体目标只允许一种冒号风格；冲突目标不一定是 test
    本身（`test foo::` 后再写 `foo:` 也会让整个 Makefile 读取失败），
    因此必须在整份文本里检查，不能只看命中 test 的那一行。
    """
    styles: Dict[str, bool] = {}
    for line in text.splitlines():
        body = line.rstrip("\r")
        if not body or body.startswith("\t"):
            continue
        stripped = body.lstrip()
        if stripped.startswith("#"):
            continue
        if (_MAKE_VAR_ASSIGNMENT.match(body) is not None
                or _MAKE_EMPTY_VAR_ASSIGNMENT.match(body) is not None):
            continue
        colon = _make_unescaped_colon(body, 0)
        if colon < 0 or _make_rule_is_target_specific(body, colon):
            continue
        double = body[colon:colon + 2] == "::"
        words = re.findall(r"(?:\\.|[^\s])+", body[:colon])
        for word in words:
            if word.endswith("&"):
                word = word[:-1]
            if not word or _make_pattern_wildcard(word)[0] >= 0:
                # 模式规则允许同一模式分别用 : 和 :: 定义，make 不会报
                # both : and :: entries；只有具体目标才做冲突检查。
                continue
            previous = styles.get(word)
            if previous is None:
                styles[word] = double
            elif previous != double:
                return True
    return False


def _make_defines_test_target(text: str,
                              repo: Optional[Path] = None) -> bool:
    """规则头命中 test 且冒号结构合法时返回 True。"""
    if _make_has_mixed_target_colon_style(text):
        return False
    saw_single = False
    saw_double = False
    for match in _MAKE_TEST_TARGET.finditer(text):
        if _make_continues_recipe_line(text, match.start()):
            continue
        line_end = _make_logical_line_end(text, match.start())
        line = text[match.start():line_end]
        colon = match.end() - match.start() - 1
        # 正则里的冒号可能落在目标名中的变量引用里（如
        # `test ${X:--x}` 并没有规则分隔符）。只有行内第一个真正的
        # 未转义冒号才是规则分隔符；不一致时说明这是变量引用里的冒号。
        if _make_unescaped_colon(line, 0) != colon:
            continue
        if not _make_rule_header_is_valid(line, colon):
            # 整行本身就是变量赋值（test:= x / test ::= x）时 test 不是
            # 规则头，跳过；target-specific 变量赋值也不是可执行目标，
            # 可以跳过。其余非法规则头会让 make 在读取阶段报错，即使
            # 别处定义了 test 目标也无法执行，必须按「没有可运行套件」
            # 处理。
            if _MAKE_VAR_ASSIGNMENT.match(line):
                continue
            if _make_rule_is_target_specific(line, colon):
                continue
            return False
        if line[colon:colon + 2] == "::":
            saw_double = True
        else:
            saw_single = True
        if saw_single and saw_double:
            # make: target file 'test' has both : and :: entries.
            return False
        # GNU make 4.3 对目标名里的 \; 有个解析限制：没有同行命令
        # 分隔符（哪怕是空的 `;`）时整行会报 missing separator。此时
        # make test 必然失败，不能探测成套件。
        if (_make_has_escaped_semicolon(line[:colon])
                and not _make_has_recipe_separator(line[colon + 1:])):
            return False
        if not _make_grouped_target_has_recipe(text, line, colon, line_end):
            return False
    if saw_single or saw_double:
        return True
    return _make_pattern_rule_defines_test(text, repo)


def _make_pattern_rule_defines_test(text: str,
                                    repo: Optional[Path] = None) -> bool:
    """模式规则是否能为 test 提供 recipe。

    `%:` / `t%st:` 这类模式规则在模式能匹配 test 且没有依赖时，
    `make test` 会直接执行它的 recipe；`test%` / `%test` 需要非空
    stem，GNU make 不会用它们匹配 test。带依赖的模式规则只有在依赖
    都是已存在的字面文件时才可静态确认（例如 `%: %.c` + 现有
    test.c），其余依赖可能来自变量、其它隐式规则或需要构建，交给
    「没有套件」处理。
    """
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        body = line.rstrip("\r\n")
        if not body or body.startswith("\t"):
            continue
        stripped = body.lstrip()
        if stripped.startswith("#"):
            continue
        if _MAKE_VAR_ASSIGNMENT.match(body):
            continue
        colon = _make_unescaped_colon(body, 0)
        if colon < 0:
            continue
        if colon + 1 < len(body) and body[colon + 1] == ":":
            rest_start = colon + 2
        else:
            rest_start = colon + 1
        rest = body[rest_start:]
        # 静态模式规则（test: %.o: %.c）与带依赖的规则都不在静态探测
        # 范围内；这里只接无依赖、有 recipe 的模式规则。
        if _make_unescaped_colon(rest, 0) >= 0:
            continue
        if _make_has_recipe_separator(rest):
            prereq = rest.split(";", 1)[0]
            has_recipe = True
        else:
            prereq = rest
            has_recipe = False
            pos = index + 1
            while pos < len(lines):
                following = lines[pos].rstrip("\r\n")
                if following.startswith("\t"):
                    has_recipe = True
                    break
                if (not following.strip()
                        or following.lstrip().startswith("#")):
                    pos += 1
                    continue
                break
        if not has_recipe:
            continue
        prereq = _make_strip_comment(prereq)
        targets = body[:colon]
        if targets.endswith("&"):
            targets = targets[:-1]
        words = re.findall(r"(?:\\.|[^\s])+", targets)
        if not words or any(_make_pattern_wildcard(word)[0] < 0
                            for word in words):
            # 普通目标与模式目标混在一行会让 make 报
            # 「mixed implicit and normal rules」并停止解析。
            continue
        for pattern in words:
            matched, stem = _make_pattern_match(pattern, "test")
            if not matched:
                continue
            if not (stem or _make_pattern_unescape(pattern) == "%"):
                continue
            if not prereq.strip(" \t|"):
                return True
            if (repo is not None
                    and _make_pattern_prereqs_exist(prereq, stem or "",
                                                    repo)):
                return True
    return False


class _MakeRequiredIncludeError(Exception):
    """必需的 include 无法读取：make 会在执行 test 前直接失败。"""


# 变量名可含除空白、:、#、=、; 之外的字符（/ % + @ ! ^ & * 等）；
# 名称用非贪婪匹配，让 `X?=1` 仍按 `?=` 运算符解析、`X? =1` 才是
# 名为 `X?` 的普通赋值。只允许 [A-Za-z0-9_.-] 会漏掉这些合法变量，
# 目标头里的 `$(X/Y)` 展开为空、可运行的 test 套件被误判成没有测试。
_MAKE_VAR_NAME = r"(?:\\.|[^\s:#=;])+"
# 赋值行先匹配字面变量名；`$(T) = test` 这类动态变量名要留给下面的
# 展开路径，名字里不能吞掉 $ ( ) { }（否则会被当成名为 `$(T` 的赋值）。
_MAKE_PLAIN_VAR_NAME = r"(?:\\.|[^\s:#=;$(){}])+"
_MAKE_VAR_ASSIGNMENT = re.compile(
    r"^[ ]*(?:(?:export|override|private)[ \t]+)*"
    r"((?:\\.|[^\s:#=;$(){}])+?)[ \t]*(::=|:=|\?=|\+=|!=|=)[ \t]*(.*)$")

_MAKE_EMPTY_VAR_ASSIGNMENT = re.compile(
    r"^[ ]*(?:(?:export|override|private)[ \t]+)*"
    r"(?:::=|::=|:=|\?=|\+=|!=|=)")

_MAKE_EMPTY_UNDEFINE = re.compile(
    r"^[ ]*(?:(?:export|override|private)[ \t]+)*undefine[ \t]*$")

_MAKE_VAR_REF = re.compile(
    r"(?<!\$)\$(?:\(([^\s:{}()=#;]+)(?::([^()\r\n]*))?\)"
    r"|\{([^\s:{}()=#;]+)(?::([^{}\r\n]*))?\}"
    r"|([A-Za-z0-9_]))")


def _make_strip_comment(line: str) -> str:
    i = 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "#":
            return line[:i]
        i += 1
    return line


def _make_strip_value_comment(line: str) -> str:
    """按 make 变量赋值语义去掉注释并处理 # 前的反斜杠。

    连续 n 个反斜杠后跟 #：输出 n//2 个反斜杠；n 为奇数时 # 是字面量，
    为偶数时 # 开始注释。其他位置的反斜杠原样保留。
    """
    out = []
    i = 0
    while i < len(line):
        if line[i] != "\\":
            if line[i] == "#":
                break
            out.append(line[i])
            i += 1
            continue
        j = i
        while j < len(line) and line[j] == "\\":
            j += 1
        if j < len(line) and line[j] == "#":
            out.append("\\" * ((j - i) // 2))
            if (j - i) % 2:
                out.append("#")
                i = j + 1
                continue
            return "".join(out)
        out.append(line[i:j])
        i = j
    return "".join(out)


def _make_quote_value_for_assignment(value: str) -> str:
    """把已按 make 语义处理过的值重新编码成单行赋值的 raw 值。

    `_make_strip_value_comment` 会去掉 # 前的转义；这里反向加倍反斜杠，
    保证重新扫描时得到同一个值（主要用于把 define 体转成占位赋值）。
    """
    out = []
    i = 0
    while i < len(value):
        if value[i] == "\\":
            j = i
            while j < len(value) and value[j] == "\\":
                j += 1
            count = j - i
            if j < len(value) and value[j] == "#":
                out.append("\\" * (count * 2 + 1))
                out.append("#")
                i = j + 1
                continue
            out.append(value[i:j])
            i = j
            continue
        if value[i] == "#":
            out.append("\\#")
        else:
            out.append(value[i])
        i += 1
    return "".join(out)


def _make_include_names(args: str) -> List[str]:
    """提取 include/-include/sinclude 的文件名（保留反斜杠转义）。

    保留转义是必要的：`include foo\\*.mk` 里的 * 是文件名的一部分，
    不能当成通配符；路径里的空格也靠反斜杠转义。需要真实文件名时用
    _make_unescape_name。
    """
    names = []
    flat = re.sub(r"\\\r?\n", " ", _make_strip_comment(args))
    for token in re.findall(r"(?:\\.|[^\s])+", flat):
        if "$" in token:
            continue
        names.append(token)
    return names


def _make_unescape_name(name: str) -> str:
    """去掉 make 文件名里的反斜杠转义（`\\ ` -> 空格、`\\*` -> *）。"""
    return re.sub(r"\\(.)", r"\1", name)


def _make_glob_pattern(name: str) -> str:
    """把 make 文件名转成 glob 模式：只有未转义的 * ? [ 是通配符。"""
    out = []
    i = 0
    while i < len(name):
        ch = name[i]
        if ch == "\\" and i + 1 < len(name):
            out.append(glob.escape(name[i + 1]))
            i += 2
            continue
        out.append(ch if ch in "*?[" else glob.escape(ch))
        i += 1
    return "".join(out)


def _make_glob_matches(name: str, repo: Path) -> Tuple[List[str], bool]:
    """按 make 的 wildcard 语义展开文件名，返回 (匹配, 是否绝对路径)。

    与 include 的必需文件检查共用：转义的通配符按字面匹配，未转义的
    才交给 glob。
    """
    unescaped = _make_unescape_name(name)
    absolute = Path(unescaped).is_absolute()
    pattern = _make_glob_pattern(name)
    if not absolute:
        pattern = os.path.join(glob.escape(str(repo)), pattern)
    try:
        matches = sorted(glob.glob(pattern))
    except (OSError, re.error):
        matches = []
    return matches, absolute


_MAKE_INCLUDE_FUNCTIONS = frozenset({
    "wildcard", "dir", "notdir", "addprefix", "addsuffix", "strip",
    "basename", "suffix", "firstword", "lastword", "abspath", "realpath",
    "filter", "filter-out", "subst", "patsubst", "word", "wordlist",
    "words", "sort", "findstring", "join",
})


def _make_pattern_unescape(text: str) -> str:
    """处理 pattern/replacement 中第一个通配 % 之前的反斜杠。

    紧邻 % 的连续反斜杠两两折叠成一个字面反斜杠，并把 % 变成字面 %；
    不紧邻 % 的反斜杠原样保留。第一个通配 % 之后的文本由调用方按字面
    使用，不再做反转义（GNU make 的行为）。
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        j = i
        while j < n and text[j] == "\\":
            j += 1
        count = j - i
        if j < n and text[j] == "%":
            out.append("\\" * (count // 2))
            out.append("%")
            i = j + 1
        else:
            out.append("\\" * count)
            i = j
    return "".join(out)


def _make_pattern_wildcard(text: str) -> Tuple[int, int]:
    """返回第一个未转义 % 的位置及其前面连续反斜杠的起点。

    没有通配 % 时返回 (-1, -1)。
    """
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\\":
            j = i
            while j < n and text[j] == "\\":
                j += 1
            if j < n and text[j] == "%":
                if (j - i) % 2 == 0:
                    return j, i
                i = j + 1
                continue
            i = j
            continue
        if text[i] == "%":
            return i, i
        i += 1
    return -1, -1


def _make_pattern_apply_stem(text: str, stem: str) -> str:
    """把模式依赖里第一个 % 替换成 stem。

    GNU make 对模式规则依赖里的 % 不做反斜杠转义：`pre\\%post` 仍会把
    第一个 % 换成 stem，反斜杠原样保留；后续 % 按字面使用。
    """
    return text.replace("%", stem, 1)


def _make_pattern_prereqs_exist(prereq: str, stem: str, repo: Path) -> bool:
    """模式规则依赖是否都是仓库内已存在的文件（含 order-only）。

    GNU make 找不到依赖且没有其它规则可构建时会直接失败；这里只接受
    已存在的字面文件，避免把需要动态构建或由变量决定的依赖误判成
    可运行套件。目录也算存在（make 不会因为没有 recipe 而去重建它）。
    """
    words = re.findall(r"(?:\\.|[^\s|])+", prereq)
    if not words:
        return False
    for word in words:
        name = _make_pattern_apply_stem(word, stem)
        # 模式规则把 test 自己列为依赖时，make 会以「Circular test <-
        # test dependency dropped」忽略该依赖；其余依赖仍需存在。
        if name == "test":
            continue
        path = Path(name)
        if not path.is_absolute():
            path = repo / path
        if not path.exists():
            return False
    return True


def _make_pattern_match(pattern: str, word: str
                        ) -> Tuple[bool, Optional[str]]:
    """make 的 % 模式匹配，返回 (是否匹配, % 位置的词干)。

    只有第一个未转义的 % 是通配符；第一个通配符之前的反斜杠按
    GNU make 规则反转义，之后的字符全部按字面匹配（包括反斜杠和
    后续 %）。
    """
    wildcard, run_start = _make_pattern_wildcard(pattern)
    if wildcard < 0:
        regex = re.escape(_make_pattern_unescape(pattern))
        return re.fullmatch(regex, word) is not None, None
    prefix = _make_pattern_unescape(pattern[:run_start])
    prefix += "\\" * ((wildcard - run_start) // 2)
    suffix = pattern[wildcard + 1:]
    regex = re.escape(prefix) + "(.*)" + re.escape(suffix)
    match = re.fullmatch(regex, word)
    if match is None:
        return False, None
    return True, match.group(1)


def _make_pattern_subst(pattern: str, repl: str, word: str) -> Optional[str]:
    """patsubst 对单个词的替换；不匹配返回 None。"""
    matched, stem = _make_pattern_match(pattern, word)
    if not matched:
        return None
    if stem is None:
        return _make_pattern_unescape(repl)
    wildcard, run_start = _make_pattern_wildcard(repl)
    if wildcard < 0:
        return _make_pattern_unescape(repl)
    prefix = _make_pattern_unescape(repl[:run_start])
    prefix += "\\" * ((wildcard - run_start) // 2)
    return prefix + stem + repl[wildcard + 1:]


def _make_pattern_subst_words(pattern: str, repl: str, text: str) -> str:
    """对 text 的每个词做 % 模式替换，按 make 语义丢弃空结果。

    含通配 % 的 patsubst / 变量替换引用先按词切分再用单个空格拼接。
    替换参数本身为空时，make 会丢掉匹配词的空结果（`$(patsubst a%,,
    a b)` 是 `b` 而不是 ` b`）；但替换参数非空、只是展开后碰巧为空时
    仍占用一个词的位置（`$(patsubst a%,%,a b)` 是 ` b`）。
    """
    out = []
    for word in text.split():
        replaced = _make_pattern_subst(pattern, repl, word)
        value = word if replaced is None else replaced
        if value or repl:
            out.append(value)
    return " ".join(out)


def _make_function_words(value: str) -> List[str]:
    return value.split()


def _make_function_index(value: str, function: str,
                         allow_zero: bool = False) -> int:
    text = value.strip()
    if allow_zero and not text and value:
        # 只有显式写了空白（`$(wordlist 1, ,a b)`）才按 0 处理；
        # 完全省略参数（`$(wordlist 1,,a b)`）时 GNU make 报
        # non-numeric second argument，不能静默当成空结果。
        return 0
    if not re.fullmatch(r"[0-9]+", text):
        raise _MakeRequiredIncludeError(f"{function}: non-numeric index")
    index = int(text)
    if index < 0 or (index == 0 and not allow_zero):
        raise _MakeRequiredIncludeError(f"{function}: invalid index")
    return index


def _make_expand_include_function(name: str, args: str, repo: Path) -> str:
    """展开 include 文件名里可静态求值的 make 函数（不含 shell/eval）。"""
    if name == "wildcard":
        found = []
        for token in re.findall(r"(?:\\.|[^\s])+", args):
            matches, absolute = _make_glob_matches(token, repo)
            raw = _make_unescape_name(token)
            for match in matches:
                if absolute:
                    found.append(match)
                else:
                    rel = os.path.relpath(match, str(repo))
                    if raw.endswith("/") and not rel.endswith("/"):
                        rel += "/"
                    found.append(rel)
        return " ".join(found)
    if name in ("addprefix", "addsuffix"):
        # make 对少于两个参数（缺少逗号）直接报错并停止解析：不能当成
        # 空展开继续找 test 目标，否则会把必然失败的 make test 探测成套件。
        if "," not in args:
            raise _MakeRequiredIncludeError(args)
        affix, names = args.split(",", 1)
        # 非末位参数的起始空白由 make 的参数解析去掉；尾随空白属于
        # 参数本身（`$(addsuffix x ,a)` 的后缀是 "x "）。
        affix = affix.lstrip(" \t")
        words = names.split()
        if name == "addprefix":
            return " ".join(affix + word for word in words)
        return " ".join(word + affix for word in words)
    if name in ("filter", "filter-out"):
        if "," not in args:
            raise _MakeRequiredIncludeError(
                f"{name}: missing argument")
        patterns, text = args.split(",", 1)
        pats = patterns.split()
        keep = []
        for word in text.split():
            matched = any(_make_pattern_match(pat, word)[0]
                          for pat in pats)
            if matched == (name == "filter"):
                keep.append(word)
        return " ".join(keep)
    if name == "subst":
        parts = args.split(",", 2)
        if len(parts) < 3:
            raise _MakeRequiredIncludeError("subst: missing argument")
        old, new, text = parts
        # 只有紧跟函数名的第一个参数会被 make 去掉起始空白；逗号后的
        # 参数保留自己的起始空白（它可能就是要替换成的文本）。
        old = old.lstrip(" \t")
        if not old:
            # GNU make 对空 from 的 subst 把 new 追加到 text 末尾
            # （$(subst ,x,foo) -> foox），不是 Python 的逐字符插入。
            return text + new
        return text.replace(old, new)
    if name == "patsubst":
        parts = args.split(",", 2)
        if len(parts) < 3:
            raise _MakeRequiredIncludeError("patsubst: missing argument")
        pattern, repl, text = parts
        # 第一个参数前的空白属于函数语法；repl 的起始空白是有效内容。
        pattern = pattern.lstrip(" \t")
        wildcard, _run_start = _make_pattern_wildcard(pattern)
        if wildcard < 0:
            # 不含通配 % 时 make 原地替换每个词，保留输入文本原有空白；
            # 空 pattern 还会匹配文本末尾的空词（包括纯空白文本）。
            out = []
            last = 0
            for match in re.finditer(r"\S+", text):
                out.append(text[last:match.start()])
                word = match.group(0)
                replaced = _make_pattern_subst(pattern, repl, word)
                out.append(word if replaced is None else replaced)
                last = match.end()
            out.append(text[last:])
            result = "".join(out)
            if not pattern and (not text or text[-1].isspace()):
                result += _make_pattern_unescape(repl)
            return result
        return _make_pattern_subst_words(pattern, repl, text)
    if name == "word":
        parts = args.split(",", 1)
        if len(parts) < 2:
            raise _MakeRequiredIncludeError("word: missing argument")
        index = _make_function_index(parts[0], "word")
        words = _make_function_words(parts[1])
        return words[index - 1] if index <= len(words) else ""
    if name == "wordlist":
        parts = args.split(",", 2)
        if len(parts) < 3:
            raise _MakeRequiredIncludeError("wordlist: missing argument")
        start = _make_function_index(parts[0], "wordlist")
        # GNU make 允许 wordlist 的结束下标为 0（结果为空），开始下标仍须 >=1；
        # 结束参数为纯空白时同样按 0 处理。
        end = _make_function_index(parts[1], "wordlist", allow_zero=True)
        words = list(re.finditer(r"\S+", parts[2]))
        if start > end or start > len(words):
            return ""
        selected = words[start - 1:end]
        if not selected:
            return ""
        return parts[2][selected[0].start():selected[-1].end()]
    if name == "words":
        return str(len(_make_function_words(args)))
    if name == "sort":
        return " ".join(sorted(set(_make_function_words(args))))
    if name == "findstring":
        parts = args.split(",", 1)
        if len(parts) < 2:
            raise _MakeRequiredIncludeError("findstring: missing argument")
        needle = parts[0].lstrip(" \t")
        return needle if needle in parts[1] else ""
    if name == "strip":
        return " ".join(args.split())
    if name == "join":
        if "," not in args:
            raise _MakeRequiredIncludeError("join: missing argument")
        left, right = args.split(",", 1)
        left_words = left.split()
        right_words = right.split()
        out = []
        for index in range(max(len(left_words), len(right_words))):
            word = ((left_words[index] if index < len(left_words) else "")
                    + (right_words[index]
                       if index < len(right_words) else ""))
            # 较短的列表缺少对应词时按空串拼接；两侧对应的词都为空
            # （实际上只会出现在较短列表耗尽后）时 make 不输出空词。
            if word:
                out.append(word)
        return " ".join(out)
    words = args.split()
    if name == "firstword":
        return words[0] if words else ""
    if name == "lastword":
        return words[-1] if words else ""
    if name in ("abspath", "realpath"):
        result = []
        for word in words:
            path = word if os.path.isabs(word) else os.path.join(str(repo),
                                                                word)
            path = os.path.abspath(path)
            if name == "realpath":
                path = os.path.realpath(path)
                if not os.path.exists(path):
                    continue
            result.append(path)
        return " ".join(result)
    if name == "dir":
        result = []
        for word in words:
            slash = word.rfind("/")
            result.append(word[:slash + 1] if slash >= 0 else "./")
        return " ".join(result)
    if name == "notdir":
        result = []
        for word in words:
            slash = word.rfind("/")
            result.append(word[slash + 1:] if slash >= 0 else word)
        return " ".join(result)
    # make 的 basename/suffix 只看最后一个 / 之后的最后一个点：
    # `foo/.bar` 的 basename 是 `foo/`、suffix 是 `.bar`；`.hidden`
    # 的 basename 为空、suffix 为 `.hidden`；目录名里的点不算后缀。
    parts = []
    for word in words:
        slash = word.rfind("/")
        dot = word.rfind(".")
        if dot > slash:
            parts.append((word[:dot], word[dot:]))
        else:
            parts.append((word, ""))
    if name == "suffix":
        # make 的 suffix 跳过没有后缀的词，不会输出空占位。
        return " ".join(suffix for _base, suffix in parts if suffix)
    return " ".join(base for base, _suffix in parts)


def _make_find_include_function(text: str, pos: int):
    """从 pos 起找下一个可静态求值的 make 函数调用。

    返回 (start, end, name, args)；找不到返回 None。按括号嵌套扫描，
    这样 `$(wildcard $(addprefix $(D)/, *.mk))` 这类常见嵌套也能展开。
    未闭合的 `$(` / `${` 会让 make 直接报错，按无套件处理。
    """
    i = pos
    while i + 1 < len(text):
        if text[i] == "$" and text[i + 1] == "$":
            # make 把 $$ 当字面 $，后面的 (...) 不会被当成函数调用。
            i += 2
            continue
        if text[i] != "$" or text[i + 1] not in "({":
            i += 1
            continue
        opener = text[i + 1]
        closer = ")" if opener == "(" else "}"
        stack = [closer]
        k = i + 2
        while k < len(text):
            ch = text[k]
            if ch == "\\":
                k += 2
                continue
            if ch == "$" and k + 1 < len(text) and text[k + 1] in "({":
                stack.append(")" if text[k + 1] == "(" else "}")
                k += 2
                continue
            if ch == stack[-1]:
                stack.pop()
                if not stack:
                    break
            k += 1
        if stack:
            # 未闭合的变量/函数引用会让 make 直接报错并停止解析。
            raise _MakeRequiredIncludeError(text[i:])
        j = i + 2
        while j < len(text) and (text[j].isalnum() or text[j] in "_-"):
            j += 1
        name = text[i + 2:j]
        if (name in _MAKE_INCLUDE_FUNCTIONS and j < len(text)
                and text[j] in " \t"):
            return i, k + 1, name, text[j:k].lstrip(" \t")
        i += 1
    return None


def _make_expand_include_functions(text: str, repo: Path) -> str:
    """展开 include 文件名里可静态求值的函数（支持嵌套调用）。"""
    pos = 0
    while True:
        call = _make_find_include_function(text, pos)
        if call is None:
            return text
        start, end, name, args = call
        evaluated = _make_expand_include_functions(args, repo)
        if "$" in evaluated:
            # 参数里还有未展开的函数/变量（如 shell/eval），不能静态求值。
            pos = end
            continue
        replacement = _make_expand_include_function(name, evaluated, repo)
        text = text[:start] + replacement + text[end:]
        pos = start + len(replacement)


def _make_include_paths(name: str, repo: Path) -> List[Path]:
    """把 include 文件名（含通配符）展开成待读取路径。

    通配符按 make 的 wildcard 语义展开；没有匹配时保留原字面量，让
    `include` 的必需文件缺失检查把它当成错误（`-include` 则忽略）。
    反斜杠转义的通配符/空格按字面文件名处理。
    """
    matches, absolute = _make_glob_matches(name, repo)
    if matches:
        return [Path(match) for match in matches]
    path = Path(_make_unescape_name(name))
    if not absolute:
        path = repo / path
    return [path]


def _make_substitute_ref(value: str, spec: str) -> str:
    """展开 make 的变量替换引用 `$(VAR:old=new)`。

    没有 % 时是后缀替换（每个以 old 结尾的词把后缀换成 new；old 为空
    时在词尾追加 new）；含 % 时等价于 patsubst。没有 = 的写法在 make
    里展开为空串。
    """
    if "=" not in spec:
        return ""
    old, new = spec.split("=", 1)
    words = value.split()
    # 只有未转义的 % 才让替换引用按 patsubst 解释；`a\%` 是字面后缀，
    # 否则 `$(X:a\%=test)` 会被错误地当成整词匹配。
    if _make_pattern_wildcard(old)[0] >= 0:
        return _make_pattern_subst_words(old, new, value)
    suffix = _make_pattern_unescape(old)
    if suffix == "":
        return " ".join(word + new for word in words)
    return " ".join(
        word[:-len(suffix)] + new if word.endswith(suffix) else word
        for word in words)


def _make_expand_refs(text: str, variables: Dict[str, Optional[str]],
                      simple: Dict[str, bool], depth: int = 0,
                      active: Optional[set] = None) -> str:
    if depth > 20:
        return text
    if active is None:
        active = set()

    def repl(match: re.Match) -> str:
        name = match.group(1) or match.group(3) or match.group(5)
        spec = None
        if match.group(1) is not None:
            spec = match.group(2)
        elif match.group(3) is not None:
            spec = match.group(4)
        if name not in variables:
            # make 里未定义变量展开为空串：`ifeq ($(T),)`、`test$(T):`
            # 都依赖这一点。shell 赋值（!=）的值未知，仍保留原样。
            return ""
        value = variables[name]
        if value is None:
            return match.group(0)
        if not simple.get(name):
            if name in active:
                # 递归变量自引用/互相引用会让 make 在展开时直接报错，
                # 不能继续探测出 test 目标（随后 make test 必然失败）。
                raise _MakeRequiredIncludeError(name)
            active.add(name)
            try:
                value = _make_expand_refs(value, variables, simple,
                                          depth + 1, active)
            finally:
                active.discard(name)
        if spec is not None:
            value = _make_substitute_ref(value, spec)
        return value

    return _MAKE_VAR_REF.sub(repl, text)


def _make_apply_assignment(match: re.Match,
                           variables: Dict[str, Optional[str]],
                           simple: Dict[str, bool]) -> None:
    name, op, raw = match.groups()
    # make 保留注释前的尾随空白（`T = test # c` 的值是 `test `），
    # 它会在 `$(T)-unit:` 里把目标拆成 test 与 -unit；rstrip 会漏掉 test。
    raw = _make_strip_value_comment(raw)
    if op == "!=":
        variables[name] = None
        simple[name] = False
    elif op == "?=":
        if name not in variables:
            variables[name] = raw
            simple[name] = False
    elif op == "+=":
        if name not in variables:
            variables[name] = raw
            simple[name] = False
        elif variables[name] is not None:
            value = raw
            if simple.get(name):
                value = _make_expand_refs(value, variables, simple)
            # make 只在旧值非空且追加值非空时插入一个分隔空格；两侧的
            # 尾随空白都属于变量值本身（`X += bar ` 的值是 `foo bar `），
            # strip() 会把它吃掉，进而让 ifeq 等条件判断出错。
            if not variables[name]:
                variables[name] = value
            elif value:
                variables[name] = variables[name] + " " + value
    elif op in (":=", "::="):
        variables[name] = _make_expand_refs(raw, variables, simple)
        simple[name] = True
    else:
        variables[name] = raw
        simple[name] = False


def _make_scan_assignment(body: str,
                          variables: Dict[str, Optional[str]],
                          simple: Dict[str, bool]) -> Optional[str]:
    """处理一行赋值/undefine；是赋值时返回展开后的行，否则返回 None。"""
    stripped_body = _make_strip_comment(body)
    undef = re.match(
        r"^[ ]*(?:(?:override|export|private)[ \t]+)*undefine[ \t]+"
        r"(" + _MAKE_VAR_NAME + r")[ \t]*$", stripped_body)
    if undef is not None:
        variables.pop(undef.group(1), None)
        simple.pop(undef.group(1), None)
        return body
    if _MAKE_EMPTY_UNDEFINE.match(stripped_body):
        raise _MakeRequiredIncludeError("empty variable name")
    match = _MAKE_VAR_ASSIGNMENT.match(body)
    expanded = body
    if match is None and "$" in body:
        expanded = _make_expand_refs(body, variables, simple)
        match = _MAKE_VAR_ASSIGNMENT.match(expanded)
    if match is None:
        if _MAKE_EMPTY_VAR_ASSIGNMENT.match(_make_strip_comment(expanded)):
            # `$(UNDEFINED) = x` 展开后是空变量名，make 在读取阶段直接报错。
            raise _MakeRequiredIncludeError("empty variable name")
        return None
    _make_apply_assignment(match, variables, simple)
    return expanded


def _make_scan_assignments(text: str,
                           variables: Dict[str, Optional[str]],
                           simple: Dict[str, bool]) -> None:
    """按出现顺序把文本里的单行赋值应用到变量表（recipe 行除外）。"""
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if not body.startswith("\t"):
            _make_scan_assignment(body, variables, simple)


def _make_flatten_target_newlines(text: str) -> str:
    """按 make 的目标列表语义折叠变量展开产生的换行。

    make 只按空格/制表符拆分目标词；换行不属于分隔符。换行若直接跟在
    非空白字符后，它属于前一个目标名（`define BODY\nfoo\ntest` 展开
    后是名为 foo<换行>test 的目标，`test` 不是独立目标）；若位于行首
    或紧跟在空格/制表符后，则属于下一个目标词前的空白，会被跳过
    （`foo \ntest` 与 `\ntest` 都能得到独立目标 test）。
    """
    out: List[str] = []
    i = 0
    while i < len(text):
        if text[i] != "\n":
            out.append(text[i])
            i += 1
            continue
        j = i
        while j < len(text) and text[j] == "\n":
            j += 1
        if not out or out[-1] in " \t":
            # 行首/空白后的换行只是下一目标词的前导空白。
            pass
        else:
            # 裸换行属于前一个目标名，不能作为行分隔符参与匹配。
            out.append("\x00" * (j - i))
        i = j
    # 展开值可能以制表符开头；规则头前的空白按 make 语义忽略，而下游
    # 用行首制表符区分 recipe，必须先把这类前导制表符消掉。
    return "".join(out).lstrip(" \t")


def _make_expand_simple_vars(text: str,
                             repo: Optional[Path] = None) -> str:
    """按出现顺序展开简单的 make 变量引用，供目标探测使用。

    处理单行 `NAME =/:=/?=/+=/!=` 赋值、undefine 和 define 块；shell
    输出等无法静态求值的写法保持原样（探测不到就按无套件处理）。变量在
    规则头之前赋值才会生效，与 make 逐行读取的行为一致；recipe 行不展开。
    变量名本身也可以是展开结果（`$(T) = test`），展开后按赋值处理。规则
    头里的静态函数（如 `T = $(subst x,test,x)` 后的 `$(T):`）按使用位置
    展开。
    """
    variables: Dict[str, Optional[str]] = {}
    simple: Dict[str, bool] = {}
    out = []
    text = _make_join_continuations(text)
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        body = line.rstrip("\r\n")
        newline = line[len(body):]
        if body.startswith("\t"):
            out.append(line)
            i += 1
            continue
        define_match = _MAKE_DEFINE_LINE.match(body)
        if define_match is not None:
            # 第一遍把生效分支里的 define 原样保留下来；这里按顺序记录
            # 变量值，但不把 define 体当作规则行输出，避免体里的
            # `test:` 被误判成目标。
            name_text = _make_strip_value_comment(
                define_match.group(1) or "").strip()
            for op in (":::=", "::=", ":=", "?=", "+=", "!=", "="):
                found = name_text.find(op)
                if found >= 0:
                    name_text = name_text[:found].rstrip()
                    break
            name = _make_expand_refs(name_text, variables, simple)
            depth = 1
            body_lines = []
            i += 1
            while i < len(lines) and depth:
                inner = lines[i].rstrip("\r\n")
                if _MAKE_DEFINE_LINE.match(inner):
                    depth += 1
                    body_lines.append(inner)
                elif _MAKE_ENDEF_LINE.match(inner):
                    depth -= 1
                    if depth:
                        body_lines.append(inner)
                else:
                    body_lines.append(inner)
                i += 1
            if name:
                variables[name] = "\n".join(body_lines)
                simple[name] = False
            continue
        expanded = _make_scan_assignment(body, variables, simple)
        if expanded is not None:
            out.append(expanded + newline)
            i += 1
            continue
        if body.lstrip().startswith("#"):
            out.append(line)
            i += 1
            continue
        # `&` 后紧跟变量引用的 grouped target 写法在变量展开为空时仍按
        # 普通目标名处理（`test&$(T):` 是目标 test&，不是 grouped test）。
        # 插入一个非空白哨兵，避免展开后误判成 `test&:`。
        expand_input = re.sub(r"&(?=\$[({])", "&\x01", body)
        expanded = _make_expand_refs(expand_input, variables, simple)
        if repo is not None:
            expanded = _make_expand_include_functions(expanded, repo)
        expanded = _make_flatten_target_newlines(expanded)
        if (_MAKE_EXPORT_DIRECTIVE.match(expanded)
                and not _MAKE_EXPORT_DIRECTIVE.match(body)):
            # 这是变量展开后才变成 export/unexport 的目标行；加哨兵避免
            # 下游把它误当成字面导出指令而漏掉同一目标列表里的 test。
            expanded = "\x01" + expanded
        if "#" not in body:
            # 注释在展开前就已切掉，变量值里的 # 是目标名的一部分，
            # 不能让下游把它当成注释起点而漏掉同一目标列表里的 test。
            expanded = expanded.replace("#", "\x01")
        out.append(expanded + newline)
        i += 1
    return "".join(out)


_MAKE_INCLUDE_LINE = re.compile(
    r"^[ ]*(include|-include|sinclude)[ \t]+(.*)$")
_MAKE_CONDITIONAL_LINE = re.compile(
    r"^[ \t]*(ifeq|ifneq|ifdef|ifndef|else|endif)(?:[ \t]+(.*))?$")
_MAKE_DEFINE_LINE = re.compile(
    r"^[ \t]*(?:(?:override|export|private)[ \t]+)*define"
    r"(?:[ \t]+(.*))?$")
# endef 后只要求有空白分隔；多余文本在生效分支只警告
# （extraneous text after 'endef' directive），仍会结束 define 块。
_MAKE_ENDEF_LINE = re.compile(r"^[ \t]*endef(?:[ \t].*)?$")
# 未生效条件分支里 make 对 define/endef 仍做词法配对，但只认没有尾随
# 文本的 endef；`endef foo` 不会结束 define，后面直到真正的 endef/EOF
# 都被吞掉。严格版用于非活动分支，保证探测与 make 行为一致。
_MAKE_ENDEF_LINE_STRICT = re.compile(
    r"^[ \t]*endef(?:[ \t]*(?:#.*)?)?$")
_MAKE_DEFINE_EMPTY_NAME = re.compile(r"^(?:::=|::=|:=|\?=|\+=|!=|=)")


def _make_line_continues(body: str) -> bool:
    """行尾是否有未转义的续行反斜杠。"""
    count = 0
    for ch in reversed(body):
        if ch != "\\":
            break
        count += 1
    return count % 2 == 1


def _make_join_continuations(text: str) -> str:
    """把非 recipe 的物理行按 make 语义合并成逻辑行。

    make 在读取阶段把「反斜杠-换行」及其两侧空白压成一个空格；变量
    赋值、条件、include 和规则头都可能跨行。逐物理行扫描会把
    `T = test \\` + `  unit` 当成两个独立行，目标变量展开后漏掉 test。
    recipe 行（以 tab 开头）的续行属于 shell 命令，不能合并。

    注释行也按 make 的续行规则合并：`# ... \\` 会把下一行继续吞进
    注释，合并后目标探测才不会把注释里的 `test:` 当成真实规则。
    """
    lines = text.splitlines(keepends=True)
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        body = line.rstrip("\r\n")
        if body.startswith("\t"):
            out.append(line)
            i += 1
            continue
        if not _make_line_continues(body):
            out.append(line)
            i += 1
            continue
        pieces: List[str] = []
        ending = line[len(body):]
        while True:
            if _make_line_continues(body):
                pieces.append(body[:-1])
                i += 1
                if i >= len(lines):
                    break
                nxt = lines[i]
                body = nxt.rstrip("\r\n")
                ending = nxt[len(body):]
            else:
                pieces.append(body)
                break
        head = pieces[0].rstrip()
        if len(pieces) == 1:
            out.append(line)
        else:
            # 只保留最后一个物理行的行尾空白；中间行两侧的空白都属于
            # 续行分隔，按 make 语义压缩成一个空格。
            middle = [piece.strip() for piece in pieces[1:-1]]
            last = pieces[-1].lstrip()
            words = [piece for piece in middle if piece]
            if last:
                words.append(last)
            if words:
                joined = head + " " + " ".join(words)
            else:
                # 续行后面紧跟空行时，反斜杠-换行替换出的空格仍留在
                # 逻辑行尾（下一行自己的换行才是行尾）。丢掉这个空格
                # 会让 define 值里的 `test \n` 变成 `test\n`，目标
                # 列表语义随之改变：裸换行会粘进前一个目标名。
                joined = head + " "
            out.append(joined + ending)
        i += 1
    return "".join(out)


def _make_ifeq_args(rest: str
                    ) -> Tuple[Optional[str], Optional[str], bool]:
    """解析 ifeq/ifneq 的两种参数写法，返回 (左值, 右值, 是否去逗号空白)。

    括号写法 make 只去掉逗号两侧的语法空白（左值 rstrip、右值 lstrip），
    且必须在变量展开前去掉；变量值自身的首尾空白仍参与比较。
    引号写法保留引号内所有空白，不能套用同样的 strip。

    括号写法的第一个逗号必须在嵌套变量/函数引用之外：常见写法
    `ifeq ($(subst a,b,a),b)` 的前两个逗号都属于 subst 的参数，旧实现
    按第一个逗号切分会把左值截成 `$(subst a`，导致条件判断错误。
    """
    rest = rest.strip()
    if rest.startswith("("):
        # 找外层配对的右括号；后面即使还有文本，make 也只警告
        # extraneous text after 'ifeq' directive，条件仍按括号内求值。
        depth = 0
        close = -1
        i = 1
        while i < len(rest):
            ch = rest[i]
            if ch == "\\":
                i += 2
                continue
            if ch in "({":
                depth += 1
            elif ch in ")}":
                if depth == 0 and ch == ")":
                    close = i
                    break
                if depth > 0:
                    depth -= 1
            i += 1
        if close < 0:
            return None, None, True
        inner = rest[1:close]
        depth = 0
        comma = -1
        i = 0
        while i < len(inner):
            ch = inner[i]
            # 条件参数里的反斜杠不转义逗号：`ifeq (a\\,b,a\\,b)` 的
            # 第一个逗号就是参数分隔符（make 不把 \\, 当成字面逗号）。
            if ch in "({":
                depth += 1
            elif ch in ")}":
                if depth > 0:
                    depth -= 1
            elif ch == "," and depth == 0:
                comma = i
                break
            i += 1
        if comma < 0:
            return None, None, True
        return inner[:comma].rstrip(), inner[comma + 1:].lstrip(), True
    # 引号写法同样允许后续多余文本（warning）。
    match = re.match(
        r"^(['\"])(.*?)\1[ \t]+(['\"])(.*?)\3", rest)
    if match is None:
        return None, None, False
    return match.group(2), match.group(4), False


def _make_expand_condition_text(text: str,
                                variables: Dict[str, Optional[str]],
                                simple: Dict[str, bool],
                                repo: Optional[Path]) -> str:
    text = _make_expand_refs(text, variables, simple)
    if repo is not None:
        text = _make_expand_include_functions(text, repo)
    return text


def _make_eval_condition(kind: str, rest: str,
                         variables: Dict[str, Optional[str]],
                         simple: Dict[str, bool],
                         repo: Optional[Path] = None) -> bool:
    # 条件行里的 # 注释与变量赋值同口径：奇数个反斜杠转义 #，偶数个
    # 开始注释。`ifeq ($(X),a\#b)` 的右值实际是 a#b（反斜杠被吃掉），
    # 不能按普通文本原样保留。
    rest = _make_strip_value_comment(rest).strip()
    if kind in ("ifdef", "ifndef"):
        name = _make_expand_condition_text(rest, variables, simple,
                                           repo).rstrip()
        if any(ch.isspace() for ch in name):
            # ifdef 的变量名展开后必须是单个词；`ifdef X Y` 会让
            # make 报 invalid syntax in conditional 并停止读取。
            raise _MakeRequiredIncludeError("invalid conditional")
        value = variables.get(name)
        defined = value is not None and value != ""
        return defined if kind == "ifdef" else not defined
    left, right, _strip_comma_spaces = _make_ifeq_args(rest)
    if left is None:
        # ifeq/ifneq 参数缺失、括号未闭合或缺少逗号都是读取期错误，
        # 即使文件后面有 test 目标 make 也不会执行。
        raise _MakeRequiredIncludeError("invalid conditional")
    left = _make_expand_condition_text(left, variables, simple, repo)
    right = _make_expand_condition_text(right, variables, simple, repo)
    # 括号写法的语法空白已在 _make_ifeq_args 里、变量展开前去掉；
    # 引号写法保留引号内的空白（ifeq "a " "a" 不相等）。
    equal = left == right
    return equal if kind == "ifeq" else not equal


def _make_apply_conditional(kind: str, rest: str, stack: List[dict],
                            variables: Dict[str, Optional[str]],
                            simple: Dict[str, bool],
                            repo: Optional[Path] = None) -> None:
    if kind == "endif":
        if not stack:
            # 没有可配对的 ifeq/ifdef：make 报 extraneous 'endif' 并停止
            # 解析，任何 test 目标都不会被执行。
            raise _MakeRequiredIncludeError("extraneous endif")
        stack.pop()
        return
    if kind == "else":
        if not stack:
            # 没有可配对的 ifeq/ifdef：make 报 extraneous 'else' 并停止
            raise _MakeRequiredIncludeError("extraneous else")
        frame = stack[-1]
        nested = _MAKE_CONDITIONAL_LINE.match(rest.strip())
        if (nested is not None
                and nested.group(1) in ("ifeq", "ifneq", "ifdef", "ifndef")):
            # else if... 是 else 的变体，但不结束条件块；同一个条件里
            # 可以连续出现多个 else if，只有普通 else 之后不能再接。
            if frame["plain_else"]:
                raise _MakeRequiredIncludeError("only one else per conditional")
            cond = False
            if frame["parent"] and not frame["taken"]:
                cond = _make_eval_condition(nested.group(1),
                                            nested.group(2) or "",
                                            variables, simple, repo)
            active = frame["parent"] and not frame["taken"] and cond
        else:
            if frame["plain_else"]:
                # make: only one 'else' per conditional
                raise _MakeRequiredIncludeError("only one else per conditional")
            frame["plain_else"] = True
            active = frame["parent"] and not frame["taken"]
        frame["active"] = active
        frame["taken"] = frame["taken"] or active
        return
    parent = not stack or stack[-1]["active"]
    cond = (_make_eval_condition(kind, rest, variables, simple, repo)
            if parent else False)
    active = parent and cond
    stack.append({"parent": parent, "taken": active, "active": active,
                  "plain_else": False})


def _make_rewrite_define_refs(text: str, name: str, alias: str) -> str:
    """把非简单变量名的引用改写成静态探测可展开的别名。

    make 允许 `define X?` 这类名字，但 `_MAKE_VAR_REF` 与第二遍的
    `_make_expand_simple_vars` 只认常规变量名。define 处补一行别名赋值，
    再把后续 `$(X?)` / `${X?}`（含替换引用）改成 `$(__xuen_define_N)`，
    规则头才能正常展开。
    """
    if any(ch in name for ch in "$(){}\r\n"):
        return text
    pattern = re.compile(
        r"(?<!\$)\$([({])" + re.escape(name) + r"(?=[:)}])")
    return pattern.sub(lambda match: "$" + match.group(1) + alias, text)


def _make_text_with_includes(text: str, repo: Path,
                             seen: Optional[set] = None,
                             depth: int = 0,
                             variables: Optional[Dict[str, Optional[str]]] = None,
                             simple: Optional[Dict[str, bool]] = None,
                             aliases: Optional[Dict[str, str]] = None) -> str:
    """读取 include 文件并丢弃未生效条件分支，供目标探测使用。

    只读取仓库内已存在的普通文件；include 文件名支持简单变量、通配符
    与 `$(wildcard ...)`。`include` 的文件缺失或不可读时 make 会在执行
    test 前以退出码 2 失败，不能把主 Makefile 里同时存在的 test 目标
    当成可用套件（否则会被 run_suite 误判成测试失败）；`-include` /
    `sinclude` 的缺失文件按 make 语义忽略。条件分支按 ifeq/ifneq/ifdef/
    ifndef/else/endif 静态求值，未生效分支里的 include 不会误读，也不会
    把其中的 test 目标当成可用套件。
    """
    if seen is None:
        seen = set()
    if aliases is None:
        aliases = {}
    if variables is None:
        # make 内置 CURDIR 是执行目录的绝对路径（探测时即 repo）。
        # include $(CURDIR)/tests.mk 很常见，不预置会因未展开变量而跳过。
        variables = {"CURDIR": str(repo.resolve())}
        simple = {"CURDIR": True}
    elif simple is None:
        simple = {}
    if depth > 20:
        return text
    text = _make_join_continuations(text)
    lines = text.splitlines(keepends=True)
    out: List[str] = []
    stack: List[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        body = line.rstrip("\r\n")
        if body.startswith("\t"):
            if not stack or stack[-1]["active"]:
                out.append(line)
            i += 1
            continue
        # define 体是变量值而不是 Makefile 语法：里面的 include/test 目标
        # 要等 $(eval ...) 展开才生效，静态探测不能把它们当成真实指令。
        # 无论 define 位于生效还是未生效分支，都先按词法配对跳过整个块；
        # 否则未生效分支里的 include missing.mk 会误触发必需 include 错误，
        # 生效分支里的 test: 又会把 define 体误判成测试目标。
        active = not stack or stack[-1]["active"]
        define_match = _MAKE_DEFINE_LINE.match(body)
        if define_match is not None:
            # define 的变量名会先展开；空名称（`define` / `define = x` /
            # `define $(UNDEFINED)`）会让 make 直接报错，后面的 test 目标
            # 不会执行。`define X = x` 这类带赋值符/尾随文本的写法只警告，
            # 名称非空仍按合法 define 处理。未生效分支里的 define 虽被
            # 跳过，但仍需做词法配对，不能校验名称。
            define_name = ""
            if active:
                name_text = _make_strip_value_comment(
                    define_match.group(1) or "").strip()
                # `define X = x` 只警告并定义 X，赋值符后的文本不是名称。
                for op in (":::=", "::=", ":=", "?=", "+=", "!=", "="):
                    found = name_text.find(op)
                    if found >= 0:
                        name_text = name_text[:found].rstrip()
                        break
                define_name = _make_expand_refs(name_text, variables, simple)
                if (not define_name.strip()
                        or _MAKE_DEFINE_EMPTY_NAME.match(
                            define_name.strip())):
                    raise _MakeRequiredIncludeError("empty define name")
            define_depth = 1
            body_lines: List[str] = []
            i += 1
            endef_pattern = (_MAKE_ENDEF_LINE if active
                             else _MAKE_ENDEF_LINE_STRICT)
            while i < len(lines) and define_depth:
                inner = lines[i].rstrip("\r\n")
                if _MAKE_DEFINE_LINE.match(inner):
                    define_depth += 1
                    body_lines.append(inner)
                elif endef_pattern.match(inner):
                    define_depth -= 1
                    if define_depth:
                        body_lines.append(inner)
                else:
                    body_lines.append(inner)
                i += 1
            if define_depth:
                # 缺少 endef：make 在读取阶段直接报错并停止，后面的 test
                # 目标（以及 define 之前的目标）都不会被执行。
                raise _MakeRequiredIncludeError("missing endef")
            if active:
                # define 定义的是递归变量，体里的换行原样保留。
                variables[define_name] = "\n".join(body_lines)
                simple[define_name] = False
                # 保留 define 块交给第二遍展开；变量名含 ? 等特殊字符
                # 时改用可被 _MAKE_VAR_REF 识别的别名，并把引用改写过去。
                target_name = define_name
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", define_name):
                    index = len(aliases)
                    while (f"__xuen_define_{index}" in variables
                           or f"__xuen_define_{index}" in aliases.values()):
                        index += 1
                    target_name = f"__xuen_define_{index}"
                    aliases[define_name] = target_name
                # 保留真正的多行值（而不是压成占位赋值），第二遍展开
                # 目标头时才能让 firstword/lastword/strip 等函数看到与
                # make 相同的空白和换行。
                out.append(f"define {target_name}\n")
                for body_line in body_lines:
                    out.append(body_line + "\n")
                out.append("endef\n")
            continue
        if active and _MAKE_ENDEF_LINE.match(body):
            # 生效分支里未处于 define 块中的 endef 是游离指令：make 报
            # missing separator 并停止解析。未生效分支里的 endef 会被
            # 直接忽略（不会报错），不能据此拒绝后面的 test 目标。
            raise _MakeRequiredIncludeError("extraneous endef")
        conditional = _MAKE_CONDITIONAL_LINE.match(body)
        if conditional is not None:
            _make_apply_conditional(conditional.group(1),
                                    conditional.group(2) or "", stack,
                                    variables, simple, repo)
            i += 1
            continue
        if stack and not stack[-1]["active"]:
            i += 1
            continue
        include = _MAKE_INCLUDE_LINE.match(body)
        if include is not None:
            logical = body
            while _make_line_continues(logical):
                logical = logical[:-1]
                if i + 1 >= len(lines):
                    break
                i += 1
                logical += " " + lines[i].rstrip("\r\n")
            include = _MAKE_INCLUDE_LINE.match(logical)
            if include is None:
                i += 1
                continue
            directive = include.group(1)
            args = _make_expand_refs(include.group(2), variables, simple)
            args = _make_expand_include_functions(args, repo)
            for name in _make_include_names(args):
                display = _make_unescape_name(name)
                absolute_name = Path(display).is_absolute()
                for path in _make_include_paths(name, repo):
                    try:
                        key = path.resolve()
                        if key in seen:
                            continue
                        if not path.is_file():
                            # 悬空符号链接的 exists() 为 False，与 make 的
                            # 「缺失」口径一致；目录等存在但不可读的路径
                            # 两种 include 都报错。
                            if path.exists() or directive == "include":
                                raise _MakeRequiredIncludeError(display)
                            continue
                        if path.stat().st_size > 2_000_000:
                            continue
                        included = path.read_text(encoding="utf-8-sig",
                                                  errors="replace")
                    except _MakeRequiredIncludeError:
                        raise
                    except (OSError, ValueError, RuntimeError):
                        raise _MakeRequiredIncludeError(display) from None
                    seen.add(key)
                    # MAKEFILE_LIST 按读取顺序追加：include 文件里的
                    # `$(lastword $(MAKEFILE_LIST))` 和之后的主文件都要
                    # 看到刚读入的文件名（与 make 一致）。通配符 include
                    # 要记录实际匹配到的文件名，而不是 `*.mk` 这样的原始
                    # 表达式；`./foo.mk` 也按 make 语义规整成 `foo.mk`。
                    if absolute_name:
                        listed = str(path)
                    else:
                        try:
                            listed = os.path.relpath(str(path), str(repo))
                        except ValueError:
                            listed = str(path)
                    makefile_list = variables.get("MAKEFILE_LIST")
                    if makefile_list is not None:
                        variables["MAKEFILE_LIST"] = (
                            (makefile_list + " " + listed).strip())
                    try:
                        out.append("\n")
                        out.append(_make_text_with_includes(
                            included, repo, seen, depth + 1, variables,
                            simple, aliases))
                        out.append("\n")
                    finally:
                        # 只把「正在处理」的文件留在 seen 里，防止 include
                        # 环无限递归；同一文件在前后两次 include 中仍应
                        # 按 make 语义各处理一次（条件分支可能因变量变化
                        # 而不同）。
                        seen.discard(key)
            i += 1
            continue
        out.append(line)
        _make_scan_assignment(body, variables, simple)
        i += 1
    if stack:
        # 条件块没在文件内闭合：make 报 missing 'endif' 并停止解析。
        # 条件不能跨 include 文件（GNU make 同样在文件末尾报错）。
        raise _MakeRequiredIncludeError("missing endif")
    result = "".join(out)
    for name, alias in aliases.items():
        result = _make_rewrite_define_refs(result, name, alias)
    return result


def _is_pytest_file(name: str) -> bool:
    return (name.endswith(".py")
            and (name.startswith("test_") or name.endswith("_test.py")))


def _has_pytest_file(repo: Path) -> bool:
    for dirpath, dirnames, filenames in os.walk(repo):
        # 与 pytest 默认 norecursedirs 对齐：点目录、build/dist、虚拟环境
        # 和依赖目录不会被 `pytest -q` 收集，只按它们探测会得到「有测试
        # 套件」的假阳性，随后运行 pytest 以「未收集到测试」退出。
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in _PYTEST_SKIP_DIRS
            # pytest 的 norecursedirs 还包含通配模式 *.egg（如
            # pkg.egg/）：安装产物里的测试同样不会被收集，探测时必须
            # 跳过，否则只命中这种目录的仓库会以退出码 5「无测试可收集」
            # 被误判成测试失败
            and not d.endswith(".egg")
        ]
        if any(_is_pytest_file(name) for name in filenames):
            return True
    return False


def _has_go_package(repo: Path) -> bool:
    """模块内是否有 `go test ./...` 会匹配到的 .go 文件。

    与 go 工具的忽略规则对齐：以 . 或 _ 开头的目录/文件名、testdata
    目录，以及任意层级的 vendor 目录都不会被 `./...` 匹配。只命中这些
    位置的仓库会以「matched no packages」（退出码 1）失败——探测成套件
    会把「没有可用测试」误记成测试失败并拒绝候选。
    """
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith((".", "_")) and d not in ("vendor", "testdata")
        ]
        if any(name.endswith(".go") and not name.startswith((".", "_"))
               for name in filenames):
            return True
    return False


def detect_test_suite(repo: Path) -> Optional[List[str]]:
    """按 pytest → make test → npm test → go test 的顺序探测可运行套件。

    返回 argv 列表；没有任何可运行套件时返回 None（此时「不能用测试
    验证」，由调用方转用户/AI 评分）。探测只做静态存在性检查，不真正
    执行测试，代价极低，每轮重探一次也没问题（工作区里新出现 tests/
    的下一轮就会被纳入测试验证）。
    """
    if not repo.is_dir():
        return None
    # 1) pytest：仓库任意子目录有 test_*.py / *_test.py，且本机装了 pytest。
    #    只查根目录和 tests/ 会漏掉 src/pkg/tests/ 等标准布局（而 go 分支
    #    已支持嵌套包）；目录名恰好叫 test_x.py 的也不能算测试文件。
    if _has_pytest_file(repo) and _find_spec("pytest"):
        return [sys.executable, "-m", "pytest", "-q"]
    # 2) make test：Makefile 里定义了 test 目标。GNU make 按
    #    GNUmakefile → makefile → Makefile 的顺序取第一个存在的文件；
    #    只查 Makefile 会漏掉合法的 lowercase/GNUmakefile 套件，也会在
    #    GNUmakefile 覆盖 Makefile 时按后者误判。只认精确的 test 目标：
    #    test-unit / test-ci 之类后缀目标不算——探测命中后会执行
    #    `make test`，而 Makefile 里根本没有 test 目标时 make 以退出码 2
    #    失败，run_suite 会把它当成「测试失败」拒绝候选，连 auto 模式的
    #    兜底评分（user/ai）都被跳过；该场景应属「没有可运行套件」。
    #    变量赋值（test := / ?= / += / != / ::=）与 test: = x 这类空变量名
    #    同样不是目标：make test 会以退出码 2 失败，必须按无套件处理。
    #    target-specific 赋值（test: X=1）只作用于目标，本身不定义可执行
    #    目标；但 test::: / test: a:b 等非法规则头会让 make 读取失败，
    #    即使别处有 test 目标也按无套件处理。
    #    搜索顺序按「路径存在」而不是「是普通文件」判断：GNU make 遇到
    #    GNUmakefile 是目录 / 悬空符号链接时同样先选中它、随后以退出码
    #    2 失败，不会跳过它去读 Makefile。若这里用 is_file 跳过坏条目，
    #    探测会命中 Makefile 并执行必然失败的 make test，把候选误判成
    #    测试失败；坏条目存在时应按「没有可运行套件」处理。
    makefile = next(
        (repo / name for name in ("GNUmakefile", "makefile", "Makefile")
         if os.path.lexists(repo / name)), None)
    if (makefile is not None and makefile.is_file()
            and shutil.which("make")):
        try:
            # utf-8-sig：Windows 编辑器保存的 Makefile 常带 BOM；GNU make
            # 会忽略 BOM 并照常执行 test 目标，按 utf-8 读取则 BOM 粘在
            # "test" 前、正则失配，可运行的套件被误判成没有测试
            text = makefile.read_text(encoding="utf-8-sig",
                                      errors="replace")
            text = _make_text_with_includes(
                text, repo, {makefile.resolve()}, 0,
                {"CURDIR": str(repo.resolve()),
                 "MAKEFILE_LIST": makefile.name},
                {"CURDIR": True, "MAKEFILE_LIST": True})
            text = _make_expand_simple_vars(text, repo)
            if _make_defines_test_target(text, repo):
                return ["make", "test"]
        except (_MakeRequiredIncludeError, OSError):
            pass
    # 3) npm test：package.json 声明了非占位的 test 脚本
    pkg = repo / "package.json"
    # 用 which 解析出的完整路径而不是裸 "npm"：Windows 上 npm 实际是
    # npm.cmd，CreateProcess 对无扩展名的程序只补 .exe，裸 "npm" 会以
    # WinError 2 启动失败，套件被误判成不可用（tests 模式永远挂起）。
    npm = shutil.which("npm") if pkg.is_file() else None
    if npm:
        try:
            # JSON 合法但结构不对（顶层是 list、scripts 是 list/str 等）
            # 都按「没有 npm 套件」处理：这类脏数据不能把探测整个打断。
            # utf-8-sig：npm 自己忽略 package.json 的 UTF-8 BOM 并正常
            # 执行 test 脚本，按 utf-8 读取却会让 json.loads 报 BOM 错误
            data = json.loads(pkg.read_text(encoding="utf-8-sig",
                                            errors="replace"))
            scripts = data.get("scripts") if isinstance(data, dict) else None
            test_cmd = scripts.get("test") if isinstance(scripts, dict) else None
            if isinstance(test_cmd, str) and test_cmd.strip() \
                    and "no test specified" not in test_cmd:
                return [npm, "test"]
        except (OSError, ValueError):
            pass
    # 4) go test：go.mod 模块下任意位置（根目录或 cmd/、internal/ 等
    #    子包）有 go 工具会匹配的 .go 文件。没有 go.mod 时不管 .go 在根
    #    目录还是子目录都不算：从仓库根执行 `go test ./...` 在模块模式下
    #    会因找不到 go.mod 失败，探测成套件只会把「没有可用测试」误记成
    #    测试失败。vendor/testdata/._ 开头目录里的文件另见 _has_go_package。
    if (shutil.which("go") and (repo / "go.mod").is_file()
            and _has_go_package(repo)):
        return ["go", "test", "./..."]
    return None


# 套件停止轮询间隔：0.2s 足以让 TUI 的 q / Ctrl+C 及时兑现，又不空转 CPU
_SUITE_POLL_SECONDS = 0.2


def _is_pytest_run(argv: List[str]) -> bool:
    """argv 是否为本模块探测出的 pytest 调用（sys.executable -m pytest ...）。"""
    return len(argv) >= 3 and argv[1] == "-m" and argv[2] == "pytest"


def _is_go_test_run(argv: List[str]) -> bool:
    """argv 是否为本模块探测出的 go test 调用（go test ./...）。"""
    return len(argv) >= 2 and argv[0] == "go" and argv[1] == "test"


def _is_make_test_run(argv: List[str]) -> bool:
    """argv 是否为本模块探测出的 make test 调用。"""
    return (len(argv) == 2 and argv[1] == "test"
            and os.path.basename(argv[0]).lower()
            in ("make", "gmake", "make.exe", "gmake.exe"))


# GNU make 4.x：No rule to make target 'test'.
# GNU make 3.81（macOS）：No rule to make target `test'.
_MAKE_MISSING_TEST_TARGET = re.compile(
    r"No rule to make target [`'\"`]test[`'\"`]")


def _make_missing_test_target(detail: str) -> bool:
    """make test 是否因「没有 test 目标」而失败（不是测试失败）。

    探测是静态读 Makefile 的：target 写在 ifeq/ifdef 等条件分支里、而
    当前环境走的正是另一支时，静态命中但实际没有该目标，`make test` 以
    退出码 2 报「No rule to make target 'test'」。这与「make test 跑了但
    命令失败」同码，不能按测试失败拒绝候选——按套件不可用处理。只匹配
    目标名为 test 的报错，缺前置目标（needed by 'test'）等仍按失败处理。
    """
    return _MAKE_MISSING_TEST_TARGET.search(detail) is not None


# GNU make 4.x：Nothing to be done for 'test'. / 'test' is up to date.
# GNU make 3.81（macOS）：Nothing to be done for `test'. / `test' is up to date.
# 只认顶层 make（不带 [n] 前缀）：子 make 无事可做不代表外层 test 没跑测试。
_MAKE_NOOP_TEST_TARGET = re.compile(
    r"(?m)^(?:make|gmake)(?:\.exe)?: "
    r"(?:Nothing to be done for [`'\"]test[`'\"]\.|"
    r"[`'\"]test[`'\"] is up to date\.)[ \t]*$")


def _make_noop_test_target(detail: str) -> bool:
    """make test 是否退出 0 但根本没有执行测试。

    空的 `test:` 目标、已存在的同名文件/目录、以及 target 只写在未生效
    条件分支里而工作区恰有 test 文件时，`make test` 都以 0 退出并打印
    「Nothing to be done for 'test'」/「'test' is up to date」。这不是
    「测试全部通过」：tests 模式会把完全未验证的候选直接采纳为最佳，
    auto 模式也会跳过兜底评分。按套件不可用处理，与 pytest 退出码 5、
    go 全部 [no test files] 同口径。
    """
    return _MAKE_NOOP_TEST_TARGET.search(detail) is not None


def _go_matched_no_packages(detail: str) -> bool:
    """go test 的输出是否是「没有匹配到任何包」（不是测试失败）。

    go 对 `./...` 未匹配到包时依次打印 `go: warning: "./..." matched
    no packages` 与 `no packages to test` 并以退出码 1 结束。要求两行
    同时出现，避免把测试自身碰巧打印的同名文本当成 go 的诊断。
    """
    return ("matched no packages" in detail
            and "no packages to test" in detail)


_GO_NO_TEST_FILES_LINE = re.compile(
    r"^\?\s+\S+\s+\[no test files\]\s*$", re.MULTILINE)


def _go_no_tests_ran(detail: str) -> bool:
    """go test 是否一个测试都没跑（所有匹配到的包都 [no test files]）。

    模块里有 .go 源码但没有任何 *_test.go 时，`go test ./...` 会为每个包
    打印 `?   pkg\t[no test files]` 并以退出码 0 结束。这与 pytest 退出码
    5 同义：编译通过不等于测试验证，不能当成「测试全部通过」——tests
    模式会把完全未验证的候选直接采纳为最佳，auto 模式也会跳过兜底评分。
    只有出现了 go 自己的 [no test files] 行、且没有任何包打印 ok/FAIL
    时才这样判定；混有真实测试的模块会打印 ok 行，不受影响。
    """
    if not _GO_NO_TEST_FILES_LINE.search(detail):
        return False
    return not re.search(r"^(?:ok|FAIL)[ \t]", detail, re.MULTILINE)


def run_suite(argv: List[str], repo: Path, timeout: float,
              stop: Optional[Callable[[], bool]] = None) -> SuiteResult:
    """运行测试套件。退出码 0 = 通过；非 0 = 失败；超时 = 失败（保守：
    宁可不采纳候选，也不让超时的测试把可能损坏的产物放进最佳）。
    pytest 的退出码 5（未收集到测试）与 go 的「matched no packages」（构建
    约束/忽略规则排除了全部包）、「全部包都是 [no test files]」（没有任何
    *_test.go），以及 make 因条件分支未生效而报「No rule to make target」
    例外：按套件不可用返回，不拒绝候选。

    stop：可选的「是否请求停止」回调。传入时按短间隔轮询，回调一旦
    为真就终止整个进程组并返回 stopped=True（available=False）——
    TUI 里按 q / Ctrl+C 时若守卫正阻塞在套件上，worker 会跑满
    verify_timeout（默认 600s），而 run_tui 只等 20s：用户主动退出被
    误报成退出码 1，被丢下的测试进程还会作为孤儿继续跑。

    与 subprocess.run 的差异：自己拉起进程并借 procs.kill_process_tree
    整组终止，测试拉起的子孙进程（xfail 子进程、npm/go 的子孙）不会
    泄漏；KeyboardInterrupt 等 BaseException 也先收尾再传播（与
    subprocess.run 的兜底行为一致）。"""
    if stop is not None and stop():
        return SuiteResult(available=False, stopped=True,
                           reason="用户请求停止，未验证")
    # make 的诊断文本随 locale 变化（中文环境是「无需做任何事」），而
    # _make_noop_test_target / _make_missing_test_target 按英文 GNU make
    # 输出判断。只对 make 固定 C locale，让「没跑测试」的判定与 CI 一致；
    # pytest/npm/go 仍继承用户 locale。
    env = None
    if _is_make_test_run(argv):
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        env["LANGUAGE"] = "C"
    try:
        proc = subprocess.Popen(
            argv, cwd=str(repo),
            # 与 ShellAgent.run 同口径隔离 stdin：TUI 模式下 textual 从
            # stdin 读键盘，测试套件若也读 stdin 会抢键（测试的 input()
            # 还会一直等不到输入、把守卫挂到 verify_timeout）。外部 agent
            # 早已用 DEVNULL，套件不能例外。
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env,
            **popen_kwargs(),
        )
    except (OSError, ValueError):
        # 探测时存在、运行时却拉不起来（PATH 变化 / 权限 ……）
        return SuiteResult(available=False, reason="测试命令无法启动")
    deadline = time.monotonic() + timeout
    stopped = False
    out = ""
    try:
        while True:
            try:
                # communicate 在 TimeoutExpired 后可安全重试，输出累积不丢
                out, _ = proc.communicate(timeout=_SUITE_POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                if stop is not None and stop():
                    stopped = True
                    kill_process_tree(proc)
                    _reap_suite(proc)
                    break
                if time.monotonic() >= deadline:
                    kill_process_tree(proc)
                    _reap_suite(proc)
                    return SuiteResult(available=True, ok=False,
                                       reason=f"测试超时（>{timeout:g}s）")
    except BaseException:
        # Ctrl+C / 进程被中断：先终止整组再传播，避免测试进程成孤儿
        # （自己拉起的进程必须自己收尾，subprocess.run 也是这么兜底的）
        kill_process_tree(proc)
        _reap_suite(proc)
        raise
    if stopped:
        return SuiteResult(available=False, stopped=True,
                           reason="用户请求停止，未验证")
    detail = (out or "").strip()
    if proc.returncode == 0:
        # go test 在没有测试文件时同样以 0 退出（逐包打印 [no test files]），
        # 不能当「测试通过」：与 pytest 退出码 5 同义，按套件不可用处理，
        # 交给调用方转兜底评分（auto）或挂起（tests）
        if _is_go_test_run(argv) and _go_no_tests_ran(detail):
            return SuiteResult(available=False, ok=False,
                               reason="go 没有可执行的测试（全部为 no test files）",
                               detail=detail)
        if _is_make_test_run(argv) and _make_noop_test_target(detail):
            return SuiteResult(available=False, ok=False,
                               reason="make test 没有执行任何测试（目标无事可做）",
                               detail=detail)
        return SuiteResult(available=True, ok=True, reason="exit 0", detail=detail)
    tail = "\n".join(detail.splitlines()[-15:])
    if proc.returncode == 5 and _is_pytest_run(argv):
        # pytest 文档定义的退出码 5：没有收集到任何测试。仓库里的
        # test_*.py 可能被 pytest 配置（python_files / testpaths /
        # addopts --ignore 等）整体排除，此时并没有「测试失败」，而是
        # 没有可执行的验证——按套件不可用处理，交给调用方转兜底评分
        # （auto）或挂起（tests），不能误拒候选
        return SuiteResult(available=False, ok=False,
                           reason="pytest 未收集到测试（退出码 5）",
                           detail=tail)
    if _is_go_test_run(argv) and _go_matched_no_packages(detail):
        # 仓库里的 .go 文件被构建约束（//go:build windows 等）或 go 的
        # 忽略规则整体排除时，`go test ./...` 以退出码 1 报「matched no
        # packages」——同样不是测试失败，而是没有可执行的验证。按套件
        # 不可用处理，交给调用方转兜底评分（auto）或挂起（tests）
        return SuiteResult(available=False, ok=False,
                           reason="go 未匹配到任何包",
                           detail=tail)
    if _is_make_test_run(argv) and _make_missing_test_target(detail):
        # Makefile 的 test 目标写在未生效的条件分支里时，静态探测会误以为
        # 有套件，make test 以退出码 2 报「No rule to make target 'test'」。
        # 与 make 跑测试失败同码，不能据此拒绝候选——按套件不可用处理
        return SuiteResult(available=False, ok=False,
                           reason="make 没有 test 目标", detail=tail)
    return SuiteResult(available=True, ok=False,
                       reason=f"退出码 {proc.returncode}", detail=tail)


def _reap_suite(proc: subprocess.Popen) -> None:
    """回收被终止的套件进程（communicate 顺带读尽残留输出并 wait）。"""
    try:
        proc.communicate(timeout=5)
    except (subprocess.TimeoutExpired, ValueError):
        pass


def resolve_repo(explicit: str, workspace: Path) -> Path:
    """测试验证的目标目录：显式配置优先；否则从工作区向上找 git 仓库根；
    都没有就用工作区本身（独立研究工作区通常没有测试，自然转评分兜底）。"""
    if explicit and explicit.strip():
        return Path(explicit).expanduser().resolve()
    d = workspace.resolve()
    for p in (d, *d.parents):
        if (p / ".git").exists():
            return p
    return d


# ----------------------------------------------------------------------
# 轮次守卫主体
@dataclass
class _Stats:
    rounds: int = 0
    candidates: int = 0
    adopted: int = 0
    rejected: int = 0
    pending: int = 0
    heartbeat: int = 0
    skipped: int = 0
    restored: int = 0


class RoundGuard:
    """研究循环的轮次守卫。用法（runner 集成处）：

        guard = RoundGuard(cfg, task, state_path, workspace, sink)
        guard.start()                    # 建目录、基线最佳、应用待决评分
        for i in rounds:
            agent.run(...)
            guard.on_round_end(i)        # 快照→验证→晋升/还原
            #（agent 失败的轮次改调 guard.on_round_failed(i, reason)）
        guard.finish()                   # 收尾：再应用一次待决评分 + 汇总

    suite_runner / judge 两个参数是可注入的测试接缝（tests/ 里用它们
    伪造测试结果与评审员输出，避免真实跑 pytest / 外部 agent）。
    suite_runner 传 None 时使用默认 run_suite，并接上 sink.should_stop：
    TUI 按 q / Ctrl+C 才能终止正在运行的测试套件（见 _run_suite）。
    """

    def __init__(
        self,
        cfg: Config,
        task: str,
        state_path: Path,
        workspace: Path,
        sink: Sink,
        *,
        suite_runner: Optional[Callable[[List[str], Path, float], SuiteResult]] = None,
        judge: Optional[Callable[[str], Tuple[bool, str]]] = None,
    ):
        self.cfg = cfg
        self.task = task
        self.state_path = state_path
        self.workspace = workspace
        self.sink = sink
        rc = cfg.rounds
        self.dir = (workspace / rc.dir).resolve()
        self.history_path = self.dir / HISTORY_NAME
        self.best_md = self.dir / BEST_MD_NAME
        self.best_json = self.dir / BEST_JSON_NAME
        self.verdicts_path = self.dir / VERDICTS_NAME
        self.repo = resolve_repo(rc.repo, workspace)
        self._suite_runner = suite_runner
        self._judge_override = judge
        self.best: Dict = {}
        self.stats = _Stats()
        # 本会话里挂起、可被 verdicts.txt 补分改判的候选；补分兑现时
        # 统计要从「待评分」桶迁走，否则汇总与晋升日志自相矛盾
        self._pending_ids: set = set()
        # 本轮已快照、但还没有终结结论（adopted/rejected/pending）的候选
        # id：任何未被现有分支覆盖的 BaseException（最典型的是 Ctrl+C 正好
        # 落在 sink 输出等点上）都会带着 candidates 已 +1、三个结论桶全 0
        # 的统计逃出去，违反 adopted+rejected+pending==candidates；而
        # on_round_failed 看到轮次已处理只会补做还原，无法弥补统计
        self._inflight_cid: Optional[str] = None
        # 本会话已计入 adopted / rejected 的候选 id（挂起另有 _pending_ids
        # 跟踪）：兜底记账据此幂等，已决候选绝不再补记成待评分
        self._settled_cids: set = set()
        # 本会话已计入各结论桶的候选 id。集合成员是计数是否生效的权威
        # 依据：中断可能落在「统计 +1」与「settled 标记」之间，单看 int
        # 无法区分是否已计入；_sync_counts 可据此幂等对账
        self._adopted_ids: set = set()
        self._rejected_ids: set = set()
        # 本会话内已由 on_round_end 处理（或已按失败/中断记账）的轮次：
        # KeyboardInterrupt 可能晚于守卫处理到达，on_round_failed 再记一遍
        # 会让轮次数/跳过数虚增、审计日志为同一轮记出自相矛盾的候选+跳过
        self._handled_rounds: set = set()
        self._hinted = False  # 「如何评分」提示只打印一次
        # verdicts.txt 里引用未知候选 id 的行：每个 id 只警告一次
        self._warned_unknown_cids: set = set()
        # 本会话已兑现的评分：判定事件写盘失败（磁盘满）时历史里没有
        # 「已决」标记，仅靠 _read_events 的 resolved 会让同一行评分在
        # 下一次 start/finish/每轮兑现时被重复应用（拒绝统计翻倍、采纳
        # 重复写盘）。内存集合与事件写入解耦，写盘失败也不重复兑现。
        self._applied_verdicts: set = set()
        # 评分解析不出的行：同样每个 id 只警告一次（_apply_user_verdicts
        # 在每轮开始/结束时都会兑现，inf 循环里每轮重复刷同一行警告会
        # 淹没真正的循环输出）
        self._warned_badscore_cids: set = set()

    # ---- 基础设施 ----
    def _append_event(self, ev: Dict) -> None:
        ev = dict(ev)
        ev.setdefault("ts", _ts())
        line = json.dumps(ev, ensure_ascii=False) + "\n"
        # 追加前确保文件以换行结尾：上一次写入若在 ENOSPC / 进程被杀时
        # 中途截断，记录里会留下无结尾换行的残行；直接追加会把新事件与
        # 残行拼成一行，_read_events 逐行解析时【两条】都会被当坏行跳过
        # ——审计日志、_recover_best 的恢复源、_apply_user_verdicts 的
        # 已决/未决判定会一起丢失。补一个换行让残行独立成行（保留可人工
        # 检查），新事件照常可读。单个 "a+b" 句柄上先 seek 再读末尾一位，
        # 避免「两次打开文件」之间被并发实例插入写入。
        with open(self.history_path, "a+b") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.seek(0, os.SEEK_END)
                    f.write(b"\n")
            f.write(line.encode("utf-8"))

    def _read_events(self) -> List[Dict]:
        events: List[Dict] = []
        try:
            raw = self.history_path.read_bytes()
        except OSError:
            return events
        # 单个坏字节（写盘中途被杀 / 磁盘满留下的半截多字节字符）不能让
        # 整份审计日志不可读：errors="replace" 只影响坏字节所在的那一行
        # （JSON 语法坏掉的行照常被跳过），其余事件照常解析。历史是
        # _recover_best 的恢复源、_apply_user_verdicts 的「已决」判定依据，
        # 一字节损坏就整份丢失会让最佳元数据被重建为基线、已决拒绝被翻案。
        # 换行字节 0x0A/0x0D 不可能出现在多字节 UTF-8 序列内部，逐行结构
        # 不受影响。只按 ASCII 换行切分（兼容外部编辑器转成 CRLF/CR 的
        # 文件）：str.splitlines 还会在 U+2028/U+2029/U+0085 等 Unicode
        # 行分隔符处切开，而 json.dumps(ensure_ascii=False) 不会转义它们
        # ——任务名/评语里含这些字符时，一条合法 JSON 事件会被拆成两半并
        # 整体丢失（审计日志与 best 恢复源一起少一条记录）。
        for line in re.split(r"\r\n|\r|\n",
                             raw.decode("utf-8-sig", errors="replace")):
            line = line.strip().lstrip("\ufeff").strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue  # 坏行跳过：审计日志绝不因为个别损坏行整体不可读
            if isinstance(ev, dict):
                events.append(ev)
        return events

    def _load_best(self) -> Dict:
        """读取 best.json；缺失/损坏/字段不合法（见 _valid_best）返回 {}。

        返回 {} 而不是未知占位：start() 据「best.md 存在但元数据不可用」
        走 _recover_best() 恢复，避免「最佳」永远停在 unknown——拒绝与
        挂起的轮次不会更新 best，汇总/评审提示词会持续失真。
        """
        try:
            data = json.loads(self.best_json.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}
        return data if _valid_best(data) else {}

    def _best_from_history(self, *, require_snapshot: bool = False) -> Optional[Dict]:
        """从 history.jsonl 最后一条基线/采纳事件恢复元数据（无副作用）。

        历史行被外部编辑/其他工具写入时字段类型可能损坏（id 是列表、
        round 是字符串、score 是文本……）：与 best.json 的加载校验
        （_valid_best）用同一口径，类型不对的事件不能恢复成最佳元数据
        ——否则回写的 best.json 下次启动仍会被拒绝，每次都走恢复分支；
        非字符串 id 还会让展示/事件关联出现异常值。

        require_snapshot=True 时只返回候选快照仍完整可读的最佳：调用方
        要拿快照当内容源（best.md 丢失），仅有元数据不够。
        """
        for ev in reversed(self._read_events()):
            if ev.get("event") == "baseline":
                best = {"id": ev.get("id"), "round": 0, "verifier": "baseline",
                        "score": None, "ts": ev.get("ts", "")}
            elif ev.get("event") == "verdict" and ev.get("result") == "adopted":
                best = {"id": ev.get("id"), "round": ev.get("round", 0),
                        "verifier": ev.get("verifier", "unknown"),
                        "score": ev.get("score"), "ts": ev.get("ts", "")}
            else:
                continue
            if not _valid_best(best):
                continue
            if require_snapshot and self._recover_best_text(best) is None:
                continue
            return best
        return None

    def _recover_best(self, *, require_snapshot: bool = False) -> Dict:
        """best.md 存在但 best.json 缺失/损坏：恢复最佳元数据并回写。

        正常提交顺序下 best.json 先于 best.md 落盘（见 start/_commit_best），
        只有外部删除/损坏 best.json 才会出现该组合。优先从 history.jsonl 的
        最后一条基线/采纳事件重建（历史只读，不追加事件）；历史也不可用时
        按 best.md 合成一条基线并补记 baseline 事件。恢复结果回写 best.json，
        后续启动直接命中；写盘失败只告警（元数据在内存中已可用，守卫照常
        工作——降级原则）。

        require_snapshot=True 用于 best.md 自身结构已损坏、不能充当内容源
        的情况：只采用候选快照仍可读的 history 最佳（当前最佳快照丢了也
        要退回较早可恢复的最佳），并从该快照自愈 best.md；否则只恢复
        元数据，内容仍以完好且可能更新的 best.md 为准。
        """
        best = self._best_from_history(require_snapshot=require_snapshot)
        if best is None and require_snapshot:
            # 没有任何可恢复的快照：仍尽量恢复最新元数据；内容只能按
            # 既有「快照不可用」口径退回脚手架，不能继续用损坏的 best.md
            best = self._best_from_history()
        baseline_only = False
        if best is None:
            best = {"id": f"baseline-{time.strftime('%Y%m%d-%H%M%S')}",
                    "round": 0, "verifier": "baseline", "score": None,
                    "ts": _ts()}
            baseline_only = True
            try:
                self._append_event({"event": "baseline", **best})
            except Exception as e:  # noqa: BLE001 —— 守卫降级原则
                self.sink.warn(f"记录基线事件失败（忽略）：{e}")
        try:
            _atomic_write(self.best_json,
                          json.dumps(best, ensure_ascii=False, indent=2))
        except OSError as e:
            self.sink.warn(f"恢复的最佳元数据写盘失败（忽略）：{e}")
        if require_snapshot:
            recovered_text = (None if baseline_only
                              else self._recover_best_text(best))
            if recovered_text is not None:
                self._heal_best_md(recovered_text)
                self.sink.warn("rounds/best.md 结构损坏，已从候选快照恢复"
                               f"可用的最佳内容（{best['id']}）")
            else:
                # 没有可恢复的内容（基线 / 快照也丢失）：把损坏的
                # best.md 重建成脚手架，后续读取不必反复走损坏回退
                self._heal_best_md(state.scaffold(self.task))
                self.sink.warn("rounds/best.md 结构损坏且没有可恢复的候选"
                               "快照：已重建为空内容")
        if baseline_only:
            self.sink.warn("rounds/best.json 与 history.jsonl 均不可用："
                           f"已重建基线最佳（{best['id']}）")
        else:
            self.sink.warn("rounds/best.json 缺失或损坏：已从 history.jsonl "
                           f"恢复最佳元数据（{best['id']}）")
        return best

    def _read_state_text(self) -> str:
        try:
            # state.read_state_file 与其它读路径同一自愈口径：非法 UTF-8
            # 按替换符降级并回写修复。这里若直接严格解码，一个坏字节会让
            # _process_round_end 把整轮当「状态文件缺失或不可读」记
            # skipped——候选快照不留、产物丢失，违反「任何一轮的产物都
            # 落在 rounds/cand-<id>.md」的承诺。只有真正读不到（文件缺失/
            # 权限/目录被占）才返回 "" 走 skipped。
            return state.read_state_file(self.state_path)
        except OSError:
            return ""

    def _sections(self, text: str) -> Tuple[str, str]:
        # 取「写入规整形态」：心跳 / 改动判定必须与 update_section_file
        # 落盘后的可读内容一致，否则含标记字面量的区块永远判为有改动，
        # 每轮都生成无意义候选并重复还原（见 _readable_section）
        return (state.sanitize_section_content(
                    state.get_section(text, state.SECTION_IDEA)),
                state.sanitize_section_content(
                    state.get_section(text, state.SECTION_ARTIFACT)))

    def _snapshot_candidate(self, round_no: int, text: str) -> str:
        """原子创建候选快照，返回实际占用的 id（撞车自动追加序号）。

        不能先算 id 再 _atomic_write：exists() 检查与写盘之间是竞态，
        同一 workspace 的两个实例在同一秒、同一轮号会算出同一 id，后写者
        用 os.replace 覆盖先写者的快照——候选快照是被拒绝/挂起候选事后在
        verdicts.txt 翻案的唯一凭据，绝不能被覆盖。O_CREAT|O_EXCL 把
        「检查 + 占用」合并为一个原子操作，跨进程并发下也不会覆盖已有快照。
        写入失败时删除半截文件：坏快照既会永久占住 id，又会被「快照可读」
        的检查误判。KeyboardInterrupt / SystemExit 同样要清掉半成品再传播。
        """
        base = f"{time.strftime('%Y%m%d-%H%M%S')}-r{round_no}"
        cid, seq = base, 2
        while True:
            path = self.dir / f"{CAND_PREFIX}{cid}.md"
            try:
                created = open(path, "x", encoding="utf-8")
            except FileExistsError:
                cid = f"{base}-{seq}"
                seq += 1
                continue
            try:
                with created as f:
                    f.write(text)
            except BaseException:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            return cid

    # ---- 生命周期 ----
    def start(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        if self.best_md.exists():
            loaded = self._load_best()
            # best.md 是「基线/最佳已建立」的内容源；元数据缺失/损坏时
            # 从历史或 best.md 恢复，而不是把 best 永远停在 unknown。
            # best.md 自身结构也损坏时，它不能再充当内容源：恢复历史最佳
            # 必须优先选快照仍可读的事件（当前最新快照丢了要退回较早的），
            # 否则元数据会指向一份内容已无从找回的最佳。
            if loaded:
                self.best = loaded
            else:
                try:
                    md_intact = _structure_intact(
                        self.best_md.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    md_intact = False
                self.best = self._recover_best(require_snapshot=not md_intact)
        else:
            # best.md 缺失不一定是首次运行：外部删除 / 截断后 best.json
            # 仍指向某个已晋升候选，对应快照 cand-<id>.md 还在——先按 id
            # 把内容找回，否则会以「当前状态」（可能是未验证的半截轮次）
            # 重建基线，等于把旧最佳悄悄降级、还可能把脏内容固化成基线。
            # 找回失败（基线没有快照 / 快照也丢了）才走首次运行路径。
            loaded = self._load_best()
            recovered = self._recover_best_text(loaded) if loaded else None
            if recovered is not None:
                self.best = loaded
                self._heal_best_md(recovered)
                self.sink.warn(f"rounds/best.md 缺失，已从候选快照恢复"
                               f"最佳内容（{loaded['id']}）")
            else:
                # best.json 也缺失/损坏时，history.jsonl 仍可能保留最后的
                # 采纳事件，对应快照 cand-<id>.md 也还在；best.json 虽可读
                # 但当前最佳快照丢失时，历史里也可能有更早、快照仍完整的
                # 最佳。只按当前状态重建基线会把旧最佳悄悄降级，甚至把
                # 未验证的半截内容固化成基线；先尝试用历史中“快照可读”的
                # 最新最佳恢复。
                history_best = self._best_from_history(require_snapshot=True)
                recovered = (self._recover_best_text(history_best)
                             if history_best is not None else None)
                if recovered is not None and history_best is not None:
                    self.best = history_best
                    try:
                        _atomic_write(
                            self.best_json,
                            json.dumps(history_best, ensure_ascii=False,
                                       indent=2))
                    except OSError as e:
                        self.sink.warn("恢复的最佳元数据写盘失败（忽略）："
                                       f"{e}")
                    self._heal_best_md(recovered)
                    if loaded:
                        self.sink.warn(
                            "rounds/best.md 缺失且当前最佳快照不可用，已从"
                            "history.jsonl 与候选快照恢复较早的最佳内容"
                            f"（{history_best['id']}）")
                    else:
                        self.sink.warn(
                            "rounds/best.md 与 best.json 均缺失，已从"
                            f"history.jsonl 与候选快照恢复最佳内容"
                            f"（{history_best['id']}）")
                else:
                    # 首次运行：把当前 research.md 固化为基线最佳（哪怕还是
                    # 脚手架）。有了基线，「第 1 轮候选被拒绝时还原到什么」
                    # 才有明确答案。与 _commit_best 同序：best.md 是「基线已
                    # 建立」的存在标志，必须最后落盘。反序（best.md 先成功、
                    # best.json 失败）会留下没有元数据的 best.md——下次启动走
                    # 「复用已有最佳」分支读到未知 id，基线事件也永远不会补记。
                    text = self._read_state_text() or state.scaffold(self.task)
                    best = {"id": f"baseline-{time.strftime('%Y%m%d-%H%M%S')}",
                            "round": 0, "verifier": "baseline", "score": None,
                            "ts": _ts()}
                    _atomic_write(
                        self.best_json,
                        json.dumps(best, ensure_ascii=False, indent=2))
                    _atomic_write(self.best_md, text)
                    self.best = best
                    try:
                        self._append_event({"event": "baseline", **self.best})
                    except Exception as e:  # noqa: BLE001 —— 守卫降级原则
                        self.sink.warn(f"记录基线事件失败（忽略）：{e}")
                    self.sink.ok(f"轮次守卫：建立基线最佳 {self.best['id']}")
        self.sink.info(
            f"轮次守卫已启用：{self.dir}（每轮快照；候选需验证通过才晋升为最佳；"
            f"verify={self.cfg.rounds.verify}"
            + (f"，兜底评分={self.cfg.rounds.fallback}"
               if self.cfg.rounds.verify == "auto" else "")
            + "）")
        try:
            self._apply_user_verdicts()
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            self.sink.warn(f"应用待决用户评分失败（忽略，稍后重试）：{e}")
        # 进程可能在轮次中途被 kill/断电：research.md 已留下未验证内容，
        # 而 best.md 仍是上一个已提交最佳。启动时必须先把「当前状态」拨回
        # 最佳，否则下一轮 agent 会从半截内容继续，甚至把脏内容晋升成最佳。
        # 补分兑现可能刚把新最佳写回 research.md，故放在其后；内容一致时
        # _restore_best 是空操作，不会产生事件或虚增还原统计。
        try:
            self._restore_best(0, "启动时还原未完成轮次")
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            self.sink.warn(f"启动时还原最佳失败（忽略）：{e}")

    def finish(self) -> None:
        try:
            self._apply_user_verdicts()
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            self.sink.warn(f"应用待决用户评分失败（忽略）：{e}")
        self._sync_counts()
        s = self.stats
        best = self.best
        self.sink.info(
            f"轮次守卫汇总：轮次 {s.rounds}（候选 {s.candidates}："
            f"采纳 {s.adopted} / 拒绝 {s.rejected} / 待评分 {s.pending}；"
            f"心跳 {s.heartbeat} / 跳过 {s.skipped} / 还原 {s.restored}）。"
            f"当前最佳：{best.get('id', '?')}"
            + (f"（第 {best['round']} 轮，{best.get('verifier')}，"
               f"评分 {best.get('score')}）" if best.get("round", 0) > 0 else ""))

    def on_round_failed(self, round_no: int, reason: str) -> None:
        """agent 启动/执行失败的轮次：不留候选（半截产物不可信），仅记账；
        同时还原最佳——失败轮次留下的半截产物同样不能污染下一轮的起点。

        中断（KeyboardInterrupt）可能晚于 on_round_end 到达：该轮已按完成
        轮次产出候选/心跳/判定事件，重复记账会虚增轮次数与跳过数，还会在
        审计日志里为同一轮同时留下候选与 skipped 两条自相矛盾的事件。
        此时只补做一次「还原最佳」（判定已完成时通常是无变化的空操作），
        确保状态仍停在最佳，不再追加任何记账。"""
        if round_no in self._handled_rounds:
            self._restore_best(round_no, why=f"轮次失败（{reason}）")
            return
        self._handled_rounds.add(round_no)
        self.stats.rounds += 1
        self.stats.skipped += 1
        # 记账事件只是审计：写盘失败不能反过来跳过还原，否则失败轮次的
        # 半截产物会留在 research.md 污染下一轮的起点
        try:
            self._append_event({"event": "skipped", "round": round_no,
                                "reason": reason})
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            self.sink.warn(f"记录跳过事件失败（忽略）：{e}")
        self._restore_best(round_no, why=f"轮次失败（{reason}）")

    # ---- 每轮守卫主流程 ----
    def on_round_end(self, round_no: int) -> str:
        """一轮 agent 成功结束后调用；返回 adopted / rejected / pending /
        heartbeat / skipped 供调用方与测试断言。

        本轮判定完成后兑现一次待决用户评分（与 start/finish 同一通道）。
        「每轮开始/结束时兑现」不能只落在会话首尾：`iterations: inf` 的
        长循环里用户补分将永远等不到兑现，后续轮次也不会从重新采纳的
        最佳继续，与 README / config 注释的承诺相矛盾。必须放在本轮
        快照与判定【之后】：提前兑现会先把旧候选写回 research.md，
        覆盖掉 agent 刚产出、尚未快照的本轮内容（违反「任何一轮的产物
        都落盘」）。
        """
        result = self._process_round_end(round_no)
        try:
            self._apply_user_verdicts()
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            self.sink.warn(f"应用待决用户评分失败（忽略，稍后重试）：{e}")
        return result

    def _process_round_end(self, round_no: int) -> str:
        self._handled_rounds.add(round_no)
        self.stats.rounds += 1
        try:
            result = self._process_round_end_body(round_no)
        except BaseException:
            # 中断（或任何异常）落在候选快照之后、终结结论入账之前的
            # 未覆盖点：候选已计入 candidates，却没有 adopted/rejected/
            # pending，违反汇总不变式；此时轮次已在 _handled_rounds 里，
            # on_round_failed 只会补做还原，补不了统计。这里兜底补记
            # 「待评分」再传播原异常；已挂起/已决/已晋升的候选幂等跳过。
            try:
                self._settle_inflight_candidate(round_no)
            finally:
                self._inflight_cid = None
            raise
        else:
            self._inflight_cid = None
        return result

    def _settle_inflight_candidate(self, round_no: int) -> None:
        """异常路径兜底：把本轮已快照但无结论的候选记为「待评分」。

        只处理「快照成功、尚无任何终结结论」这一种状态；已挂起
        （_pending_ids）、已决（_settled_cids）或已晋升（best 已指向
        该候选）时直接跳过，避免重复计数。记账本身失败只告警——不能
        掩盖触发它的原始异常。
        """
        self._sync_counts()
        cid = self._inflight_cid
        if cid is None or cid in self._pending_ids \
                or cid in self._settled_cids or self.best.get("id") == cid:
            return
        try:
            self._pend(round_no, cid, "轮次被中断，候选挂起")
        except BaseException as e:  # noqa: BLE001 —— 守卫降级原则
            try:
                self.sink.warn(f"记录中断候选挂起失败（忽略）：{e}")
            except BaseException:  # noqa: BLE001 —— 连告警都失败时保原始异常
                pass

    def _process_round_end_body(self, round_no: int) -> str:
        text = self._read_state_text()
        if not text:
            # research.md 整个没了：没法当候选，也别让下一轮拿到空状态
            self.stats.skipped += 1
            try:
                self._append_event({"event": "skipped", "round": round_no,
                                    "reason": "状态文件缺失或不可读"})
            except Exception as e:  # noqa: BLE001 —— 守卫降级原则
                self.sink.warn(f"记录跳过事件失败（忽略）：{e}")
            self._restore_best(round_no, why="状态文件缺失")
            return "skipped"

        # 1) 结构检查：区块标记被外部 agent 弄坏的内容无法被安全读取，
        #    更不能进最佳——结构损坏直接拒绝（守卫级判定，无需测试/评分）
        if not _structure_intact(text):
            self.stats.candidates += 1
            cid = None
            try:
                cid = self._snapshot_candidate(round_no, text)
                self._inflight_cid = cid
                self._append_event({"event": "candidate", "id": cid,
                                    "round": round_no, "corrupt": True})
            except KeyboardInterrupt:
                if cid is not None:
                    try:
                        self._append_event({"event": "candidate", "id": cid,
                                            "round": round_no, "corrupt": True})
                    except Exception as e2:  # noqa: BLE001
                        self.sink.warn(f"记录候选事件失败（中断，忽略）：{e2}")
                    try:
                        self._pend(round_no, cid, "轮次被中断，候选挂起")
                    except Exception as e:  # noqa: BLE001
                        self.sink.warn(f"记录中断候选挂起失败（忽略）：{e}")
                else:
                    self.stats.candidates -= 1
                    self.stats.skipped += 1
                raise
            except Exception as e:
                self.stats.candidates -= 1
                self.stats.skipped += 1
                self._inflight_cid = None  # 候选已撤销，兜底不得再挂起
                try:
                    self._append_event({"event": "skipped", "round": round_no,
                                        "reason": f"候选快照写盘失败：{e}"})
                except Exception as e2:  # noqa: BLE001 —— 守卫降级原则
                    self.sink.warn(f"记录跳过事件失败（忽略）：{e2}")
                self._restore_best(round_no, why="候选快照写盘失败")
                raise
            verdict = Verdict(verifier="guard", result="rejected",
                              reason="区块标记缺失或损坏，无法安全读取")
            try:
                self._append_event({"event": "verdict", "id": cid,
                                    "round": round_no,
                                    **_verdict_fields(verdict)})
            except Exception as e:  # noqa: BLE001 —— 守卫降级原则
                self.sink.warn(f"记录判定事件失败（判定已生效，忽略）：{e}")
                # 判定已生效：事件缺失时靠内存集合阻止本轮收尾的
                # _apply_user_verdicts 把同一候选再拒绝/采纳一次
                self._applied_verdicts.add(cid)
            self._count_rejected(cid)
            self.sink.err(f"候选 {cid} 被守卫拒绝：{verdict.reason}，已还原最佳")
            self._restore_best(round_no, why="结构损坏")
            return "rejected"

        # 2) 无改动 → 心跳（不产生候选，避免无意义快照淹没真正的轮次）
        cand_idea, cand_artifact = self._sections(text)
        best_text = self._read_best_md()
        best_idea, best_artifact = self._sections(best_text)
        if (cand_idea, cand_artifact) == (best_idea, best_artifact):
            self.stats.heartbeat += 1
            # 心跳事件写盘失败不能把「无改动」变成守卫异常：本轮没有
            # 候选/判定，记账已完成，事件只是审计噪音
            try:
                self._append_event({"event": "heartbeat",
                                    "round": round_no})
            except Exception as e:  # noqa: BLE001 —— 守卫降级原则
                self.sink.warn(f"记录心跳事件失败（忽略）：{e}")
            return "heartbeat"

        # 3) 有改动 → 候选快照（先落盘：无论后续验证成败，本轮产物都不丢）
        self.stats.candidates += 1
        cid = None
        changed = [n for n, (c, b) in {
            "idea": (cand_idea, best_idea),
            "artifact": (cand_artifact, best_artifact),
        }.items() if c != b]
        try:
            cid = self._snapshot_candidate(round_no, text)
            self._inflight_cid = cid
            self._append_event({"event": "candidate", "id": cid,
                                "round": round_no, "changed": changed})
        except KeyboardInterrupt:
            if cid is not None:
                try:
                    self._append_event({"event": "candidate", "id": cid,
                                        "round": round_no,
                                        "changed": changed})
                except Exception as e2:  # noqa: BLE001
                    self.sink.warn(f"记录候选事件失败（中断，忽略）：{e2}")
                try:
                    self._pend(round_no, cid, "轮次被中断，候选挂起")
                except Exception as e:  # noqa: BLE001
                    self.sink.warn(f"记录中断候选挂起失败（忽略）：{e}")
            else:
                self.stats.candidates -= 1
                self.stats.skipped += 1
            raise
        except Exception as e:
            self.stats.candidates -= 1
            self.stats.skipped += 1
            self._inflight_cid = None  # 候选已撤销，兜底不得再挂起
            try:
                self._append_event({"event": "skipped", "round": round_no,
                                    "reason": f"候选快照写盘失败：{e}"})
            except Exception as e2:  # noqa: BLE001 —— 守卫降级原则
                self.sink.warn(f"记录跳过事件失败（忽略）：{e2}")
            self._restore_best(round_no, why="候选快照写盘失败")
            raise
        self.sink.info(f"候选快照：{CAND_PREFIX}{cid}.md"
                       "（尚未验证，不代表最佳）")

        # 4) 验证 → 晋升 / 拒绝 / 挂起
        try:
            verdict = self._verify(round_no, cid)
            if verdict.result == "adopted":
                # 先完成外部副作用（best.md / best.json 写盘）再记已决事件：
                # 写盘失败（磁盘满 / 目录只读）时保持「未决」——先记一条
                # adopted 会让 _apply_user_verdicts 的 resolved 集合永久跳过
                # 该候选，用户腾出磁盘后补分也再翻不了案，审计日志还会留下
                # 一条未兑现的 adopted（与 _apply_user_verdicts 的修复同一
                # 口径：外部副作用成功前不能留下不可撤销的结论）
                self._adopt(cid, round_no, verdict)
        except Exception as e:  # noqa: BLE001 —— 守卫降级 + 统计一致
            # 晋升可能已经提交成功，异常只落在提交后的统计/通知上（如
            # sink.ok 在 TUI 已退出时抛错）。此时不能把候选再挂起：best
            # 已指向它，再计入 pending 会让 adopted+pending 超过
            # candidates。先按内存里的 best 对账，补记 adopted 与判定事件，
            # 让调用方看到本轮已完成。
            if self.best.get("id") == cid:
                self._count_adopted(cid)
                try:
                    self._append_event({"event": "verdict", "id": cid,
                                        "round": round_no,
                                        **_verdict_fields(verdict)})
                except Exception as e2:  # noqa: BLE001 —— 守卫降级原则
                    self.sink.warn(f"记录判定事件失败（判定已生效，忽略）：{e2}")
                self._applied_verdicts.add(cid)
                try:
                    self.sink.warn(f"候选 {cid} 已晋升，但收尾失败（忽略）："
                                   f"{e}")
                except Exception:  # noqa: BLE001 —— 通知失败不能改判定
                    pass
                return "adopted"
            # 验证/晋升中途失败（best.md/best.json 写盘失败、候选快照损坏
            # 等）：候选已快照落盘，必须按「待评分」记账并还原最佳。绝不能
            # 只把异常抛给 runner——未计入 adopted/rejected/pending 会让
            # 汇总出现「候选 1，采纳/拒绝/待评分皆 0」的自相矛盾，违反
            # adopted+rejected+pending==candidates 不变式；挂起结论照常落
            # 审计日志，用户补分/重试仍可翻案。KeyboardInterrupt 等
            # BaseException 不在此列：中断轮次由 runner 口径还原、不写判定。
            try:
                self._append_event({"event": "verdict", "id": cid,
                                    "round": round_no, "verifier": "guard",
                                    "result": "pending", "score": None,
                                    "reason": f"验证或晋升失败（{e}），"
                                              "候选挂起等待重试"})
            except Exception as e2:  # noqa: BLE001 —— 守卫降级原则
                self.sink.warn(f"记录候选挂起事件失败（忽略）：{e2}")
            self._pend(round_no, cid, "验证失败，候选挂起")
            raise
        except KeyboardInterrupt:
            # 中断落在验证/晋升途中：候选快照已落盘但还没有结论，必须按
            # 「待评分」记账，否则汇总会出现「候选 1、采纳/拒绝/待评分全
            # 0」，违反 adopted+rejected+pending==candidates。既有中断
            # 语义保持不变：不写 verdict 事件（不能把中断伪装成已决），
            # runner 的 on_round_failed 只补做还原，不重复记轮次。
            # 若 _adopt 已在中断前提交成功（best 已指向该候选），则不能
            # 再挂起它（否则 adopted+pending 会超过 candidates）。提交成功
            # 不等于统计已入账：中断可能正好落在 self.best = best 之后、
            # stats.adopted += 1 之前，必须用 _adopted_ids 对账后补齐。
            if self.best.get("id") == cid:
                committed = None
            else:
                loaded = self._load_best()
                committed = loaded if loaded.get("id") == cid else None
            if self.best.get("id") == cid or committed is not None:
                if committed is not None:
                    self.best = committed
                self._count_adopted(cid)
                try:
                    self._append_event({"event": "verdict", "id": cid,
                                        "round": round_no,
                                        **_verdict_fields(verdict)})
                except Exception as e:  # noqa: BLE001 —— 守卫降级原则
                    self.sink.warn(f"记录中断前已生效判定失败（忽略）：{e}")
                self._applied_verdicts.add(cid)
            else:
                try:
                    self._pend(round_no, cid, "轮次被中断，候选挂起")
                except Exception as e:  # noqa: BLE001 —— 守卫降级原则
                    self.sink.warn(f"记录中断候选挂起失败（忽略）：{e}")
            raise
        # 判定已经生效（采纳已完成外部副作用，拒绝/挂起只是记账），
        # 审计事件写盘失败（磁盘满 / 只读）不能反过来把本轮变成异常：
        # 异常会被 runner 当成「守卫处理异常」跳过后续记账——拒绝/挂起
        # 的 stats 不更新，汇总出现「候选 1，采纳/拒绝/待评分全 0」，
        # 违反 adopted+rejected+pending==candidates；采纳轮虽已计入
        # adopted，但 research.md 也不会按拒绝/挂起路径还原。历史丢失
        # 只影响审计与恢复源，不能让本轮判定与状态机自相矛盾。
        try:
            self._append_event({"event": "verdict", "id": cid,
                                "round": round_no, **_verdict_fields(verdict)})
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            self.sink.warn(f"记录判定事件失败（判定已生效，忽略）：{e}")
            # 判定已生效但事件缺失：本轮收尾的 _apply_user_verdicts 会
            # 因为 resolved 里没有该 id 而重新兑现 verdicts.txt 里的同一
            # 行——拒绝统计翻倍、采纳重复写盘。内存集合与事件写入解耦。
            # 挂起不是终局判定，绝不能记入：用户之后补分仍需能翻案。
            if verdict.result in ("adopted", "rejected"):
                self._applied_verdicts.add(cid)
        if verdict.result == "adopted":
            return "adopted"
        if verdict.result == "rejected":
            self._count_rejected(cid)
            self.sink.warn(f"候选 {cid} 未通过（{verdesc(verdict)}），"
                           f"保留最佳并还原")
            self._restore_best(round_no, why="候选被拒绝")
            return "rejected"
        self._pend(round_no, cid, "候选待评分")
        return "pending"

    def _pend(self, round_no: int, cid: str, why: str) -> None:
        """把候选从「候选」计入「待评分」：还原最佳并提示用户评分。

        正常挂起（评审无结论）与验证/晋升失败共用此记账口径：候选快照都
        已落盘，统计必须与之一一对应（adopted+rejected+pending==candidates），
        否则汇总自相矛盾、待评分候选数失真。"""
        self._pending_ids.add(cid)
        self._sync_counts()
        self._restore_best(round_no, why=why)
        self._hint_user_scoring(cid)

    # ---- 验证决策 ----
    def _run_suite(self, suite: List[str]) -> SuiteResult:
        """跑测试套件。默认运行器接上 sink.should_stop：TUI 按 q /
        Ctrl+C 时立即整组终止套件，否则守卫会在套件上阻塞到
        verify_timeout（默认 600s），run_tui 只等 20s——主动退出会被
        误报成退出码 1，测试进程还会成孤儿。注入的测试接缝保持原
        三参数签名（它们不接触真实进程，不存在停止时延）。"""
        runner = self._suite_runner
        if runner is None:
            return run_suite(suite, self.repo, self.cfg.rounds.verify_timeout,
                             stop=self.sink.should_stop)
        return runner(suite, self.repo, self.cfg.rounds.verify_timeout)

    def _verify(self, round_no: int, cid: str) -> Verdict:
        mode = self.cfg.rounds.verify
        if mode == "off":
            return Verdict(verifier="none", result="adopted",
                           reason="verify=off：不验证，最新即最佳（快照照存）")
        if self.sink.should_stop():
            self.sink.warn("用户请求停止：跳过候选验证，候选挂起")
            return Verdict(verifier="guard", result="pending",
                           reason="用户请求停止，未验证")

        if mode in ("auto", "tests"):
            suite = detect_test_suite(self.repo)
            if suite is not None:
                res = self._run_suite(suite)
                if res.available:
                    if res.ok:
                        return Verdict(verifier="tests", result="adopted",
                                       reason="测试全部通过｜" + detail_field(res))
                    return Verdict(verifier="tests", result="rejected",
                                   reason="测试失败｜" + detail_field(res))
                if res.stopped:
                    # 套件被用户停止：候选没有验证结论，挂起等待评分；
                    # 不能再转兜底评审——用户已经离开，拉起新进程只会让
                    # run_tui 的等待再次超时、把主动退出误报成退出码 1
                    self.sink.warn("用户请求停止：测试套件已终止，候选挂起")
                    return Verdict(verifier="tests", result="pending",
                                   reason="用户请求停止，套件未跑完")
                if mode == "tests":
                    # 显式只要测试，但套件运行时拉不起来：无法下结论 → 挂起
                    self.sink.warn(f"测试套件无法运行（{res.reason}），"
                                   "候选挂起等待用户评分")
                    return Verdict(verifier="tests", result="pending",
                                   reason=f"套件无法运行：{res.reason}")
                self.sink.warn(f"测试套件无法运行（{res.reason}），"
                               f"转兜底评分（{self.cfg.rounds.fallback}）")
            elif mode == "tests":
                return Verdict(verifier="tests", result="pending",
                               reason="未检测到可运行的测试套件，等待用户评分")
            # auto 且（无套件 / 套件不可用）→ 兜底评分者

        if mode == "ai":
            return self._ai_verdict(round_no, cid)
        if mode == "user":
            # 显式 user：只认用户评分。fallback 只服务于 auto（默认就是
            # ai），若拿 fallback 顶替用户的选择，verify=user 会被静默
            # 变成 AI 评分——用户永远等不到 verdicts.txt 的兑现通道
            return self._user_verdict(cid)
        # auto 且无可用测试套件 → fallback 指定的兜底评分者
        if self.cfg.rounds.fallback == "ai":
            return self._ai_verdict(round_no, cid)
        return self._user_verdict(cid)

    def _user_verdict(self, cid: str) -> Verdict:
        try:
            verdicts = self._read_verdicts()
        except OSError:
            verdicts = {}
        if cid in verdicts:
            score, comment = verdicts[cid]
            if score is None:
                # 行存在但分数解析不出（打错字/格式不对）：按「挂起」处理，
                # 不能当拒绝——「已决」的拒绝会被记进 history，用户改好
                # 这行也会在 _apply_user_verdicts 里被永久跳过
                return Verdict(verifier="user", result="pending",
                               reason="评分无法解析（格式：<候选id> <0-10分> [评语]），"
                                      "保持挂起等待修正",
                               comment=comment)
            adopted = score >= self.cfg.rounds.adopt_score
            return Verdict(
                verifier="user", score=score,
                result="adopted" if adopted else "rejected",
                reason=f"用户评分 {score:g}",
                comment=comment)
        return Verdict(verifier="user", result="pending",
                       reason="等待用户在 verdicts.txt 中评分")

    def _ai_verdict(self, round_no: int, cid: str) -> Verdict:
        prompt = self._judge_prompt(round_no, cid)
        ok, text = self._run_judge(prompt)
        if not ok:
            # 评审员基础设施失败（超时/非零退出）≠ 候选差：不下结论，挂起
            return Verdict(verifier="ai", result="pending",
                           reason="评审员运行失败（超时或非零退出），等待用户评分")
        score = parse_score(text)
        if score is None:
            return Verdict(verifier="ai", result="pending",
                           reason="评审输出里解析不出 0-10 分，等待用户评分")
        adopted = score >= self.cfg.rounds.adopt_score
        comment = _last_comment(text)
        return Verdict(verifier="ai", score=score,
                       result="adopted" if adopted else "rejected",
                       reason=f"AI 评分 {score:g}（阈值 {self.cfg.rounds.adopt_score:g}）",
                       comment=comment)

    def _run_judge(self, prompt: str) -> Tuple[bool, str]:
        if self._judge_override is not None:
            return self._judge_override(prompt)
        cmd = self.cfg.rounds.judge_command.strip() or self.cfg.agent.command
        agent = ShellAgent(
            cmd, self.workspace, timeout=self.cfg.rounds.judge_timeout,
            on_output=self.sink.agent_output, on_stderr=self.sink.agent_stderr,
        )
        # 评审期间把 sink 的「当前 agent」指向评审员：TUI 里按 q / Ctrl+C
        # 才能终止正在运行的评审。否则 stop_agent() 杀的是已结束的主
        # agent，评审进程会脱离终端会话跑满 judge_timeout（并让退出码误报）
        prev_agent = getattr(self.sink, "agent", None)
        self.sink.agent = agent
        try:
            if self.sink.should_stop():
                self.sink.warn("用户请求停止：跳过 AI 评审，候选挂起")
                return False, ""
            text = agent.run(prompt)
        except (OSError, ValueError) as e:
            self.sink.warn(f"AI 评审调用失败：{e}")
            return False, ""
        finally:
            self.sink.agent = prev_agent
        if agent.timed_out:
            self.sink.warn("AI 评审超时")
            return False, text
        if agent.returncode not in (0, None):
            self.sink.warn(f"AI 评审异常退出（退出码 {agent.returncode}）")
            return False, text
        return True, text

    def _read_candidate_text(self, cid: str) -> str:
        """严格读取候选快照内容；不可读时抛 OSError（不退回实时状态）。

        与 _adopt / _apply_user_verdicts 同一读取口径：评审员必须看到与
        被晋升物【完全相同】的内容。评审期间 research.md 可能被外部再改
        一次（后台进程收尾、用户手改、并发的另一实例），直接重读实时状态
        会让评审的是 A、晋升的是快照 B——AI 给 A 打的分被用来采纳从未被
        验证过的 B，候选/最佳分离的验证不变量被破坏。
        快照在验证期间被删除/损坏时，候选无法证明被验证过：调用方按
        「待评分」挂起（快照恢复后仍可补分），绝不能拿未验证的实时状态
        顶替。
        """
        try:
            return (self.dir / f"{CAND_PREFIX}{cid}.md").read_text(
                encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise OSError(f"候选快照 {cid} 不可读：{e}") from e

    def _judge_prompt(self, round_no: int, cid: str) -> str:
        best_text = self._read_best_md()
        b_idea, b_artifact = self._sections(best_text)
        c_idea, c_artifact = self._sections(self._read_candidate_text(cid))
        best = self.best
        score_note = (f"（历史评分 {best.get('score'):g}）"
                      if isinstance(best.get("score"), (int, float))
                      else "")
        return f"""你是「灵感驱动研究循环」的轮次评审员，独立于研究过程，只做对比评分。

【研究任务】{self.task}

【当前最佳】（{best.get('id', '?')}，第 {best.get('round', '?')} 轮产物{score_note}）
--- 想法区 ---
{b_idea or "（空）"}

--- 产物区 ---
{b_artifact or "（空）"}

【本轮候选】（{cid}，第 {round_no} 轮产物）
--- 想法区 ---
{c_idea or "（空）"}

--- 产物区 ---
{c_artifact or "（空）"}

请从【任务契合度 / 研究深度 / 可操作性 / 新颖性】四个维度综合比较本轮候选与当前最佳：
先用不超过 5 行给出简短评语（指出候选相对最佳的核心变化与风险）；
然后在输出的最后一行【严格】按如下格式单独给出总分：

评分: <0 到 10 之间的整数或一位小数>

（参考锚点：10 = 远超当前最佳；7 = 明显更好；5 = 大致相当；3 = 明显退步；0 = 完全偏离任务）"""

    # ---- 晋升 / 还原 ----
    def _recover_best_text(self, best: Optional[Dict] = None) -> Optional[str]:
        """从最佳 id 对应的候选快照找回最佳内容（结构完好才返回）。

        best.md 是还原 / 评审的唯一内容源，但每个晋升过的最佳都有内容
        完全相同的候选快照 cand-<id>.md（见 _commit_best：两者写自同一份
        被验证内容）。best.md 被外部删除 / 截断 / 编码损坏时按 id 从快照
        找回，避免 _restore_best 把脚手架（「暂无」）或空区块写回
        research.md、静默丢掉当前最佳。基线最佳没有对应快照，读不到时
        返回 None，调用方退回原口径。
        """
        info = self.best if best is None else best
        cid = info.get("id") if isinstance(info, dict) else None
        if not _valid_cid(cid):
            return None
        try:
            text = (self.dir / f"{CAND_PREFIX}{cid}.md").read_text(
                encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        # 快照也损坏（磁盘级损坏 / 被外部篡改）时不能拿它当最佳
        return text if _structure_intact(text) else None

    def _heal_best_md(self, text: str) -> None:
        """把找回的最佳内容回写 best.md（自愈；失败只告警不阻断）。"""
        try:
            _atomic_write(self.best_md, text)
        except OSError as e:
            self.sink.warn(f"找回的最佳内容写回 best.md 失败（忽略）：{e}")

    def _read_best_md(self) -> str:
        try:
            text = self.best_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # best.md 缺失 / 不可读：先按最佳 id 从候选快照找回，找回
            # 失败才按「空」处理（等价于基线脚手架，绝不能把损坏内容
            # 当最佳写回 research.md）
            recovered = self._recover_best_text()
            if recovered is not None:
                self.sink.warn("best.md 缺失或不可读，已从候选快照恢复"
                               f"最佳内容（{self.best.get('id', '?')}）")
                self._heal_best_md(recovered)
                return recovered
            return state.scaffold(self.task)
        if not _structure_intact(text):
            recovered = self._recover_best_text()
            if recovered is not None:
                self.sink.warn("best.md 结构损坏，已从候选快照恢复最佳内容"
                               f"（{self.best.get('id', '?')}）")
                self._heal_best_md(recovered)
                return recovered
            # 无快照可救（基线 / 快照也丢失）：与缺失分支同一口径按
            # 「空」处理，绝不能把损坏内容当最佳写回 research.md。
            return state.scaffold(self.task)
        return text

    def _commit_best(self, text: Optional[str], best: Dict) -> None:
        """把候选快照晋升为最佳：best.json + best.md 两个文件都成功才生效。

        提交顺序必须让内容源（best.md，_restore_best / _read_best_md 的
        唯一内容来源）最后落盘：反序（best.md 先成功、best.json 失败）时
        未完成晋升的候选内容已成为下一轮的还原源——self.best / 统计 /
        best.json 都还指向旧最佳，内容却已被悄悄替换，「候选必须通过
        验证（或拿到高分）才晋升」的核心不变式被破坏。
        best.json 先落盘、best.md 失败时最多元数据短暂超前、内容仍停在
        旧最佳；此时尽力把元数据回滚为旧指针，保持两个文件一致。
        调用方据异常保持候选「未决」：写盘恢复后补分/重试仍能兑现。
        """
        if not text:
            # 快照与当前状态都读不出内容（如快照被外部删除）时没有任何
            # 被验证过的内容可写进最佳：只推进元数据会把最佳指向一份读
            # 不到内容的快照。按写盘失败同等处理，保持候选未决可重试
            raise OSError("候选快照不可读，无法写盘晋升最佳")
        # best.json 记录的是「哪份快照是最佳」；研究循环只前进不改写历史，
        # 旧 best.md 内容被覆盖前仍在各轮 cand-*.md / git 提交里留档
        try:
            _atomic_write(self.best_json,
                          json.dumps(best, ensure_ascii=False, indent=2))
            _atomic_write(self.best_md, text)
        except BaseException:
            # 内容源写盘失败：撤销刚推进的元数据指针，回到「两个文件都
            # 指向旧最佳」的一致状态（回滚自身也可能失败，尽力而为）。
            # best.md 已经发布时说明两次写盘都已完成，中断只是落在返回前，
            # 不能反过来把元数据回滚成旧指针。
            try:
                md_committed = self.best_md.read_text(
                    encoding="utf-8") == text
            except (OSError, UnicodeDecodeError):
                md_committed = False
            if not md_committed:
                try:
                    _atomic_write(self.best_json,
                                  json.dumps(self.best, ensure_ascii=False,
                                             indent=2))
                except BaseException:
                    pass
            raise

    def _sync_counts(self) -> None:
        """按本会话候选 id 集合重算结论桶，并补齐已决标记。"""
        self.stats.adopted = len(self._adopted_ids)
        self.stats.rejected = len(self._rejected_ids)
        self.stats.pending = len(self._pending_ids)
        self._settled_cids.update(self._adopted_ids)
        self._settled_cids.update(self._rejected_ids)

    def _count_adopted(self, cid: str) -> None:
        """把候选计入 adopted；集合成员是幂等对账的提交点。"""
        self._adopted_ids.add(cid)
        self._sync_counts()

    def _count_rejected(self, cid: str) -> None:
        """把候选计入 rejected；集合成员是幂等对账的提交点。"""
        self._rejected_ids.add(cid)
        self._sync_counts()

    def _adopt(self, cid: str, round_no: int, verdict: Verdict) -> None:
        # 晋升的必须是被验证过的候选快照本身：测试套件 / AI 评审可能跑很久，
        # 期间状态文件可能被外部再改一次。直接读当前状态会把未经验证的内容
        # 写进 best.md（best.json 记录的却是候选 id）；下一轮候选被拒时
        # _restore_best 就会把这份未验证内容还原进研究循环，破坏候选/最佳
        # 分离。快照不可读（如验证期间被外部删除）时抛异常，由调用方
        # 按「待评分」挂起；绝不能退回当前状态晋升未验证内容。
        text = self._read_candidate_text(cid)
        # 快照写入后可能被外部截断/篡改（见 _structure_intact）：晋升前
        # 重新校验区块结构，损坏快照按写盘失败处理（异常上抛，候选保持
        # 未决可补分重试，self.best / 统计都不动），绝不让它进 best.md
        if not _structure_intact(text):
            raise OSError("候选快照区块标记损坏，无法晋升为最佳")
        best = {"id": cid, "round": round_no, "verifier": verdict.verifier,
                "score": verdict.score, "ts": _ts(),
                "reason": verdict.reason}
        # 两个文件都写盘成功后才提交内存状态与统计：任何一步失败时
        # self.best / 统计都不能指向一份没有完整落盘的最佳（调用方据
        # 异常按「守卫本轮降级」处理，候选保持未决可补分翻案）
        self._commit_best(text, best)
        self.best = best
        self._count_adopted(cid)
        self.sink.ok(f"第 {round_no} 轮候选通过验证（{verdesc(verdict)}），"
                     f"晋升为最佳（{cid}）")

    def _restore_best(self, round_no: int, why: str) -> List[str]:
        """把 research.md 的两个区块还原为当前最佳内容（前进式还原：
        不删任何文件、不改写历史，只把循环的「当前状态」拨回最佳）。
        返回实际被改回的区块名列表（无变化返回空表，不产生事件噪音）。"""
        best_text = self._read_best_md()
        cur = self._read_state_text()
        changed: List[str] = []
        for name, key in ((state.SECTION_IDEA, "idea"),
                          (state.SECTION_ARTIFACT, "artifact")):
            want = _readable_section(best_text, name)
            if want is None:
                # best.md 自身损坏时按「空内容」处理，但结构仍要修复回来
                want = ""
            have = _readable_section(cur, name)
            if want == have:
                continue
            try:
                state.update_section_file(self.state_path, name, want)
                changed.append(key)
            except (OSError, ValueError) as e:
                self.sink.warn(f"还原最佳区块 {key} 失败（忽略）：{e}")
        if not changed:
            return changed
        self.stats.restored += 1
        # 区块已实际写回，还原已经生效：审计事件写盘失败只能告警，
        # 不能让调用方误以为还原失败（拒绝/挂起路径会因异常跳过后续
        # 提示与返回；runner 再补还原也只是空操作）
        try:
            self._append_event({"event": "restored", "round": round_no,
                                "why": why, "best": self.best.get("id"),
                                "changed": changed})
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            self.sink.warn(f"记录还原事件失败（还原已生效，忽略）：{e}")
        self.sink.warn(f"已还原为当前最佳 {self.best.get('id', '?')}"
                       f"（{why}；改动区块：{'、'.join(changed)}）；"
                       "下一轮将从最佳继续，更差的候选不会污染后续轮次")
        return changed

    def _hint_user_scoring(self, cid: str) -> None:
        if self._hinted:
            return
        self._hinted = True
        self.sink.info(
            f"给候选打分：在 {self.verdicts_path} 追加一行"
            f"「{cid} <0-10分> [评语]」（>= {self.cfg.rounds.adopt_score:g} 采纳）。"
            "候选已按最佳还原；被补分采纳时会前进式晋升并写回状态文件")

    # ---- 用户评分（verdicts.txt）----
    def _read_verdicts(self) -> Dict[str, Tuple[Optional[float], str]]:
        out: Dict[str, Tuple[Optional[float], str]] = {}
        try:
            raw = self.verdicts_path.read_bytes()
        except OSError:
            return out
        # utf-8-sig：与 words / cli 等其它用户可编辑文件同一 BOM 防护口径。
        # 带 BOM 的首行若不剥，cid 会变成 "\ufeff<cid>"，用户评分被静默忽略。
        # errors="replace"：个别坏字节（非 UTF-8 编辑器保存 / 粘贴损坏）
        # 不能让整份评分文件静默失效——cid 与分数列都是 ASCII，坏字节只会
        # 出现在评语里，替换后这两列照常解析；与本函数「坏行跳过、好行
        # 照常生效」的容错口径一致
        text = raw.decode("utf-8-sig", errors="replace")
        # 只按 ASCII 换行切分（与 _read_events 同一口径）：str.splitlines
        # 还会在 U+2028/U+2029/U+0085 等 Unicode 行分隔符处切开，评语里
        # 含这些字符时一行评分会被拆成两行——后半段若恰好以「cid 分数」
        # 开头，就会被解析成一条凭空出现的伪评分（用户被迫翻案/拒绝）。
        for line in re.split(r"\r\n|\r|\n", text):
            # 逐行再剥一次 BOM：utf-8-sig 只处理文件首，拼接/粘贴的多段
            # 内容里靠后的行同样可能带 BOM
            line = line.strip().lstrip("\ufeff").strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 2)
            if len(parts) < 2:
                continue
            cid, raw = parts[0], parts[1]
            comment = parts[2].strip() if len(parts) > 2 else ""
            try:
                score = float(raw)
            except ValueError:
                score = None
            else:
                # nan/inf 不是合法评分：min/max 夹取会把它们留成 10 分，
                # 等于凭空给候选满分——必须和「解析不出」同等对待
                if not math.isfinite(score):
                    score = None
                else:
                    score = max(0.0, min(10.0, score))
            if score is None and cid in out and out[cid][0] is not None:
                # 同一候选写了两行、后一行分数打错（"abc"/"nan"）时，
                # 不能让坏行覆盖前面已解析出的有效评分——本函数的约定是
                # 「坏行跳过、好行照常生效」。后一行有效评分仍按最后一条
                # 覆盖（用户用新分数纠正旧分数的主要写法）。
                continue
            out[cid] = (score, comment)
        return out

    def _apply_user_verdicts(self) -> None:
        """把 verdicts.txt 里的新评分应用到仍处「待评分」的候选上。
        采纳旧候选 = 前进式晋升（快照内容成为新最佳并写回 research.md），
        拒绝旧候选 = 只记账。这是异步用户评分的兑现通道。采纳前会重新
        校验快照的区块结构（见 _structure_intact），损坏快照保持挂起。"""
        verdicts = self._read_verdicts()
        if not verdicts:
            return
        events = self._read_events()
        resolved: set = set()
        candidates: Dict[str, Dict] = {}
        for ev in events:
            ev_event = ev.get("event")
            cid = ev.get("id")
            if not _valid_cid(cid):
                # 历史行被外部编辑/其他工具写入时 id 可能是列表/字典等
                # 非字符串：拿它当 candidates/resolved 的键会直接抛
                # TypeError（unhashable），让 start()/finish() 的补分兑现
                # 整体失败（守卫降级、汇总丢失）；含 NUL/路径分隔符的
                # 字符串则会让后续 cand-<id>.md 的读取抛 ValueError 或
                # 越出 rounds 目录。与 _recover_best / _valid_best 同一
                # 口径（_valid_cid）：无法安全归属到候选的事件跳过
                continue
            if ev_event == "candidate":
                candidates[cid] = ev
            elif (ev_event == "verdict"
                  and ev.get("result") in ("adopted", "rejected")):
                # 只有真正下了结论（采纳/拒绝）才算已决；「挂起」事件
                # 不算——挂起候选正是要等这里的补分来翻案的。
                # 缺失/未知 result（外部编辑出合法 JSON 但字段损坏）同样
                # 不能算已决：否则一个坏事件会把候选永久锁死，用户补分
                # 再也翻不了案；已知结论之外的值一律不采信。
                resolved.add(cid)
        # 当前最佳天然已经「已决」：历史里的 verdict 事件可能因磁盘满
        # 丢失（见 _process_round_end 的降级写），但即便事件缺失，也不该
        # 让用户后来的一行评分把当前最佳再采纳一次（统计重复）或记一条
        # 「拒绝当前最佳」的自相矛盾判定（最佳内容不会因此回退）。
        resolved.add(self.best.get("id"))
        for cid, score_comment in verdicts.items():
            if cid in resolved or cid in self._applied_verdicts:
                continue
            if cid not in candidates:
                # 引用了不存在的候选 id（抄错一个字符等）：静默忽略会让
                # 用户以为评分已提交，实际永远不生效。每个 id 只提示一次，
                # 避免长循环里每轮刷屏
                if cid not in self._warned_unknown_cids:
                    self._warned_unknown_cids.add(cid)
                    self.sink.warn(
                        f"rounds/verdicts.txt 里的候选 id「{cid}」不存在"
                        "（该行被忽略，请核对是否抄写错误）")
                continue
            score, comment = score_comment
            if score is None:
                # 解析不出的行按「挂起」处理（README：既不采纳也不丢弃）：
                # 记为「已决」会把候选永久锁死，用户修正这行也再翻不了案。
                # 每个 id 只警告一次（与未知 id 同一口径），见字段注释
                if cid not in self._warned_badscore_cids:
                    self._warned_badscore_cids.add(cid)
                    self.sink.warn(f"候选 {cid} 的评分行无法解析（保持挂起）："
                                   f"请改为「{cid} <0-10分> [评语]」")
                continue
            round_no = candidates[cid].get("round", 0)
            if not _valid_round(round_no):
                # 历史行被外部编辑/其他工具写入时可能是合法 JSON 但类型
                # 不对的 round（字符串、true……）。原样写进 best.json 会让
                # finish() 的 `best["round"] > 0` 比较抛 TypeError（汇总
                # 整段丢失），下次启动也会因 _valid_best 拒绝而跳过该采纳
                # 事件、把最佳回退到更早的记录。与 _recover_best 同一口径：
                # round 不可信时按 0（基线轮次）归一化，采纳本身照常兑现
                # （候选 id 与快照仍然有效，不能因元数据坏而丢失产物）
                self.sink.warn(f"候选 {cid} 的历史轮次字段不可用"
                               f"（{round_no!r}），已按第 0 轮记账")
                round_no = 0
            adopted = score >= self.cfg.rounds.adopt_score
            text = None
            if adopted:
                # 先读快照再记「已决」事件：读不到就还是挂起，不能先写
                # 一条 adopted 事件把候选锁死——快照恢复后也兑现不了
                cand_path = self.dir / f"{CAND_PREFIX}{cid}.md"
                try:
                    text = cand_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as e:
                    self.sink.warn(f"采纳旧候选 {cid} 失败（快照不可读，保持挂起）：{e}")
                    continue
                # 快照写入后可能被外部截断/篡改：补分晋升前必须重新校验
                # 区块结构（与 _process_round_end / _adopt 同一不变量——
                # 损坏内容绝不进 best.md）。保持挂起而不是拒绝，与「快照
                # 不可读」同口径：用户修复快照后补分仍能兑现
                if not _structure_intact(text):
                    self.sink.warn(f"采纳旧候选 {cid} 失败（快照区块标记"
                                   "损坏，保持挂起）")
                    # 快照损坏前若曾晋升写盘失败，research.md 可能仍残留
                    # 该候选内容：顺手还原最佳，保证下一轮从最佳出发
                    self._restore_best(round_no, why="候选快照结构损坏")
                    continue
            verdict = Verdict(verifier="user", score=score,
                              result="adopted" if adopted else "rejected",
                              reason=f"用户补评分 {score:g}",
                              comment=comment)
            best: Dict = {}
            if adopted:
                # 先把最佳写盘、再记「已决」事件：best.md/best.json 写盘
                # 失败（磁盘满 / 目录只读……）时必须保持挂起——已决事件
                # 会让本函数永久跳过该候选（resolved），用户腾出磁盘后也
                # 再翻不了案，而汇总还会一边虚报「采纳 1」一边留着旧最佳。
                # 与上面「先读快照再记已决」同一口径：外部副作用成功前
                # 不能留下不可撤销的结论。写盘顺序见 _commit_best：内容源
                # best.md 最后提交，半途失败不会把未采纳的候选内容泄漏为
                # 下一轮的还原源
                best = {"id": cid, "round": round_no, "verifier": "user",
                        "score": score, "ts": _ts(), "late": True,
                        "reason": verdict.reason}
                try:
                    self._commit_best(text, best)
                except OSError as e:
                    self.sink.warn(f"采纳旧候选 {cid} 失败（最佳写盘失败，"
                                   f"保持挂起）：{e}")
                    continue
            # 已决事件是补分兑现的审计/去重依据，但写盘失败不能反过来
            # 阻断兑现：采纳候选时 best.md/best.json 已经成功落盘，
            # 此时抛异常会让 self.best/统计停在旧值（调用方只看到
            # 「补分失败，稍后重试」），下一次兑现又会重复写盘/统计；
            # 拒绝同样会漏记统计。事件缺失用内存 _applied_verdicts 去重。
            try:
                self._append_event({"event": "verdict", "id": cid,
                                    "round": round_no, "late": True,
                                    **_verdict_fields(verdict)})
            except Exception as e:  # noqa: BLE001 —— 守卫降级原则
                self.sink.warn(f"记录补分判定事件失败（判定已生效，忽略）：{e}")
            self._applied_verdicts.add(cid)
            # 统计与改判同步：采纳/拒绝是对「本次运行兑现的判定」的计数
            # （跨会话旧候选也计入，否则汇总会一边宣布晋升、一边报
            # 「采纳 0」）；pending 只回减本会话计入过待评分的候选，
            # 跨会话候选从未加过，绝不能把它减成负数
            self._pending_ids.discard(cid)
            if adopted:
                self.best = best
                self._count_adopted(cid)
            else:
                self._count_rejected(cid)
            if not adopted:
                self.sink.info(f"旧候选 {cid} 获用户补评 {score:g}，"
                               "未达阈值，保持当前最佳")
                continue
            # 前进式采纳旧快照：内容成为新最佳，并写回状态文件，
            # 下一轮直接从它继续（不改写 history.jsonl 的既有记录）
            cur = self._read_state_text()
            changed: List[str] = []
            for name, key in ((state.SECTION_IDEA, "idea"),
                              (state.SECTION_ARTIFACT, "artifact")):
                want = _readable_section(text, name)
                if want is None:
                    want = ""
                have = _readable_section(cur, name)
                if want != have:
                    try:
                        state.update_section_file(self.state_path, name, want)
                        changed.append(key)
                    except (OSError, ValueError) as e:
                        self.sink.warn(f"写回区块失败（{name}）：{e}")
            # 回写最佳也是一次实际还原：与 restored 事件保持 1:1。无区块
            # 变化（research.md 已与快照一致）或写回失败时不能产生事件、
            # 也不能虚增统计（与 _restore_best 的无变化口径一致）
            if changed:
                self.stats.restored += 1
                try:
                    self._append_event({"event": "restored",
                                        "round": round_no,
                                        "why": "旧候选被补评采纳",
                                        "best": cid, "changed": changed})
                except Exception as e:  # noqa: BLE001 —— 守卫降级原则
                    self.sink.warn(f"记录还原事件失败（还原已生效，忽略）：{e}")
            self.sink.ok(f"旧候选 {cid} 获用户补评 {score:g}，"
                         "前进式晋升为最佳"
                         + ("并写回状态文件" if changed else
                            "（状态文件已与快照一致，无需写回）"))


# ----------------------------------------------------------------------
# 纯函数 / 展示辅助
def _verdict_fields(v: Verdict) -> Dict:
    return {"verifier": v.verifier, "score": v.score, "result": v.result,
            "reason": v.reason}


def verdesc(v: Verdict) -> str:
    d = f"{v.verifier}"
    if v.score is not None:
        d += f" {v.score:g} 分"
    if v.reason:
        d += f"：{v.reason}"
    return d


def detail_field(res: SuiteResult) -> str:
    tail = "\n".join((res.detail or "").splitlines()[-5:])
    return (res.reason + (f"｜输出尾部：{tail}" if tail else "")).strip()[:500]


def _last_comment(text: str, max_lines: int = 5) -> str:
    """评审输出里除「评分: N」行外的最后几行，当评语展示。"""
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not any(p.search(ln) for p in _SCORE_PATTERNS)]
    return " / ".join(lines[-max_lines:])[:300]
