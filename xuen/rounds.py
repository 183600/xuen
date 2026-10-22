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
    ".ruff_cache", "build", "dist", "CVS", "_darcs", "{arch}",
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
    + r"|[^:\s#;\\=]|\\(?:[^\s]|[ \t]+(?![ \t])))+")
# 逻辑行内的词分隔：空白，或反斜杠续行。make 把续行与周围空白压成一个
# 空格（`test \` + `foo:` 与 `test foo:` 等价、`test\` + `:` 与 `test :`
# 等价），目标列表跨续行时同样要能识别 test；续行进入词内部则拆成两个
# 词（`te\` + `st:` 是目标 te 与 st），与加空格的行为一致。
_MAKE_SEP = r"(?:[ \t]|\\\r?\n)"
# 目标列表内部的词分隔还包含未转义等号。GNU make 把目标列表里的 `=`
# 也当作词分隔符（`foo test=1:` 定义 foo / test / 1 三个目标；
# `test\=1:` 才是名为 test=1 的目标）。`+=` / `?=` 的运算符前缀也属于
# 分隔符：`test+=1:` 定义 test 与 1，但 `test!=1:` 的目标名是 test!。
# 赋值形式检测（test 后紧跟 `= x`）仍只用 _MAKE_SEP，不能把 `test==x`
# 里的第二个等号吃掉。
_MAKE_TARGET_SEP = r"(?:[ \t]|[+?]?=|\\\r?\n)"
# test 之前的目标名也可以含未转义的 %：GNU make 4.3 只有在【第一个
# 目标】是模式时才会报 fatal 的 mixed implicit and normal rules；第一个
# 目标是普通名时只警告 deprecated syntax 并继续定义 test（`foo %test
# test:` 仍能执行 test）。正则先放行 %，首目标是否为模式交给
# _make_mixed_targets_are_fatal 判断，避免漏掉可运行套件。
_MAKE_TARGET_WORD_BEFORE_TEST = _MAKE_TARGET_WORD
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
    # 目标名前的 `./`（可重复，如 `./test` / `.//test` / `././test`）
    # 会被 make 规范化掉，`make test` 仍能命中该目标；这不是模式规则，
    # 不能漏探测。`../test` / `foo/./test` 则与 test 不同名。
    r"(?:" + _MAKE_TARGET_WORD_BEFORE_TEST + _MAKE_TARGET_SEP + r"+)*"
    r"(?:\./+)*test"
    # test 后可以继续跟目标名（`test foo=bar:` 定义 test / foo / bar）。
    # 行首的 `test = bar:` / `test := x` 已在 _make_expand_simple_vars
    # 里按变量赋值整行剔除，不需要在这里做赋值的负向前瞻——那会误伤
    # `foo test =1:`（make 定义 foo / test / 1）。
    r"(?:" + _MAKE_TARGET_SEP + r"+" + _MAKE_TARGET_WORD + r")*"
    # GNU make 4.3 的 grouped target 用 `&:` 分隔，且不要求 & 前有空白
    # （`test&:` 与 `test &:` 都定义可执行的 test 目标）；`test& :` 则是
    # 名为 test& 的普通目标，不能命中。
    + _MAKE_TARGET_SEP + r"*(?:&)?:"
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
        if ch == "$" and i + 1 < n:
            if text[i + 1] in "({":
                opener = text[i + 1]
                closer = ")" if opener == "(" else "}"
                depth = 1
                j = i + 2
                while j < n and depth:
                    cj = text[j]
                    if cj == opener:
                        depth += 1
                    elif cj == closer:
                        depth -= 1
                    j += 1
                i = j
            else:
                # `$;`、`$#` 等单字符变量引用内部的分号/井号不是注释或
                # 同行命令起点；它们展开后可能正好是规则分隔符之前的空白。
                i += 2
            continue
        if ch == ":":
            return i
        i += 1
    return -1


# GNU make 的变量名可含除空白、:、#、=、; 之外的字符（/ % + @ ! ^ & * 等
# 都是合法的 target-specific 变量名）；只允许 [A-Za-z0-9_.-] 会把
# `test: X/Y=1` 这类「只有变量赋值、没有可执行 test 目标」的 Makefile
# 误判成有测试套件。反斜杠转义的下一个字符属于名字本身，但空白、:、#
# 不行：`test: X\ Y=1` 是前置依赖 `X Y=1`，`test: X\:Y=1` 也是依赖，
# 它们都不是 target-specific 变量赋值。反斜杠本身仍可作名字的最后一个
# 字符（`test: X\ =1` 的变量名是 `X\`）。
_MAKE_VAR_NAME_UNIT = r"(?:\\[^\s#:=]|\\|[^\s:#=;\\\x00-\x02])+"
_MAKE_TARGET_SPECIFIC_ASSIGNMENT = re.compile(
    r"(?:(?:export|private|override)[ \t]+)*"
    r"(?:" + _MAKE_VAR_NAME_UNIT + r"[ \t]*)?"
    r"(?:::=|::=|:=|[+?]?=|!=)"
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
    rest = line[start:].lstrip(" \t")
    # `+=` / `?=` / `!=` 紧跟在分隔符后是空变量名（make 报 empty
    # variable name），不是 target-specific 赋值；正则的变量名单元
    # 会把 `+`/`?`/`!` 吃成名字，需要先排除这种运算符开头的写法。
    # `+ =x` / `+?=x` 的变量名非空，仍是合法赋值。
    modifier = re.match(r"(?:(?:export|private|override)[ \t]+)*",
                        rest)
    if re.match(r"(?:\+=|\?=|!=)", rest[modifier.end():]) is not None:
        return False
    return _MAKE_NAMED_TARGET_ASSIGNMENT.match(rest) is not None


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


def _make_rule_header_rest_end(rest: str) -> int:
    r"""返回冒号后属于规则头/前置依赖的结束位置。

    make 优先用未转义的分号分隔同行 recipe；没有未转义分号时，GNU make
    4.3 会把第一个转义分号当分隔符。例如 `test: a\;b X:=1` 定义 test，
    依赖 a，recipe 是 `b X:=1`；但 `test: a\;b:c ; recipe` 里后面的
    未转义分号让 `a\;b:c` 整体进入依赖列表，第二个冒号仍需校验。
    """
    i = 0
    escaped = -1
    while i < len(rest):
        ch = rest[i]
        if ch == "\\":
            if i + 1 < len(rest) and rest[i + 1] == ";":
                if escaped < 0:
                    escaped = i
            i += 2
            continue
        if ch == "$" and i + 1 < len(rest) and rest[i + 1] in "({":
            # 变量引用内部的分号是参数，不是同行 recipe 分隔符：
            # `test: $(addprefix ;,)` 展开后依赖列表为空，不能在这里
            # 截断成未闭合的 `$(addprefix ` 而误报读取失败。
            opener = rest[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 1
            j = i + 2
            while j < len(rest):
                cj = rest[j]
                if cj == opener:
                    depth += 1
                elif cj == closer:
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            i = j
            continue
        if ch == "#":
            break
        if ch == ";":
            return i
        i += 1
    return escaped if escaped >= 0 else len(rest)


def _make_mixed_targets_are_fatal(targets: str) -> bool:
    """目标列表首词是模式时，混入普通目标会让 make 直接停止解析。

    GNU make 4.3 对 `%test test:` 报 fatal error，但对 `foo %test test:`
    只警告 mixed implicit and normal rules: deprecated syntax，并继续把
    test 定义为普通目标。决定 fatal 与否的是第一个目标是否为模式；这里
    只做这一项判断，是否真的含 test 已由调用方的正则保证。
    """
    words = re.findall(r"(?:\\.|[^\s=])+", targets)
    return bool(words) and _make_pattern_wildcard(words[0])[0] >= 0


def _make_targets_mix_pattern_and_normal(targets: str) -> bool:
    """首个目标是模式，且同一规则里还混有普通目标。

    GNU make 4.3 只在首个目标是模式时把这种混用当成 fatal
    （`%test foo:` 失败；`foo %test:` 只警告并继续解析）。分组标记
    末尾的单独 `&` 不是目标。
    """
    words = re.findall(r"(?:\\.|[^\s=])+", targets)
    if words and words[-1] == "&" and targets.endswith("&"):
        # 只有紧贴规则分隔符的 `&` 是 grouped 标记；`%test & :` 里的
        # `&` 本身是普通目标，仍构成 mixed implicit and normal rules。
        words.pop()
    if not words or _make_pattern_wildcard(words[0])[0] < 0:
        return False
    kinds = [_make_pattern_wildcard(word)[0] >= 0 for word in words]
    return not all(kinds)


def _make_rule_header_is_valid(line: str, colon: int) -> bool:
    """检查已命中 test 目标的规则头里的第二个冒号是否合法。

    普通规则里前置依赖不能再出现未转义冒号（test: a:b / test: dep: x
    都会让 make 报 target pattern contains no '%'）；唯一例外是静态模式
    规则 test: %.o: %.c——第二个冒号前必须恰好是一个含未转义 % 的
    target-pattern（test: foo bar: dep 会报 multiple target patterns）。
    变量引用可能展开出 %，静态检查无法确定，沿用原来的探测口径。
    """
    # 目标列表紧贴着规则分隔符、且末尾是奇数个 `$` 时，make 会把最后的
    # `$` 与 `:` 拼成变量引用（`a $:` / `a x$:` / `a \$:` 都报 missing
    # separator，后面的 test 目标也不会生效）；`$$` 是字面 `$`，不受影响。
    targets = line[:colon]
    if _make_mixed_targets_are_fatal(targets):
        return False
    if targets.endswith("$") and (
            len(targets) - len(targets.rstrip("$"))) % 2 == 1:
        return False
    start = colon + 1
    if start < len(line) and line[start] == ":":
        start += 1
    # target-specific 赋值可能使用 := / ::=，其冒号会被误当成静态模式
    # 规则的第二个冒号；变量名里又允许 %（如 `test: X%Y:=1`），不能靠
    # 「第二个冒号前有 %」放行。先按赋值语义识别，这类行不是可执行规则。
    if _make_target_specific_assignment(line[start:]):
        return False
    rest_end = start + _make_rule_header_rest_end(line[start:])
    second = _make_unescaped_colon(line[:rest_end], start)
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


def _make_has_recipe_separator(rest: str, *,
                               skip_refs: bool = False) -> bool:
    """规则头剩余部分是否有未转义、未进注释的同行命令分隔符 ;。

    skip_refs 用于原始文本：变量引用内部的分号只是参数，make 要等展开后
    才可能把它变成分隔符，不能先当成 recipe 起点。
    """
    i = 0
    n = len(rest)
    while i < n:
        ch = rest[i]
        if ch == "\\":
            i += 2
            continue
        if skip_refs and ch == "$" and i + 1 < n and rest[i + 1] in "({":
            opener = rest[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 1
            j = i + 2
            while j < n:
                cj = rest[j]
                if cj == opener:
                    depth += 1
                elif cj == closer:
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            i = j
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
    rest = line[colon + 1:]
    # 与 _make_rule_header_rest_end 同口径：没有未转义分号时，GNU make 4.3
    # 会把第一个 `\;` 当同行 recipe 分隔符（`test &: foo\;bar` 不报
    # grouped targets must provide a recipe），不能只看未转义分号。
    if _make_has_recipe_separator(rest) or "\\;" in rest:
        return True
    pos = line_end + 1 if line_end < len(text) else len(text)
    while pos < len(text):
        end = text.find("\n", pos)
        if end < 0:
            end = len(text)
        nxt = text[pos:end]
        # 制表符开头的行就是 recipe（哪怕内容只是 shell 注释或空行）；
        # 只有非 recipe 的空白/注释行才允许出现在目标与 recipe 之间。
        if nxt.startswith("\t"):
            return True
        stripped = nxt.strip()
        if not stripped or stripped.startswith("#"):
            pos = end + 1
            continue
        return False
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


def _make_target_words(text: str) -> List[str]:
    """按 make 的词法切分目标列表，把整个 `$(...)`/`${...}` 当作一个词。

    变量引用内部可以有空白与字面 `test`（`$(flavor test foo, ...)`），
    它们不是目标名。按空白直接切会把内部的 test 当成目标，再和真实的
    `test:` 规则比较冒号风格，误报 `: / ::` 冲突。
    """
    words: List[str] = []
    buf: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            buf.append(text[i:i + 2])
            i += 2
            continue
        if ch == "$" and i + 1 < n and text[i + 1] in "({":
            opener = text[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 1
            j = i + 2
            while j < n and depth:
                cj = text[j]
                if cj == opener:
                    depth += 1
                elif cj == closer:
                    depth -= 1
                j += 1
            buf.append(text[i:j])
            i = j
            continue
        if ch.isspace():
            if buf:
                words.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        words.append("".join(buf))
    return words


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
                or _MAKE_EMPTY_VAR_ASSIGNMENT.match(body) is not None
                # 行首 export/unexport/vpath 等是读取指令，不是规则头：
                # `export test::` 只把变量名 test 导出、`vpath test:...`
                # 只是搜索路径，后面的合法 test 规则仍可执行，不能把
                # 它们当成 test 的 :: / : 规则制造冲突。
                or _MAKE_EXPORT_DIRECTIVE.match(body) is not None
                or _MAKE_NON_RULE_DIRECTIVE.match(body) is not None):
            continue
        colon = _make_unescaped_colon(body, 0)
        if colon < 0 or _make_rule_is_target_specific(body, colon):
            continue
        double = body[colon:colon + 2] == "::"
        raw_targets = body[:colon]
        # 只有紧贴规则分隔符的 `&` 才是 grouped 标记；`foo& :` 里的 &
        # 与冒号之间有空白，是名为 foo& 的普通目标，不能剥成 foo。
        grouped_marker = raw_targets.endswith("&")
        words = _make_target_words(raw_targets)
        for index, word in enumerate(words):
            last_word = index == len(words) - 1
            # 只有最后一个目标词的末尾 `&` 是 grouped 标记；
            # `test& foo:` 里的 test& 是普通目标名，不能当成 test。
            if last_word and grouped_marker and word.endswith("&"):
                word = word[:-1]
            # 行首/目标前的 `\;` 会被 make 丢弃，`\;test&::` 实际仍是
            # test 的 grouped 双冒号规则；不剥掉前缀会漏掉与已有 test:
            # 的 :/:: 冲突，整份 Makefile 读取失败却被误判成套件。
            while word.startswith("\\;"):
                word = word[2:]
            # 目标列表里的未转义 `=` 也是词分隔符：`test=1::` 同时定义
            # test 与 1，且两者都带 `::`。展开阶段会把规则目标名里的
            # 字面等号换成 \x04，_make_target_word_units 两种都切。
            units = _make_target_word_units(word)
            for unit_index, unit in enumerate(units):
                if (last_word and grouped_marker
                        and unit_index == len(units) - 1
                        and unit.endswith("&")):
                    unit = unit[:-1]
                while unit.startswith("\\;"):
                    unit = unit[2:]
                # make 会把目标名前的 `./` / `.//` 规范化掉，`./test`
                # 与 `test` 是同一条规则；不规整会漏掉 :/:: 冲突。
                unit = re.sub(r"^(?:\./+)+", "", unit)
                if not unit or _make_pattern_wildcard(unit)[0] >= 0:
                    # 模式规则允许同一模式分别用 : 和 :: 定义，make
                    # 不会报 both : and :: entries；只有具体目标才做
                    # 冲突检查。
                    continue
                previous = styles.get(unit)
                if previous is None:
                    styles[unit] = double
                elif previous != double:
                    return True
    return False


_MAKE_EMPTY_TARGET_ASSIGNMENT = re.compile(r"^(?:::=|::=|:=|[+?]?=|!=)")

# 展开阶段会把变量赋值/define 等行替换成注释，但 make 读取时它们会清空
# 「当前目标」：紧跟其后的 tab 行属于 recipe commences before first target。
# 真正由用户写的注释不会清空上下文，所以这里用一个带控制字符的注释作为
# 哨兵，让 _make_has_recipe_before_first_target 能区分两者。
_MAKE_CONTEXT_RESET = "#\x02"


# private / override 不列入：后面跟规则头时它们是普通目标名
# （`private foo:` / `override foo:` 都定义 foo），只有跟变量赋值/
# define 时才是修饰符；赋值行已由 _MAKE_VAR_ASSIGNMENT 跳过。
_MAKE_NON_RULE_DIRECTIVE = re.compile(
    # private / override 只能修饰 undefine；它们后面跟其他指令关键字
    # （`private export foo`）或规则头（`private foo:`）时是普通目标名。
    r"^[ \t]*(?:(?:(?:private|override)[ \t]+)*undefine"
    r"|include|sinclude|-include|vpath|export|unexport|define)(?:[ \t]|$)")


def _make_has_grouped_target_without_recipe(text: str) -> bool:
    """任一 grouped target 缺少 recipe 都会让 make 读取失败。

    `foo&: dep` / `foo&:` 后面没有同行 `;` 或 tab recipe 时，make 报
    `grouped targets must provide a recipe`；即使别处有合法 test 目标也
    不会执行。原先只校验命中 test 的 grouped 目标，其他目标的同类错误
    会被漏掉。裸 `&:`（目标列表为空或只有一个 `&`）是 make 接受的空规则，
    不在此列。
    """
    pos = 0
    for raw in text.splitlines(keepends=True):
        body = raw.rstrip("\r\n")
        if body and not body.startswith("\t"):
            stripped = body.lstrip(" \t")
            if (stripped and not stripped.startswith("#")
                    and _MAKE_VAR_ASSIGNMENT.match(body) is None
                    and _MAKE_EMPTY_VAR_ASSIGNMENT.match(body) is None
                    and _MAKE_NON_RULE_DIRECTIVE.match(body) is None):
                colon = _make_unescaped_colon(body, 0)
                targets = body[:colon].lstrip(" \t") if colon >= 0 else ""
                if (colon > 0 and targets not in ("", "&")
                        and body[colon - 1] == "&"
                        # `foo&: X=1` 是 target-specific 变量赋值，make 不
                        # 要求它带 recipe；只有真正的 grouped target 缺
                        # recipe 才会报错。
                        and not _make_rule_is_target_specific(body, colon)):
                    if not _make_grouped_target_has_recipe(
                            text, body, colon, pos + len(body)):
                        return True
        pos += len(raw)
    return False


def _make_target_list_has_bare_trailing_dollar(targets: str) -> bool:
    r"""目标列表末尾的奇数次 `$` 是否吃掉了规则分隔符。

    `foo $:` 里的 `$:` 是单字符变量引用，冒号被吃掉后整行没有规则
    分隔符，make 报 missing separator；`$:` / `$x$:` 这类只剩变量引用
    的整行展开为空目标列表，make 反而接受。判断时先跳过变量引用与转义
    字符，只有还剩下真实字符时才认为会报错。
    """
    if not targets.endswith("$"):
        return False
    if (len(targets) - len(targets.rstrip("$"))) % 2 == 0:
        return False
    i = 0
    real = False
    last = len(targets) - 1
    while i < last:
        ch = targets[i]
        if ch == "\\":
            # 反斜杠后的字符是字面目标名，不是变量引用，算真实字符。
            real = True
            i += 2
            continue
        if ch == "$" and i + 1 < last:
            if targets[i + 1] in "({":
                opener = targets[i + 1]
                closer = ")" if opener == "(" else "}"
                depth = 1
                j = i + 2
                while j < len(targets) and depth:
                    if targets[j] == opener:
                        depth += 1
                    elif targets[j] == closer:
                        depth -= 1
                    j += 1
                i = j
                continue
            i += 2
            continue
        if not ch.isspace():
            real = True
        i += 1
    return real


def _make_target_list_only_variable_refs(targets: str) -> bool:
    """目标列表是否只由变量引用/空白组成、且以裸 `$` 结尾。"""
    if not targets.endswith("$"):
        return False
    if (len(targets) - len(targets.rstrip("$"))) % 2 == 0:
        return False
    i = 0
    last = len(targets) - 1
    while i < last:
        ch = targets[i]
        if ch == "\\":
            return False
        if ch.isspace():
            i += 1
            continue
        if ch == "$" and i + 1 < last:
            if targets[i + 1] in "({":
                opener = targets[i + 1]
                closer = ")" if opener == "(" else "}"
                depth = 1
                j = i + 2
                while j < len(targets) and depth:
                    if targets[j] == opener:
                        depth += 1
                    elif targets[j] == closer:
                        depth -= 1
                    j += 1
                i = j
                continue
            i += 2
            continue
        return False
    return True


def _make_target_text_only_refs(text: str) -> bool:
    """目标文本是否只由变量引用、空白和 grouped 标记 `&` 组成。"""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace() or ch == "&":
            i += 1
            continue
        if ch == "\\":
            return False
        if ch == "$" and i + 1 < n:
            if text[i + 1] in "({":
                opener = text[i + 1]
                closer = ")" if opener == "(" else "}"
                depth = 1
                j = i + 2
                while j < n and depth:
                    cj = text[j]
                    if cj == "$" and j + 1 < n and text[j + 1] in "({":
                        depth += 1
                        j += 2
                        continue
                    if cj == closer:
                        depth -= 1
                    j += 1
                i = j
                continue
            i += 2
            continue
        return False
    return True


def _make_has_bare_trailing_dollar_rule(text: str) -> bool:
    r"""原始文本里是否有目标列表以裸 `$` 吃掉规则分隔符的规则。

    `foo $:` 在展开前就因 `$:` 变量引用吃掉冒号而缺少规则分隔符，make
    报 missing separator。变量展开阶段会把这类行整个展开掉，后续的规则
    结构检查就看不到冒号了，所以必须在展开前单独扫一遍。`$:` / `$x$:`
    这类只剩变量引用的行展开为空目标列表，make 接受，交给
    _make_target_list_has_bare_trailing_dollar 判断。
    """
    define_depth = 0
    for line in text.splitlines():
        body = line.rstrip("\r")
        if not body:
            continue
        if define_depth:
            if _MAKE_DEFINE_LINE.match(body) is not None:
                define_depth += 1
            elif _MAKE_ENDEF_LINE.match(body) is not None:
                define_depth -= 1
            continue
        if body.startswith("\t"):
            continue
        stripped = body.lstrip(" \t")
        if not stripped or stripped.startswith("#"):
            continue
        if _MAKE_DEFINE_LINE.match(body) is not None:
            define_depth = 1
            continue
        if (_MAKE_VAR_ASSIGNMENT.match(body) is not None
                or _MAKE_EMPTY_VAR_ASSIGNMENT.match(body) is not None
                or _MAKE_NON_RULE_DIRECTIVE.match(body) is not None):
            continue
        colon = _make_unescaped_colon(body, 0)
        if colon < 0:
            continue
        targets = body[:colon]
        bare = _make_target_list_has_bare_trailing_dollar(targets)
        only_refs = _make_target_list_only_variable_refs(targets)
        if not bare and not only_refs:
            continue
        if (only_refs
                and re.match(r"^[ \t]*(?:[;#]|$)", body[colon + 1:])):
            # `$:` / `$x$:` 后面没有内容（或只有注释/同行命令）时，
            # `$:` 吃掉冒号后整行展开为空目标列表，make 接受。
            continue
        if colon + 1 < len(body) and body[colon + 1] == ":":
            # `foo $::`：`$:` 吃掉第一个冒号，第二个冒号仍是规则分隔符。
            # 目标前缀只有变量引用（`$x$::` / `$::`）时整行仍接受；
            # `foo $::$(X)=1` 则是 target-specific 赋值，变量名为空时
            # 由展开阶段的 raw 检查报错，不能在这里直接放过。
            if _make_target_text_only_refs(targets[:-1]):
                continue
        # `$:` 吃掉冒号后，前缀与剩余文本会拼成一行重新解析：
        # `foo$:X:=1` 是变量 `fooX` 的赋值（make 接受）。纯变量引用
        # 目标（`$x$:`）展开后前缀可能为空，只接受无空白的普通赋值，
        # 无法静态判断空动态变量名时仍保守拒绝。
        suffix = body[colon + 1:]
        suffix_at_start = not suffix.startswith((" ", "\t"))
        rebuilt = targets[:-1] + suffix
        spaced = (bare and len(targets) >= 2
                  and targets[-2] in " \t")
        if spaced and _make_unescaped_colon(rebuilt, 0) < 0:
            # `foo $:X=1` / `foo $: =x` / `foo $:+=1`：`$` 是独立目标
            # 词，吃掉冒号后 make 不会把 `foo X=1` 重新当成变量赋值，
            # 而是报 missing separator。
            return True
        if spaced and re.match(r"(?:::=|::=|:=|[+?]?=|!=)",
                               suffix.lstrip(": \t")):
            # `foo $::=x` / `foo $:::=x`：`$` 是独立目标词时，剩余冒号
            # 是规则分隔符，后面的 `=x` 是空变量名，而不是把整行重建成
            # `foo :=x` 赋值。
            return True
        if bare and suffix_at_start and not only_refs and not spaced:
            if (_MAKE_VAR_ASSIGNMENT.match(rebuilt) is not None
                    or _MAKE_DYNAMIC_VAR_ASSIGNMENT.match(rebuilt)
                    is not None):
                continue
        elif (only_refs and suffix_at_start
                and _MAKE_VAR_ASSIGNMENT.match(suffix) is not None):
            continue
        escaped_dollar = False
        if targets.endswith("$"):
            slashes = 0
            pos = len(targets) - 2
            while pos >= 0 and targets[pos] == "\\":
                slashes += 1
                pos -= 1
            escaped_dollar = slashes % 2 == 1
        if (bare or only_refs) and not escaped_dollar:
            # `$:` 吃掉冒号后 make 只看剩余文本里是否还有规则分隔符：
            # 重建行 `X:::=1` / `X\:Y=1` 仍会让整个 Makefile 读取失败，
            # 必须按无套件处理，不能被后续展开洗成合法赋值。
            if _make_has_missing_separator_line(rebuilt):
                return True
            if (_make_unescaped_colon(rebuilt, 0) >= 0
                    and _make_has_invalid_extra_rule_colon(rebuilt)):
                return True
        # `$:` 只吃掉紧邻的冒号；规则头剩余部分若还有未转义冒号，整行
        # 仍可能被 make 接受（`foo $: a:b` 定义目标 foo a）。只有后续
        # 再没有冒号，或第一个剩余冒号属于 `:=`（空变量名）时才失败。
        i = colon + 1
        later = -1
        while i < len(body):
            ch = body[i]
            if ch == "\\":
                i += 2
                continue
            if ch in "#;":
                break
            if ch == ":":
                later = i
                break
            i += 1
        if later < 0:
            # `foo$:$(X)=1` / `$:$(X)=1` 的 `$:` 吃掉冒号后剩
            # `foo$(X)=1` / `$(X)=1`，是合法的动态变量名赋值（make
            # 接受），不是缺少分隔符。纯变量引用目标只在重建行确实是
            # 赋值时放过；`$x$:foo` 这类展开后没有分隔符的行仍报错。
            rebuilt = targets[:-1] + body[colon + 1:]
            if (suffix_at_start
                    and (_MAKE_VAR_ASSIGNMENT.match(rebuilt) is not None
                         or _make_dynamic_assignment_name(rebuilt) is not None
                         or _MAKE_DYNAMIC_VAR_ASSIGNMENT.match(rebuilt)
                         is not None)):
                continue
            return True
        if later + 1 < len(body) and body[later + 1] == "=":
            return True
    return False


def _make_targets_have_internal_escaped_semicolon(targets: str) -> bool:
    r"""目标列表里是否有需要同行分隔符的原始 `\;`。

    make 4.3 对目标名里的 `\;` 有限制：没有同行命令分隔符时整行报
    missing separator。行首（前导空白后）连续的 `\;` 是特例，会在展开
    阶段单独剥离/忽略；本函数只扫描引用之外剩余的 `\;`。
    """
    i = 0
    n = len(targets)
    while i < n:
        ch = targets[i]
        if ch == "$" and i + 1 < n and targets[i + 1] in "({":
            opener = targets[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 1
            j = i + 2
            while j < n:
                cj = targets[j]
                if cj == opener:
                    depth += 1
                elif cj == closer:
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            i = j
            continue
        if ch == "\\" and i + 1 < n and targets[i + 1] == ";":
            return True
        i += 2 if ch == "\\" else 1
    return False

def _make_has_invalid_extra_rule_colon(text: str) -> bool:
    """任一规则头的第二个未转义冒号是否让 make 读取失败。

    `foo: a:b`、`foo: :x`、`foo::: dep` 等不是合法规则，GNU make 会在
    读取阶段报 target pattern contains no '%' / missing target pattern。
    即使别处定义了 test，整份 Makefile 也不会执行。探测原先只校验命中
    test 的规则头，其他目标的非法冒号结构会让候选被误判成测试套件。
    """
    for line in text.splitlines():
        body = line.rstrip("\r")
        if not body or body.startswith("\t"):
            continue
        stripped = body.lstrip(" \t")
        if not stripped or stripped.startswith("#"):
            continue
        if (_MAKE_VAR_ASSIGNMENT.match(body) is not None
                or _MAKE_EMPTY_VAR_ASSIGNMENT.match(body) is not None):
            continue
        if _MAKE_NON_RULE_DIRECTIVE.match(body) is not None:
            continue
        colon = _make_unescaped_colon(body, 0)
        if colon < 0:
            continue
        targets = body[:colon].lstrip(" \t")
        if not targets or targets == "&":
            continue
        if _make_rule_is_target_specific(body, colon):
            # target-specific 赋值（`%test test: X+=1`）即使目标列表里
            # 模式与普通目标混用也合法，不能按 mixed 规则拒绝。
            continue
        if _make_targets_mix_pattern_and_normal(targets):
            # `%test foo:` / `test% & :` 等模式目标与普通目标混用；
            # 首个目标是模式时 make 读取即停止，即使别处有 test。
            return True
        if _make_target_list_has_bare_trailing_dollar(body[:colon]):
            # `foo $:` 的 `$:` 吃掉规则分隔符，make 在读取阶段报
            # missing separator；即使别处有 test 目标也无法执行。
            return True
        start = colon + 1
        if start < len(body) and body[start] == ":":
            start += 1
        rest = body[start:].lstrip(" \t")
        if _MAKE_EMPTY_TARGET_ASSIGNMENT.match(rest):
            return True
        if _MAKE_NAMED_TARGET_ASSIGNMENT.match(rest) is not None:
            continue
        rest_end = start + _make_rule_header_rest_end(body[start:])
        second = _make_unescaped_colon(body[:rest_end], start)
        if second < 0:
            continue
        target_pattern = body[start:second].strip(" \t")
        if not target_pattern:
            return True
        if _make_pattern_wildcard(targets.split()[0])[0] >= 0:
            # 模式目标后面再出现第二个冒号是 static pattern rule；
            # make 报 mixed implicit and static pattern rules（首个目标
            # 为普通名时只警告，因此这里同样看首目标）。
            return True
        i = 0
        has_percent = False
        while i < len(target_pattern):
            ch = target_pattern[i]
            if ch == "\\":
                i += 2
                continue
            if ch.isspace():
                return True
            if ch == "%":
                has_percent = True
            i += 1
        if not has_percent and "$" not in target_pattern:
            return True
    return False


def _make_has_recipe_before_first_target(text: str) -> bool:
    """在第一个真正的目标规则之前出现 recipe 行时，make 读取即失败。

    `X=1` / target-specific 赋值 / export 等指令之后紧跟制表符开头的
    recipe 行，GNU make 都会报 `recipe commences before first target`，
    即使文件后面另有合法的 test 目标也不会执行。探测若只看 test 行，
    会把这种 Makefile 当成可运行套件，随后 `make test` 失败并误伤候选。
    """
    seen_rule = False
    define_depth = 0
    for line in text.splitlines():
        body = line.rstrip("\r")
        if not body:
            continue
        if define_depth:
            # define 体不是 Makefile 语法，里面的 tab 行也不是 recipe。
            if _MAKE_DEFINE_LINE.match(body) is not None:
                define_depth += 1
            elif _MAKE_ENDEF_LINE.match(body) is not None:
                define_depth -= 1
            continue
        if body.startswith("\t"):
            # GNU make 在首个目标前允许制表符开头的空行/注释行（以及
            # `\t` 后只有变量引用且展开为空的读取期文本）；它们不是
            # recipe，不能据此判定 suite 不可运行。`\t# c` / `\t   `
            # 在真实 make 中会被忽略，后面的 test 目标照常执行。
            if not seen_rule and body[1:].lstrip(" \t").startswith("#"):
                continue
            if not seen_rule and not body[1:].strip():
                continue
            if not seen_rule:
                return True
            continue
        stripped = body.lstrip(" \t")
        if stripped.startswith(_MAKE_CONTEXT_RESET):
            # 变量赋值/define/include 等非规则行会清空当前目标；真正的
            # 用户注释不会，所以只有哨兵注释才重置。
            seen_rule = False
            continue
        if stripped.startswith("#"):
            continue
        if _MAKE_DEFINE_LINE.match(body) is not None:
            define_depth = 1
            seen_rule = False
            continue
        if _MAKE_NON_RULE_DIRECTIVE.match(body) is not None:
            seen_rule = False
            continue
        # 传入的是展开后的文本：变量赋值行已被 _make_expand_simple_vars
        # 替换成哨兵注释，因此这里仍带冒号的「赋值形」行其实往往是变量
        # 展开后的目标列表（如 `$(T) foo=bar test:`，T 为空）——不能按
        # 变量赋值跳过，否则会把随后的合法 recipe 误判成「首个目标前出现
        # recipe」。
        colon = _make_unescaped_colon(body, 0)
        if colon < 0:
            # 其他非规则行（export / vpath / $(info ...) 等）同样会清空
            # 当前目标。
            seen_rule = False
            continue
        targets = body[:colon].lstrip(" \t")
        if not targets or targets == "&":
            seen_rule = True
            continue
        if _make_rule_is_target_specific(body, colon):
            # target-specific 赋值不是可挂 recipe 的规则；make 会让随后的
            # tab 行报 recipe commences before first target。
            seen_rule = False
            continue
        seen_rule = True
    return False


_MAKE_ASSIGNMENT_OPERATORS = (":::=", "::=", ":=", "?=", "+=", "!=", "=")


def _make_name_without_refs(text: str) -> str:
    """遮住变量引用/转义字符，只留下会分隔变量名的字面空白。"""
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            out.append("X")
            i += 2
            continue
        if ch == "$" and i + 1 < n and text[i + 1] in "({":
            opener = text[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 1
            j = i + 2
            while j < n and depth:
                if text[j] == opener:
                    depth += 1
                elif text[j] == closer:
                    depth -= 1
                j += 1
            out.append("X")
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _make_assignment_lhs_has_space(body: str) -> bool:
    """独立赋值左侧在运算符前是否仍有空白分隔的多个词。

    `foo bar = x` / `$(X) $(strip ) := x` 的左侧字面空白会让 make 报
    missing separator 或 empty variable name；只有运算符前的尾部空白
    会被去掉。`export X Y = z` 是导出多个变量，属于特例。规则行
    （运算符前已有未转义冒号）是 target-specific 赋值/依赖列表，不按
    独立赋值处理。

    make 会跳过左侧有多词的运算符继续找下一个：`foo a=b := c` 里
    第一个 `=` 左侧多词，但后面的 `:=` 是立即赋值运算符，仍会让 make
    报 empty variable name，不能因为后面还有冒号就当成规则。
    """
    stripped = body.lstrip(" \t")
    if re.match(r"export(?:[ \t]+|$)", stripped) is not None:
        return False
    i = 0
    n = len(body)
    has_invalid = False
    has_immediate = False
    while i < n:
        ch = body[i]
        if ch == "#":
            break
        if ch == "\\":
            i += 2
            continue
        if ch == "$" and i + 1 < n and body[i + 1] in "({":
            opener = body[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 1
            j = i + 2
            while j < n and depth:
                if body[j] == opener:
                    depth += 1
                elif body[j] == closer:
                    depth -= 1
                j += 1
            if depth:
                return False
            i = j
            continue
        if ch == "$":
            # 单字符引用可能吃掉后面的冒号/等号（`$: = x`）。
            i += 2
            continue
        op = ""
        for candidate in _MAKE_ASSIGNMENT_OPERATORS:
            if body.startswith(candidate, i):
                op = candidate
                break
        if not op:
            i += 1
            continue
        lhs = body[:i]
        if _make_unescaped_colon(lhs, 0) >= 0:
            return False
        lhs = _make_name_without_refs(lhs).lstrip(" \t")
        for _ in range(2):
            modifier = re.match(
                r"(?:override|private)(?:[ \t]+|$)", lhs)
            if modifier is None:
                break
            lhs = lhs[modifier.end():]
        if not re.search(r"[ \t]", lhs.rstrip(" \t")):
            # 左侧是单个变量名，make 在这里就确定是赋值。
            return False
        if op in (":=", "::=", "!=", ":::="):
            has_immediate = True
        else:
            has_invalid = True
        i += len(op)
    if has_immediate:
        return True
    if has_invalid:
        # 延迟运算符左侧有多词时，make 会继续寻找后面的规则冒号；找到
        # 就按目标/依赖列表解析（`foo bar = x: y` 定义目标 foo/bar），
        # 没找到才是 missing separator。
        return _make_unescaped_colon(body, 0) < 0
    return False


def _make_has_missing_separator_line(text: str, *,
                                    expanded: bool = False) -> bool:
    """是否有会被 make 报 missing separator 的非规则行。

    `foo` / `test\\:` / `a\\:b` 这类既不是变量赋值、也不是读取指令的
    行没有规则分隔符，make 在读取阶段直接失败，后面的 test 目标不会
    执行。原先只扫描带冒号的行，导致这类错误被漏掉，可运行的 test 套件
    反被误判成「有套件」（实际 `make test` 失败后会误伤候选）。

    必须在变量展开前扫描：`$: ;` / `$x ;` 这类整行变量引用会展开成
    空目标列表并被执行，展开后就只剩一个 `;`，无法与真正的裸 `;`
    （missing rule before recipe）区分。行首 `$` 的写法交给后续的变量
    展开逻辑判断；展开为空的合法行不会再报错，展开成文本的由调用方
    继续按规则头处理。
    """
    define_depth = 0
    for line in text.splitlines():
        body = line.rstrip("\r")
        if not body:
            continue
        if define_depth:
            if _MAKE_DEFINE_LINE.match(body) is not None:
                define_depth += 1
            elif _MAKE_ENDEF_LINE.match(body) is not None:
                define_depth -= 1
            continue
        if body.startswith("\t"):
            continue
        stripped = body.lstrip(" \t")
        if (not stripped or stripped.startswith("#")
                or stripped.startswith(_MAKE_CONTEXT_RESET)):
            continue
        if expanded and stripped.startswith(";"):
            # `$: ;` / `$(X) ;` 的目标列表由空变量引用组成，展开后只剩
            # 同行命令；make 接受这种空目标规则，不能当成 missing
            # separator。字面 ` ;` 已在展开前的扫描里拒绝。
            continue
        if stripped.startswith("\\;"):
            # 目标词开头的 `\;` 会被 make 丢弃，整行即使没有规则分隔符
            # 也不报 missing separator（`\;test:` 定义 test，`\;`
            # 只是空行）；展开阶段也会产生这种行。但同行 recipe 分隔符
            # 会让 make 按规则解析：`\;test$: ; @true` 的 `$:` 吃掉冒号
            # 后仍因 recipe 报 missing separator，不能把整行忽略。
            if not _make_has_recipe_separator(body, skip_refs=True):
                continue
            indent = body[:len(body) - len(stripped)]
            body = indent + stripped[2:]
            stripped = body.lstrip(" \t")
        if _MAKE_DEFINE_LINE.match(body) is not None:
            define_depth = 1
            continue
        if expanded:
            # 展开后的扫描只看到「不是赋值、但展开结果像赋值」的行：
            # 真正的赋值行已在 _make_expand_simple_vars 里换成上下文
            # 哨兵。make 在展开前就决定一行是不是赋值，`X = =` 后的
            # `$(X)` 展开成 `=` 仍是缺失分隔符的规则头，不能因为展开
            # 文本匹配赋值正则就放过。
            if (_MAKE_NON_RULE_DIRECTIVE.match(body) is not None
                    or _MAKE_CONDITIONAL_LINE.match(body) is not None):
                continue
        elif (_MAKE_VAR_ASSIGNMENT.match(body) is not None
                or _make_dynamic_assignment_name(body) is not None
                or _MAKE_EMPTY_VAR_ASSIGNMENT.match(body) is not None
                or _MAKE_NON_RULE_DIRECTIVE.match(body) is not None
                or _MAKE_CONDITIONAL_LINE.match(body) is not None):
            continue
        if _make_assignment_lhs_has_space(body):
            return True
        raw_colon = _make_unescaped_colon(body, 0)
        if raw_colon >= 0:
            if _make_target_list_has_bare_trailing_dollar(body[:raw_colon]):
                # `foo$:...` 的 `$:` 会吃掉规则冒号，行是否合法由
                # _make_has_bare_trailing_dollar_rule 统一判定。
                continue
            if _make_rule_is_target_specific(body, raw_colon):
                # target-specific 变量赋值不定义可执行目标，GNU make
                # 不会对它的目标列表报 mixed implicit and normal rules：
                # `%test test: X+=1` 合法，后面的测试目标照常执行。
                continue
            if _make_targets_mix_pattern_and_normal(
                    _make_name_without_refs(
                        body[:raw_colon].lstrip(" \t"))):
                # `%\.o foo ?= a:b` 这类首个目标是模式、后面又混入普通
                # 目标的写法，即使含有赋值运算符，make 也会在读取期报
                # mixed implicit and normal rules。
                return True
            continue
        # `$#` / `$;` / `$:` 这类单字符引用会吃掉后面的字符：`test $#:`
        # 里的 `#` 不是注释起点、`test $::` 里第一个冒号被 `$:` 吃掉，
        # 但第二个冒号仍是规则分隔符。先遮住单字符引用再找规则冒号。
        masked: List[str] = []
        pos = 0
        while pos < len(body):
            if body[pos] == "$" and pos + 1 < len(body):
                if body[pos + 1] == "$":
                    # `$$` 是字面 `$`，不构成单字符引用；后面的冒号仍是
                    # 规则分隔符（`test $$:` 定义可执行的 test 目标）。
                    masked.append("$$")
                    pos += 2
                    continue
                if body[pos + 1] not in "({":
                    masked.append("\x03")
                    pos += 2
                    continue
            masked.append(body[pos])
            pos += 1
        if _make_unescaped_colon("".join(masked), 0) >= 0:
            continue
        if stripped.startswith("$"):
            # 单独一行 `$` / `$$` 展开不出任何 Makefile 语法，make 仍报
            # missing separator（eval 里常见于 `$(eval $$)`）。
            if not stripped.strip("$ \t"):
                return True
            continue
        return True
    return False


def _make_last_unescaped_colon(text: str) -> int:
    """返回 text 里最后一个未转义冒号的下标（无则 -1）。"""
    last = -1
    i = 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == ":":
            last = i
        i += 1
    return last


def _make_expanded_targets_end_with_colon(targets: str) -> bool:
    r"""展开后的单个目标词是否以裸冒号结尾并成为非法静态模式。

    `$(join test,:):` 展开后被 make 看成目标 `test:` 加规则分隔符，
    报 missing target pattern；`$(subst x,:,x):` 展开成 `::` 则是空
    目标列表，make 接受。只有裸冒号前还有字面目标名（且目标列表不是
    以冒号开头）时才按读取错误处理；`\:` 是目标名里的字面冒号。

    多个目标词的情况更复杂：`$(addprefix ...)` 整体展开成
    `test test:` 时 make 仍接受，因此这里只对单个目标词判定。
    """
    text = targets.strip(" \t")
    if not text or len(text.split()) != 1:
        return False
    last = _make_last_unescaped_colon(text)
    if last < 0 or last != len(text) - 1:
        return False
    prefix = text[:last].rstrip(" \t")
    if not prefix or prefix.lstrip(" \t").startswith(":"):
        return False
    return True


def _make_target_word_units(word: str) -> List[str]:
    """按 make 规则头词法再切分目标词：未转义 `=` 是词分隔符。

    `foo test=1:` 定义目标 foo / test / 1；`foo test+=1:` 的 `+`/`?`
    是紧贴 `=` 的运算符前缀，只吸收一个（`test++=1` 的目标是 test+）。
    没有 `=` 时，末尾的 `+`/`?` 属于目标名本身：`test+:` 只定义
    test+，不能当成 test 而与后面的 `test:` 误报冒号风格冲突。
    `test\\=1:` 里的等号被转义，属于目标名本身。
    """
    units: List[Tuple[str, bool]] = []
    buf: List[str] = []
    i = 0
    n = len(word)
    while i < n:
        ch = word[i]
        if ch == "\\" and i + 1 < n:
            buf.append(word[i:i + 2])
            i += 2
            continue
        if ch in ("=", "\x04"):
            # \x04 是展开阶段给规则目标名里的字面等号打的哨兵：
            # make 仍把 `test=1:` 的目标列表分成 test / 1，冲突检查
            # 必须按同样的词边界切分，否则 `$(X) test=1::` 与后面的
            # `test:` 冲突会被漏掉。
            units.append(("".join(buf), True))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    units.append(("".join(buf), False))
    result: List[str] = []
    for unit, before_equals in units:
        if before_equals and unit.endswith(("+", "?")):
            unit = unit[:-1]
        if unit:
            result.append(unit)
    return result


def _make_line_defines_test(line: str, colon: int) -> bool:
    """规则头的目标列表里是否有真正的 test 目标词。

    `_MAKE_TEST_TARGET` 允许目标词任意拼接，会把 `$(origin ./test , $<):`
    这类表达式内部的 `test` 当目标；多出来的 :: 又会和真实 test 规则
    触发伪冲突。按 make 词法切词后只认完整的 test / ./test 目标。

    只有目标列表的【最后一个词】末尾的 `&` 是 grouped 标记；`test& foo:`
    定义的是目标 `test&` 与 foo，不能把 `test&` 剥成 test。
    """
    targets = line[:colon]
    words = _make_target_words(targets)
    for index, word in enumerate(words):
        last_word = index == len(words) - 1
        if last_word and word.endswith("&"):
            word = word[:-1]
        while word.startswith("\\;"):
            word = word[2:]
        units = _make_target_word_units(word)
        for unit_index, unit in enumerate(units):
            if (last_word and unit_index == len(units) - 1
                    and unit.endswith("&")):
                unit = unit[:-1]
            if re.fullmatch(r"(?:\./+)*test", unit):
                return True
    return False


def _make_defines_test_target(text: str,
                              repo: Optional[Path] = None) -> bool:
    """规则头命中 test 且冒号结构合法时返回 True。"""
    if _make_has_mixed_target_colon_style(text):
        return False
    if _make_has_invalid_extra_rule_colon(text):
        return False
    if _make_has_grouped_target_without_recipe(text):
        return False
    if _make_has_recipe_before_first_target(text):
        return False
    saw_single = False
    saw_double = False
    for match in _MAKE_TEST_TARGET.finditer(text):
        if _make_continues_recipe_line(text, match.start()):
            continue
        line_end = _make_logical_line_end(text, match.start())
        line = text[match.start():line_end]
        if _MAKE_NON_RULE_DIRECTIVE.match(line):
            # `vpath test:$(X)=1` 是 vpath 指令（参数里恰好有 test:），
            # 不定义目标；不能因为它命中正则就否掉别处的合法 test 规则。
            continue
        colon = match.end() - match.start() - 1
        # 正则里的冒号可能落在目标名中的变量引用里（如
        # `test ${X:--x}` 并没有规则分隔符）。只有行内第一个真正的
        # 未转义冒号才是规则分隔符；不一致时说明这是变量引用里的冒号。
        if _make_unescaped_colon(line, 0) != colon:
            continue
        if not _make_line_defines_test(line, colon):
            # 正则可能命中变量引用内部的 test（如 $(origin ./test,...)）。
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
        words = _make_target_words(targets)
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
    # 变量名里的空白就是分隔符：`foo\ x=y` 不是名为 `foo x` 的赋值。
    # 反斜杠本身仍可作名字的最后一个字符（`foo\=bar` 是变量 foo\ = bar）。
    # `:` `#` `$` 即使转义也不能进入变量名：`a\\: = x` 会被 make 当作
    # 目标/空变量名错误，不能按赋值整行跳过，否则后面的 test 套件会误判。
    r"((?:\\[^\s=:#$]|\\|[^\s:#=$(){}])+?)[ \t]*(::=|:=|\?=|\+=|!=|=)[ \t]*(.*)$")

_MAKE_DYNAMIC_VAR_UNIT = (
    r"(?:\$\([^()\r\n]*\)|\$\{[^{}\r\n]*\}|\$[^\r\n]|\\[^\s=:#$]|\\"
    r"|[^\s:#=;$(){}])")
_MAKE_DYNAMIC_VAR_ASSIGNMENT = re.compile(
    r"^[ ]*(?:(?:export|override|private)[ \t]+)*"
    r"(" + _MAKE_DYNAMIC_VAR_UNIT + r"+?)[ \t]*"
    r"(::=|:=|\?=|\+=|!=|=)[ \t]*(.*)$")

# GNU make 4.3 不把 `:::=` 当成赋值运算符：行首 `:::=x` 是空目标列表的
# target-specific 赋值（make 接受），而 `::=x` / `:=x` / `=x` 才是空变量
# 名错误。这里不能把 `:::=` 列入，否则可运行的 test 套件会被误判。
_MAKE_EMPTY_VAR_ASSIGNMENT = re.compile(
    r"^[ ]*(?:(?:export|override|private)[ \t]+)*"
    r"(?:::=|:=|\?=|\+=|!=|=)")

# 行首真正没有变量名的赋值（`=x` / `?=x` / `+=x` / `!=x` / `:=x` /
# `::=x`）。带修饰符的写法不同：`private +=x` 里 make 把 `private` 当
# 变量名（运算符前的最后一个词成为名字），所以不能把修饰符算进来。
_MAKE_TRULY_EMPTY_VAR_ASSIGNMENT = re.compile(
    r"^[ \t]*(?:::=|:=|\?=|\+=|!=|=)")

_MAKE_EMPTY_UNDEFINE = re.compile(
    r"^[ ]*(?:(?:export|override|private)[ \t]+)*undefine[ \t]*$")

_MAKE_VAR_REF = re.compile(
    r"(?<!\$)\$(?:\(([^\s:{}()=#;]+)(?::([^()\r\n]*))?\)"
    r"|\{([^\s:{}()=#;]+)(?::([^{}\r\n]*))?\}"
    r"|([A-Za-z0-9_]))")


def _make_strip_comment(line: str) -> str:
    """去掉引用之外的注释；变量引用内部的 # 是字面量。

    与 make 读取指令/规则头的语义一致：`$(join #,)`、`$#` 里的 # 不
    会提前截断；只有引用外的 # 才按反斜杠转义规则开始注释。
    """
    out = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "$" and i + 1 < n:
            nxt = line[i + 1]
            if nxt in "({":
                opener = nxt
                closer = ")" if opener == "(" else "}"
                depth = 1
                j = i + 2
                while j < n and depth:
                    cj = line[j]
                    if cj == opener:
                        depth += 1
                    elif cj == closer:
                        depth -= 1
                    j += 1
                out.append(line[i:j])
                i = j
            else:
                out.append(line[i:i + 2])
                i += 2
            continue
        if ch == "\\" and i + 1 < n:
            out.append(line[i:i + 2])
            i += 2
            continue
        if ch == "#":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _make_strip_value_comment(line: str) -> str:
    """按 make 变量赋值语义去掉注释并处理 # 前的反斜杠。

    连续 n 个反斜杠后跟 #：输出 n//2 个反斜杠；n 为奇数时 # 是字面量，
    为偶数时 # 开始注释。其他位置的反斜杠原样保留。

    变量引用内部的 # 不是注释起点（make 在引用未闭合时也一直把它当
    字面量）：`X = $(subst #,x,#)` 的值是两个 # 参与函数调用，而不是
    从第一个 # 截断。引用外的 # 才按上述反斜杠规则处理。
    """
    out = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "$" and i + 1 < n:
            nxt = line[i + 1]
            if nxt in "({":
                opener = nxt
                closer = ")" if opener == "(" else "}"
                depth = 1
                j = i + 2
                while j < n and depth:
                    cj = line[j]
                    if cj == "\\":
                        j += 2
                        continue
                    if cj == opener:
                        depth += 1
                    elif cj == closer:
                        depth -= 1
                    j += 1
                # 未闭合的引用一直延伸到行尾，其中的 # 仍是字面量。
                out.append(line[i:j])
                i = j
                continue
            # `$$` 是字面美元符，`$#` / `$:` 等是单字符变量引用；两者
            # 后面的字符都不构成注释起点。
            out.append(line[i:i + 2])
            i += 2
            continue
        if ch != "\\":
            if ch == "#":
                break
            out.append(ch)
            i += 1
            continue
        j = i
        while j < n and line[j] == "\\":
            j += 1
        if j < n and line[j] == "#":
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
    flat = re.sub(r"\\\r?\n", " ", args)
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
# 这些函数无法静态求值：参数里出现未定义变量时保留原样，不能把函数
# 名当成变量名展开为空（`$(shell echo test)` 可能真的产生 test 目标）。
_MAKE_UNSUPPORTED_FUNCTIONS = frozenset({
    "shell", "eval", "call", "foreach", "if", "or", "and", "intcmp",
    "let", "file", "value", "origin", "flavor", "info", "warning",
    "error", "guile",
})
_MAKE_FUNCTIONS = _MAKE_INCLUDE_FUNCTIONS | _MAKE_UNSUPPORTED_FUNCTIONS


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


def _make_patsubst_literal_sequence(pattern: str, repl: str,
                                    text: str) -> str:
    """无 % 但含空白的 patsubst 模式按 make 的实际行为做序列替换。

    GNU make 4.3 对 `$(patsubst test foo,X,test foo)` 会把连续词序列
    "test foo"（包括词间原有空白）整体替换成 X，而不是逐词比较；只有
    边界是空白/行首/行尾时才命中，`xtest foo` 与双空格 `test  foo`
    都不匹配。
    """
    literal = _make_pattern_unescape(pattern)
    replacement = _make_pattern_unescape(repl)
    if not literal:
        return text
    out: List[str] = []
    start = 0
    pos = 0
    while True:
        found = text.find(literal, pos)
        if found < 0:
            break
        end = found + len(literal)
        before_ok = found == 0 or text[found - 1].isspace()
        after_ok = end == len(text) or text[end].isspace()
        if before_ok and after_ok:
            out.append(text[start:found])
            out.append(replacement)
            start = end
            pos = end
        else:
            out.append(text[start:found + 1])
            start = found + 1
            pos = found + 1
    out.append(text[start:])
    return "".join(out)


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


_MAKE_FUNCTION_ARITY = {
    "wildcard": 1, "dir": 1, "notdir": 1, "addprefix": 2,
    "addsuffix": 2, "strip": 1, "basename": 1, "suffix": 1,
    "firstword": 1, "lastword": 1, "abspath": 1, "realpath": 1,
    "filter": 2, "filter-out": 2, "subst": 3, "patsubst": 3,
    "word": 2, "wordlist": 3, "words": 1, "sort": 1,
    "findstring": 2, "join": 2,
}

# `$(call name,...)` 的 name 若正好是内建函数名，make 会直接调用该
# 函数；参数个数不足时和普通函数调用一样是读取期 fatal 错误。
# 这里只记录最少参数个数（file 允许 1 或 2 个参数）。
_MAKE_CALL_MIN_ARGS = {
    **_MAKE_FUNCTION_ARITY,
    "file": 1, "foreach": 3, "if": 2, "or": 1, "and": 1,
    "value": 1, "origin": 1, "flavor": 1, "error": 1, "info": 1,
    "warning": 1, "shell": 1, "guile": 1, "intcmp": 2, "let": 2,
}


def _make_split_function_args(args: str, arity: int,
                              opener: str = "(") -> List[str]:
    """按 make 的函数参数个数在顶层逗号处切分（嵌套引用里的逗号不切）。

    先切分再展开每个参数，参数展开结果里的逗号才不会在重新拼接时被
    误当成新的参数分隔符：`$(findstring $(filter-out a,test,test foo),
    test)` 的第一个参数展开后含逗号，仍属于同一个 find 参数。
    """
    parts: List[str] = []
    start = 0
    closer = ")" if opener == "(" else "}"
    depth = 0
    i = 0
    while i < len(args) and len(parts) < arity - 1:
        ch = args[i]
        # GNU make 的函数参数分隔只看顶层逗号，反斜杠不转义逗号：
        # `$(if a\,b,x,y)` 仍有四个参数（条件为 `a\`）。
        # 嵌套只按与函数引用自身相同的括号配对：`$(subst (a,b),X,(a,b))`
        # 里的逗号不是分隔符，而 `$(subst {a,b},X,{a,b})` 里的逗号是。
        if ch == opener:
            depth += 1
        elif ch == closer:
            if depth:
                depth -= 1
        elif ch == "," and depth == 0:
            parts.append(args[start:i])
            start = i + 1
        i += 1
    parts.append(args[start:])
    return parts


def _make_check_refs_closed(text: str) -> None:
    """检查文本里的变量/函数引用是否成对，未闭合时按 make 读取错误处理。

    引用只按与起始括号相同的字符配对；`$(...${...}...)` 里的花括号
    不影响外层圆括号的结束位置。函数参数按顶层逗号切开后，跨括号
    类型留下的 `${a` 这类片段在 make 里同样是 unterminated reference。
    """
    i = 0
    n = len(text)
    while i + 1 < n:
        if text[i] != "$":
            i += 1
            continue
        nxt = text[i + 1]
        if nxt == "$":
            i += 2
            continue
        if nxt not in "({":
            i += 2
            continue
        opener = nxt
        closer = ")" if opener == "(" else "}"
        depth = 1
        k = i + 2
        while k < n:
            if text[k] == opener:
                depth += 1
            elif text[k] == closer:
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if depth:
            raise _MakeRequiredIncludeError(text[i:])
        i = k + 1


def _make_check_top_level_call_args(text: str) -> None:
    """校验顶层 `$(call ...)` 原文的参数片段是否闭合。

    其他静态函数展开可能先改写 call 参数里的内容（甚至把跨括号类型的
    逗号片段拼回去），所以必须在任何展开之前按原文切分并检查。只检查
    顶层 call：未生效条件分支里的 call 不会被 make 展开。
    """
    i = 0
    n = len(text)
    while i + 1 < n:
        if text[i] != "$":
            i += 1
            continue
        nxt = text[i + 1]
        if nxt == "$":
            i += 2
            continue
        if nxt not in "({":
            i += 2
            continue
        opener = nxt
        closer = ")" if opener == "(" else "}"
        depth = 1
        k = i + 2
        while k < n:
            if text[k] == opener:
                depth += 1
            elif text[k] == closer:
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if depth:
            return
        j = i + 2
        while j < k and (text[j].isalnum() or text[j] in "_-"):
            j += 1
        if (text[i + 2:j] == "call" and j < k
                and text[j] in " \t"):
            raw_args = text[j:k].lstrip(" \t")
            for part in _make_split_function_args(raw_args, 1000000, opener):
                _make_check_refs_closed(part)
                # call 会展开全部参数，参数里的嵌套 call 同样按原文切分；
                # `$(call f,$(call g,x,${a,b}))` 的 `${a` 片段也会报错。
                _make_check_top_level_call_args(part)
        i = k + 1


def _make_expand_include_function(
        name: str, args, repo: Path, *, expanded: bool = False) -> str:
    """展开 include 文件名里可静态求值的 make 函数（不含 shell/eval）。

    `expanded=False` 表示 args 还是未展开的原文，函数名后的第一个参数
    需要按 make 参数解析去掉起始空白；调用方若已经先展开参数，则先对
    原文做过这一步，必须传 expanded=True，否则展开结果自身的前导空白
    会被错误吃掉（`$(subst $(...) ,... )` 的模式可能就是空格）。
    """
    if isinstance(args, str):
        args = _make_split_function_args(args, _MAKE_FUNCTION_ARITY[name])
    parts = args
    if name == "wildcard":
        found = []
        repo_prefix = str(repo) + os.sep
        for token in re.findall(r"(?:\\.|[^\s])+", parts[0]):
            absolute = Path(_make_unescape_name(token)).is_absolute()
            pattern = _make_glob_pattern(token)
            if not absolute:
                pattern = os.path.join(glob.escape(str(repo)), pattern)
            try:
                matches = sorted(glob.glob(pattern))
            except (OSError, re.error):
                matches = []
            for match in matches:
                if not absolute and match.startswith(repo_prefix):
                    # 相对模式要保留用户写的 `./`、`..`、双斜杠等
                    # 路径前缀；make 的 wildcard 会原样返回它们。
                    found.append(match[len(repo_prefix):])
                else:
                    found.append(match)
        return " ".join(found)
    if name in ("addprefix", "addsuffix"):
        # make 对少于两个参数（缺少逗号）直接报错并停止解析：不能当成
        # 空展开继续找 test 目标，否则会把必然失败的 make test 探测成套件。
        if len(parts) < 2:
            raise _MakeRequiredIncludeError(name + ": missing argument")
        affix, names = parts
        # 非末位参数的起始空白由 make 的参数解析去掉；尾随空白属于
        # 参数本身（`$(addsuffix x ,a)` 的后缀是 "x "）。
        if not expanded:
            affix = affix.lstrip(" \t")
        words = names.split()
        if name == "addprefix":
            return " ".join(affix + word for word in words)
        return " ".join(word + affix for word in words)
    if name in ("filter", "filter-out"):
        if len(parts) < 2:
            raise _MakeRequiredIncludeError(
                f"{name}: missing argument")
        patterns, text = parts
        pats = patterns.split()
        keep = []
        for word in text.split():
            matched = any(_make_pattern_match(pat, word)[0]
                          for pat in pats)
            if matched == (name == "filter"):
                keep.append(word)
        return " ".join(keep)
    if name == "subst":
        if len(parts) < 3:
            raise _MakeRequiredIncludeError("subst: missing argument")
        old, new, text = parts
        # 只有紧跟函数名的第一个参数会被 make 去掉起始空白；逗号后的
        # 参数保留自己的起始空白（它可能就是要替换成的文本）。
        if not expanded:
            old = old.lstrip(" \t")
        if not old:
            # GNU make 对空 from 的 subst 把 new 追加到 text 末尾
            # （$(subst ,x,foo) -> foox），不是 Python 的逐字符插入。
            return text + new
        return text.replace(old, new)
    if name == "patsubst":
        if len(parts) < 3:
            raise _MakeRequiredIncludeError("patsubst: missing argument")
        pattern, repl, text = parts
        # 第一个参数前的空白属于函数语法；repl 的起始空白是有效内容。
        if not expanded:
            pattern = pattern.lstrip(" \t")
        wildcard, _run_start = _make_pattern_wildcard(pattern)
        if wildcard < 0 and any(ch.isspace() for ch in pattern):
            return _make_patsubst_literal_sequence(pattern, repl, text)
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
        if len(parts) < 2:
            raise _MakeRequiredIncludeError("word: missing argument")
        index = _make_function_index(parts[0], "word")
        words = _make_function_words(parts[1])
        return words[index - 1] if index <= len(words) else ""
    if name == "wordlist":
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
        return str(len(_make_function_words(parts[0])))
    if name == "sort":
        return " ".join(sorted(set(_make_function_words(parts[0]))))
    if name == "findstring":
        if len(parts) < 2:
            raise _MakeRequiredIncludeError("findstring: missing argument")
        needle = parts[0]
        if not expanded:
            needle = needle.lstrip(" \t")
        return needle if needle in parts[1] else ""
    if name == "strip":
        return " ".join(parts[0].split())
    if name == "join":
        if len(parts) < 2:
            raise _MakeRequiredIncludeError("join: missing argument")
        left, right = parts
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
    words = parts[0].split()
    if name == "firstword":
        return words[0] if words else ""
    if name == "lastword":
        return words[-1] if words else ""
    if name in ("abspath", "realpath"):
        result = []
        for word in words:
            path = word if os.path.isabs(word) else os.path.join(str(repo),
                                                                word)
            if name == "realpath":
                # 先按原样（含尾随 /）判断存在性：文件 `a` 存在，但
                # `a/` 在 make 里不是有效路径，realpath 返回空。若先
                # abspath 规范化掉尾随斜杠，会错误地返回文件路径。
                if not os.path.exists(path):
                    continue
                path = os.path.realpath(path)
                if not os.path.exists(path):
                    continue
            else:
                path = os.path.abspath(path)
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
        depth = 1
        k = i + 2
        while k < len(text):
            ch = text[k]
            # 引用只按与起始括号相同的字符配对；另一种括号嵌套
            #（`$(...${...}...)`）里的右括号仍会结束外层引用。
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if depth:
            # 未闭合的变量/函数引用会让 make 直接报错并停止解析。
            raise _MakeRequiredIncludeError(text[i:])
        j = i + 2
        while j < len(text) and (text[j].isalnum() or text[j] in "_-"):
            j += 1
        name = text[i + 2:j]
        if (name in _MAKE_INCLUDE_FUNCTIONS and j < len(text)
                and text[j] in " \t"):
            return i, k + 1, name, text[j:k].lstrip(" \t")
        if ((name in _MAKE_CONDITION_FUNCTIONS or name == "foreach")
                and j < len(text) and text[j] in " \t"):
            # if/or/and 短路、foreach 的 body 只对非空列表求值：里面的
            # 静态函数不能在这里提前展开，否则未选中的分支/空列表 body
            # 里的参数错误会被误当成读取期错误。交给条件/foreach 展开器
            # 选中后再处理。只有函数名后紧跟空白才是调用；`$(foreach,...)`
            # 没有空白，是名为 `foreach,...` 的普通变量引用，继续向下
            # 扫描才能展开其中嵌套的 if/or/and。
            i = k + 1
            continue
        i += 1
    return None


def _make_has_unresolved_ref(text: str) -> bool:
    """文本里是否还有无法静态求值的 `$` 引用（`$$` 是字面美元符，不算）。"""
    return "$" in text.replace("$$", "")


def _make_refs_only_without_literals(text: str) -> bool:
    """文本是否只由无法静态求值的引用/空白组成、没有字面字符。

    变量名里的 `$(shell ...)` 输出未知：若名字还含字面字符（`A$(shell
    ...)`），无论 shell 输出什么都非空；若只有引用（`$(shell ...)` /
    `$(foreach,$(shell ...))`），输出为空时 make 会报 empty variable
    name，静态探测无法确认套件可运行，必须按「没有套件」处理。
    """
    i = 0
    n = len(text)
    has_literal = False
    while i < n:
        if text[i] == "$" and i + 1 < n:
            if text[i + 1] == "$":
                # `$$` 是字面美元符。
                has_literal = True
                i += 2
                continue
            if text[i + 1] in "({":
                opener = text[i + 1]
                closer = ")" if opener == "(" else "}"
                depth = 1
                j = i + 2
                while j < n and depth:
                    if text[j] == opener:
                        depth += 1
                    elif text[j] == closer:
                        depth -= 1
                    j += 1
                if depth:
                    return False
                i = j
                continue
            # `$x` 这类单字符引用同样不是字面字符。
            i += 2
            continue
        if not text[i].isspace():
            has_literal = True
        i += 1
    return not has_literal


def _make_unknown_name_may_be_empty(name: str) -> bool:
    """名字里只剩无法静态求值的引用时，结果可能为空（见上）。"""
    return _make_has_unresolved_ref(name) and _make_refs_only_without_literals(
        name)


def _make_expand_include_functions(
        text: str, repo: Path,
        variables: Optional[Dict[str, Optional[str]]] = None,
        simple: Optional[Dict[str, bool]] = None,
        overrides: Optional[set] = None) -> str:
    """展开 include 文件名里可静态求值的函数（支持嵌套调用）。

    传入变量表时参数按 make 语义完整展开（含变量/条件/嵌套函数）：
    参数边界必须在原文上确定，否则先展开变量、再按「函数名后的空白」
    丢首空白会把变量值自身的前导空白吃掉（`$(subst $x ,...)` 的 `$x`
    展开为空后，那个空格属于 old 参数，不是语法空白）。
    """
    pos = 0
    while True:
        call = _make_find_include_function(text, pos)
        if call is None:
            return text
        start, end, name, args = call
        opener = text[start + 1]
        # 按函数参数个数先切分、再分别展开：展开结果里自带的逗号属于参数
        # 内容，不能再当成参数分隔符（否则 findstring 的 find 参数会被截断）。
        raw_parts = _make_split_function_args(
            args, _MAKE_FUNCTION_ARITY[name], opener)
        # 参数个数只看顶层逗号，与参数能否静态求值无关；即使后面是
        # `$(shell ...)`，`$(addprefix $(shell ))` 仍会报 insufficient
        # number of arguments 并停止读取。
        if len(raw_parts) < _MAKE_FUNCTION_ARITY[name]:
            raise _MakeRequiredIncludeError(name + ": missing argument")
        # make 只去掉函数名后第一个参数原文的起始空白；必须在展开前
        # 处理，展开结果里的前导空格属于值本身。
        raw_parts[0] = raw_parts[0].lstrip(" \t")
        evaluated: List[Optional[str]] = []
        unresolved = False
        for part in raw_parts:
            if variables is not None:
                value = _make_expand_condition_arg(
                    part, variables, simple or {}, repo, 0, overrides)
            else:
                value = None
            if value is None:
                value = _make_expand_include_functions(
                    _make_expand_automatic_refs(part), repo)
            if _make_has_unresolved_ref(value):
                # 参数里还有未展开的函数/变量（如 shell/eval），不能静态求值。
                unresolved = True
                evaluated.append(None)
                continue
            # `$$` 在参数展开后是字面 `$`；用非引用哨兵占位，避免后续
            # 静态函数再次把它当成单字符变量引用。`$(subst $$,1,x)`
            # 的参数个数/替换边界仍按 make 语义判断。
            evaluated.append(value.replace("$$", "\x03"))
        if unresolved:
            # 后面的参数无法静态求值时整个函数不能展开，但 word/wordlist
            # 的下标参数已展开时，非法下标仍会让 make 在读取期报错
            # （`$(wordlist x,x,$(shell ...)) test:` 不会执行 test）。
            # 参数按下标独立检查：前一个含 shell 不影响后一个判错。
            if name == "word":
                if evaluated and evaluated[0] is not None:
                    _make_function_index(evaluated[0], "word")
            elif name == "wordlist":
                if evaluated and evaluated[0] is not None:
                    _make_function_index(evaluated[0], "wordlist")
                if len(evaluated) > 1 and evaluated[1] is not None:
                    _make_function_index(
                        evaluated[1], "wordlist", allow_zero=True)
            pos = end
            continue
        replacement = _make_expand_include_function(
            name, evaluated, repo, expanded=True)
        text = text[:start] + replacement + text[end:]
        pos = start + len(replacement)


def _make_find_function_call(text: str, pos: int, name: str,
                             *, skip_compound: bool = False):
    """从 pos 起找下一个 `$(name ...)` / `${name ...}` 调用。

    skip_compound 会跳过整个条件/foreach/call 引用，交给各自的展开器
    按原文确定参数边界后再处理其中的目标函数。
    """
    i = pos
    while i + 1 < len(text):
        if text[i] == "$" and text[i + 1] == "$":
            i += 2
            continue
        if text[i] != "$" or text[i + 1] not in "({":
            i += 1
            continue
        opener = text[i + 1]
        closer = ")" if opener == "(" else "}"
        depth = 1
        k = i + 2
        while k < len(text):
            ch = text[k]
            # 引用只按与起始括号相同的字符配对；另一种括号嵌套
            #（`$(...${...}...)`）里的右括号仍会结束外层引用。
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if depth:
            raise _MakeRequiredIncludeError(text[i:])
        j = i + 2
        while j < len(text) and (text[j].isalnum() or text[j] in "_-"):
            j += 1
        if (skip_compound
                and (text[i + 2:j] in _MAKE_CONDITION_FUNCTIONS
                     or text[i + 2:j] in ("foreach", "call"))):
            i = k + 1
            continue
        after = i + 2 + len(name)
        if (text[i + 2:after] == name and after < len(text)
                and text[after] in " \t"):
            return i, k + 1, text[after:k].lstrip(" \t")
        i += 1
    return None


_MAKE_METADATA_FUNCTIONS = frozenset({"origin", "flavor"})


def _make_expand_metadata_functions(
        text: str, variables: Dict[str, Optional[str]],
        simple: Dict[str, bool],
        overrides: Optional[set] = None) -> str:
    """展开可静态求值的 `$(origin var)` / `$(flavor var)`。

    origin 的返回值按读取期能确定的信息计算：变量在 makefile 里赋值是
    `file`（带 override 是 `override`），继承自环境是 `environment`，
    其余是 `undefined`；flavor 对应 `simple` / `recursive` / `undefined`。
    常见写法 `ifeq ($(origin X),undefined)` 不展开会被当成字面文本，
    条件恒不成立，从而漏掉或凭空多出 test 目标。
    """
    pos = 0
    while True:
        best = None
        for name in _MAKE_METADATA_FUNCTIONS:
            call = _make_find_function_call(text, pos, name)
            if call is None:
                continue
            if best is None or call[0] < best[0]:
                best = call
        if best is None:
            return text
        start, end, args = best
        raw_args = _make_split_function_args(args, 1, text[start + 1])
        argument = raw_args[0]
        # 参数本身可以嵌套 origin/flavor：`$(flavor $(flavor ;))` 的
        # 内层先展开成 undefined，外层再查名为 undefined 的变量。嵌套
        # 参数必须先递归展开，否则整个调用被当成未解析引用跳过，eval
        # 注入的 `undefined` 行就漏掉 missing separator。
        argument = _make_expand_metadata_functions(
            argument, variables, simple, overrides)
        if _make_has_unresolved_ref(argument):
            # 参数里还有无法展开的引用（shell/call 等），不能猜变量名。
            pos = end
            continue
        # `$$` 是字面 `$`：`$(origin $$)` 查的是名为 `$` 的变量。
        name = argument.replace("$$", "$")
        if name in variables:
            origin = "override" if overrides and name in overrides else "file"
            flavor = "simple" if simple.get(name) else "recursive"
        elif name in os.environ:
            origin = "environment"
            flavor = "recursive"
        else:
            origin = "undefined"
            flavor = "undefined"
        replacement = origin if text[start + 2:start + 2 + len(
            "origin")] == "origin" else flavor
        text = text[:start] + replacement + text[end:]
        pos = start + len(replacement)


_MAKE_SIDE_EFFECT_FUNCTIONS = ("info", "warning")


def _make_expand_eval_functions(
        text: str,
        variables: Dict[str, Optional[str]],
        simple: Dict[str, bool],
        repo: Optional[Path] = None,
        overrides: Optional[set] = None) -> str:
    """展开赋值名/define 名里的 `$(eval ...)`，结果为空串。

    eval 的参数会先展开并作为 Makefile 行立即解析，再返回空串。名称里
    出现 eval（`$(eval X=1) = 2`）时，make 仍按空变量名报错；只需删除
    eval 调用并应用其中的简单赋值，避免把原文当成非空名称漏检。
    """
    pos = 0
    while True:
        call = _make_find_function_call(text, pos, "eval")
        if call is None:
            return text
        start, end, args = call
        expanded_arg = _make_expand_condition_text(
            args, variables, simple, repo, overrides)
        for eval_line in expanded_arg.splitlines():
            if eval_line.startswith("\t"):
                continue
            # eval 参数先展开一次，再按 Makefile 行解析；解析时 `$$`
            # 已经是字面 `$`，会按生成的文本继续展开。`$(eval $$)` 生成
            # 单独一行 `$`，`$(eval $$(X))foo = x` 在 X=test 时生成
            # `test`，make 都报 missing separator。用第二次展开后的文本
            # 做校验，赋值仍按第一次展开的原文应用，避免提前展开延迟
            # 赋值右侧。
            check_line = eval_line
            for _ in range(20):
                before_line = check_line
                # 嵌套 eval 会在外层参数展开时先执行；`$(eval $(eval x))`
                # 的内层 `x` 已经让 make 读取失败，不能随外层一起删掉。
                check_line = _make_expand_eval_functions(
                    check_line, variables, simple, repo, overrides)
                if "$$" in check_line:
                    check_line = check_line.replace("$$", "$")
                check_line = _make_resolve_single_char_refs(
                    check_line, variables, simple)
                second = _make_expand_condition_text(
                    check_line, variables, simple, repo, overrides)
                if second is not None:
                    check_line = second
                if check_line == before_line:
                    break
            # eval 参数先展开、再按 Makefile 行解析；`$(eval foo)` 的
            # `foo` 没有规则分隔符，会让 make 在读取阶段直接失败。原先
            # 只扫描赋值，非赋值行被静默丢弃，后面的 test 目标因此被
            # 误判成可运行套件。
            if _make_has_missing_separator_line(check_line):
                raise _MakeRequiredIncludeError("eval: missing separator")
            if _make_has_invalid_extra_rule_colon(check_line):
                # eval 生成的行同样要按 Makefile 规则校验：`$(eval foo:
                # a:b)` 在读取期报 target pattern contains no '%'，
                # `$(eval foo: =1)` 报 empty variable name。只检查
                # missing separator 会让嵌在依赖/赋值右侧的 eval 漏掉
                # 这些错误，后面看似可运行的 test 目标被误判成套件。
                raise _MakeRequiredIncludeError(
                    "eval: invalid rule header")
            _make_scan_assignment(
                eval_line, variables, simple, overrides, repo)
        text = text[:start] + text[end:]
        pos = start


def _make_expand_side_effect_functions(
        text: str,
        variables: Optional[Dict[str, Optional[str]]] = None,
        simple: Optional[Dict[str, bool]] = None,
        repo: Optional[Path] = None,
        overrides: Optional[set] = None) -> str:
    """把只产生输出、结果为空串的 `$(info ...)` / `$(warning ...)` 展开掉。

    调用方必须已展开条件函数并检查 error：`$(info $(if a,$(error x),))`
    里的 error 仍然会触发读取失败，不能先把它连同 info 一起删掉。
    参数本身也会在读取期展开，其中的 eval 同样会先解析参数行；
    `$(warning $(eval x))` 不能把未生效的 eval 连同 warning 一起删掉。
    """
    pos = 0
    while True:
        best = None
        for name in _MAKE_SIDE_EFFECT_FUNCTIONS:
            call = _make_find_function_call(text, pos, name)
            if call is None:
                continue
            if best is None or call[0] < best[0]:
                best = call
        if best is None:
            return text
        start, end, args = best
        if variables is not None:
            # 只校验参数展开的读取期错误；warning/info 的输出不参与
            # Makefile 语义，展开结果本身仍然丢弃。
            _make_expand_condition_text(
                args, variables, simple or {}, repo, overrides)
        text = text[:start] + text[end:]
        pos = start


def _make_expand_call_functions(
        text: str, variables: Dict[str, Optional[str]],
        simple: Dict[str, bool], repo: Optional[Path] = None,
        overrides: Optional[set] = None, depth: int = 0) -> str:
    """静态展开 `$(call var,参数...)`。

    make 先展开变量名与每个参数，再把参数按序号赋给 `$(1)`…`$(0)` 保持
    变量名，最后在局部变量表里展开变量值。`$(call test,test)` 这类写法
    常用于动态拼目标名，不展开会把函数原文留成目标名而漏探测 test。
    """
    if depth > 10:
        return text
    pos = 0
    while True:
        call = _make_find_function_call(text, pos, "call")
        if call is None:
            return text
        start, end, args = call
        parts = _make_split_function_args(args, 1000000, text[start + 1])
        # call 会先展开全部参数；任一参数里的未闭合引用都是读取期错误，
        # 即使 callable 的值根本不使用这个参数。
        for part in parts:
            _make_check_refs_closed(part)
        raw_name = parts[0].lstrip(" \t")
        name = _make_expand_call_arg(
            raw_name, variables, simple, repo, overrides, depth + 1)
        if "$" in name:
            pos = end
            continue
        # 内建函数名不是变量，call 会直接调用它；参数不足时 make 报
        # insufficient number of arguments，即使存在同名用户变量也一样。
        min_args = _MAKE_CALL_MIN_ARGS.get(name)
        if min_args is not None and len(parts) - 1 < min_args:
            raise _MakeRequiredIncludeError(name + ": missing argument")
        if name in variables:
            value = variables[name]
            if value is None:
                # shell 赋值的值未知，不能猜。
                pos = end
                continue
        elif name in os.environ:
            value = os.environ[name]
        else:
            # 未定义的 callable 展开为空。
            text = text[:start] + text[end:]
            pos = start
            continue
        params = []
        unresolved = False
        for part in parts[1:]:
            value_part = _make_expand_call_arg(
                part, variables, simple, repo, overrides, depth + 1)
            if "$" in value_part:
                unresolved = True
                break
            params.append(value_part)
        if unresolved and "$" in value:
            pos = end
            continue
        local_vars = dict(variables)
        local_simple = dict(simple)
        local_vars["0"] = name
        local_simple["0"] = True
        for index, param in enumerate(params, 1):
            local_vars[str(index)] = param
            local_simple[str(index)] = True
        result = _make_expand_call_arg(
            value, local_vars, local_simple, repo, overrides, depth + 1)
        text = text[:start] + result + text[end:]
        pos = start + len(result)


def _make_expand_call_arg(
        text: str, variables: Dict[str, Optional[str]],
        simple: Dict[str, bool], repo: Optional[Path] = None,
        overrides: Optional[set] = None, depth: int = 0) -> str:
    """把静态可求值的函数展开到不动点，供 call 的参数/函数体复用。"""
    for _ in range(20):
        before = text
        text = _make_expand_automatic_refs(text)
        text = _make_expand_value(text, variables, simple)
        if repo is not None:
            text = _make_expand_include_functions(
                text, repo, variables, simple, overrides)
        text = _make_expand_condition_functions(
            text, variables, simple, repo, overrides=overrides)
        text = _make_expand_foreach(text, variables, simple, repo)
        text = _make_expand_metadata_functions(
            text, variables, simple, overrides)
        text = _make_expand_error_functions(text)
        text = _make_expand_side_effect_functions(
            text, variables, simple, repo, overrides)
        text = _make_expand_call_functions(
            text, variables, simple, repo, overrides, depth)
        text = _make_expand_refs(text, variables, simple, repo=repo)
        if repo is not None:
            text = _make_expand_include_functions(text, repo)
        text = _make_expand_computed_refs(text, variables, simple)
        text = _make_resolve_single_char_refs(text, variables, simple)
        if text == before:
            break
    return text


def _make_expand_error_functions(text: str) -> str:
    """遇到会立即展开的 `$(error ...)` 时按 make 读取失败处理。

    调用方必须先展开条件函数：未生效的 if/or/and 分支会被删掉，剩下的
    error 调用在读取阶段必然执行并终止 make；忽略它会把后面存在的 test
    目标误判成可运行套件。
    """
    pos = 0
    while True:
        call = _make_find_function_call(text, pos, "error")
        if call is None:
            return text
        raise _MakeRequiredIncludeError("error")


def _make_expand_value(text: str,
                       variables: Dict[str, Optional[str]],
                       simple: Dict[str, bool],
                       depth: int = 0) -> str:
    """静态展开 `$(value var)`：返回变量未展开的原始值。

    只处理值里不含 `$` 的简单情况；原始值里的引用在 make 里不会再次
    展开，直接放回文本会被后续展开误当成目标/变量，保留原样更安全。
    """
    if depth > 20:
        return text
    pos = 0
    while True:
        call = _make_find_function_call(
            text, pos, "value", skip_compound=True)
        if call is None:
            return text
        start, end, args = call
        parts = _make_split_function_args(args, 1, text[start + 1])
        raw_name = parts[0].lstrip(" \t")
        name = _make_expand_foreach_part(
            raw_name, variables, simple, None, depth + 1)
        if "$" in name:
            replacement = None
        elif name not in variables:
            # make 里未定义变量的 value 是空串。
            replacement = ""
        elif variables[name] is None:
            # shell 赋值的值未知，不能猜。
            replacement = None
        else:
            replacement = variables[name]
            if "$" in replacement:
                replacement = None
        if replacement is None:
            pos = end
            continue
        text = text[:start] + replacement + text[end:]
        pos = start + len(replacement)


def _make_expand_foreach_part(text: str,
                              variables: Dict[str, Optional[str]],
                              simple: Dict[str, bool],
                              repo: Optional[Path],
                              depth: int,
                              active: Optional[set] = None) -> str:
    """展开 foreach 参数/循环体里的静态变量与函数。"""
    for _ in range(20):
        before = text
        text = _make_expand_automatic_refs(text)
        # 与条件文本同理：info/warning 删除前先检查参数里的静态函数。
        if repo is not None:
            text = _make_expand_include_functions(text, repo)
        text = _make_expand_value(text, variables, simple, depth + 1)
        text = _make_expand_condition_functions(text, variables, simple, repo)
        text = _make_expand_foreach(
            text, variables, simple, repo, depth + 1, active)
        text = _make_expand_refs(
            text, variables, simple, active=active, repo=repo)
        text = _make_expand_error_functions(text)
        text = _make_expand_side_effect_functions(
            text, variables, simple, repo)
        text = _make_expand_call_functions(
            text, variables, simple, repo)
        text = _make_expand_refs(
            text, variables, simple, active=active, repo=repo)
        if repo is not None:
            text = _make_expand_include_functions(text, repo)
            text = _make_expand_refs(
                text, variables, simple, active=active, repo=repo)
        text = _make_expand_computed_refs(text, variables, simple)
        text = _make_resolve_single_char_refs(text, variables, simple)
        if text == before:
            break
    return text


def _make_expand_foreach(text: str,
                         variables: Dict[str, Optional[str]],
                         simple: Dict[str, bool],
                         repo: Optional[Path] = None,
                         depth: int = 0,
                         active: Optional[set] = None) -> str:
    """静态展开 `$(foreach var,list,body)`（含嵌套）。

    foreach 在目标名里很常见（`$(foreach x,test foo,$(x))::` 会同时
    定义 test/foo）。不展开会把函数原文当成一个目标名，既可能漏掉
    test，也可能漏掉与已有 test 规则的 :/:: 冲突。
    """
    if depth > 20:
        return text
    pos = 0
    while True:
        call = _make_find_function_call(text, pos, "foreach")
        if call is None:
            return text
        start, end, args = call
        parts = _make_split_function_args(args, 3, text[start + 1])
        if len(parts) < 3:
            raise _MakeRequiredIncludeError("foreach: missing argument")
        name = _make_expand_foreach_part(
            parts[0], variables, simple, repo, depth + 1, active).strip()
        words = _make_expand_foreach_part(
            parts[1], variables, simple, repo, depth + 1, active).split()
        body = parts[2]
        results = []
        for word in words:
            local_vars = dict(variables)
            local_simple = dict(simple)
            local_vars[name] = word
            local_simple[name] = True
            results.append(_make_expand_foreach_part(
                body, local_vars, local_simple, repo, depth + 1, active))
        replacement = " ".join(results)
        text = text[:start] + replacement + text[end:]
        pos = start + len(replacement)


def _make_standalone_eval_args(body: str) -> Optional[List[str]]:
    """整行只有 `$(eval ...)` 调用时返回各参数原文。

    eval 在读取时展开并立即解析参数内容，可定义目标/变量；但 eval 行
    本身不会成为后续 tab recipe 的当前目标。只处理整行调用，嵌在目标
    行或 recipe 里的 eval 情况更复杂，保持原样交给保守路径。
    """
    calls: List[str] = []
    i = 0
    n = len(body)
    while i < n:
        if body[i] in " \t":
            i += 1
            continue
        if (body[i] != "$" or i + 1 >= n
                or body[i + 1] not in "({"):
            return None
        opener = body[i + 1]
        closer = ")" if opener == "(" else "}"
        depth = 1
        k = i + 2
        while k < n:
            ch = body[k]
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if depth:
            return None
        content = body[i + 2:k]
        name_end = 0
        while (name_end < len(content)
               and (content[name_end].isalnum()
                    or content[name_end] in "_-")):
            name_end += 1
        if content[:name_end] != "eval":
            return None
        if name_end < len(content) and content[name_end] not in " \t":
            return None
        calls.append(content[name_end:].lstrip(" \t"))
        i = k + 1
    return calls or None


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
                      active: Optional[set] = None,
                      repo: Optional[Path] = None) -> str:
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
                # 与目标展开主流程一致：条件先于 foreach，且静态函数要
                # 拿到 repo 才能求值（`$(foreach v,$(suffix x),...)`）。
                # 递归变量值里的 foreach 若在条件未生效分支中，make 不会
                # 展开它；提前按外层变量展开会误判分支或触发参数错误。
                value = _make_expand_condition_functions(
                    value, variables, simple, repo, depth + 1)
                value = _make_expand_foreach(
                    value, variables, simple, repo, depth + 1, active)
                value = _make_expand_refs(value, variables, simple,
                                          depth + 1, active, repo)
            finally:
                active.discard(name)
        if spec is not None:
            value = _make_substitute_ref(value, spec)
        return value

    return _MAKE_VAR_REF.sub(repl, text)


def _make_resolve_single_char_refs(
        text: str, variables: Dict[str, Optional[str]],
        simple: Dict[str, bool]) -> str:
    """展开目标行里剩下的单字符变量引用（`$x` / `$:` / `$ `）。

    GNU make 的变量引用可以只由一个字符组成，且该字符可以是冒号、井号、
    分号或空白：`test $:` 里的 `$:` 会吃掉规则分隔符（missing separator），
    而 `test$ test:` 里的 `$ ` 会吃掉词间空白，把两个词粘成 `testtest`。
    这些语法在 `_MAKE_VAR_REF` 的常规展开之后仍然存在（未定义的标点变量
    不会被它匹配），若不处理，目标探测会把被吃掉的 `test` 当成独立目标，
    或者反过来把 `test test$::` 这类可运行套件误判成没有 test。

    `$$` 是字面 `$`，用非分隔哨兵保留其占位，避免它再次被当引用；已知的
    标点变量名（如 `$!`）按赋值展开，未定义的单字符引用展开为空，与
    make 一致。`$(...)` / `${...}` 保持原样，交给已有的静态函数/未知
    变量逻辑处理。
    """
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != "$" or i + 1 >= n:
            out.append(ch)
            i += 1
            continue
        nxt = text[i + 1]
        if nxt in "({":
            # 未知引用的内容仍可能展开出 test，不能动；整段原样保留。
            closer = ")" if nxt == "(" else "}"
            depth = 1
            j = i + 2
            while j < n and depth:
                cj = text[j]
                if cj == "$" and j + 1 < n and text[j + 1] in "({":
                    depth += 1
                    j += 2
                    continue
                if cj == closer:
                    depth -= 1
                j += 1
            out.append(text[i:j])
            i = j
            continue
        if nxt == "$":
            out.append("\x03")
            i += 2
            continue
        if nxt in variables:
            value = variables[nxt]
            if value is None:
                out.append(text[i:i + 2])
            else:
                try:
                    value = _make_expand_refs(value, variables, simple)
                except _MakeRequiredIncludeError:
                    value = text[i:i + 2]
                out.append(value)
        # 反斜杠原本转义的是 `$`，引用消失后它不能转而把后面的规则
        # 分隔符（`test \$::` 的第二个冒号）也转义掉；插入哨兵隔开。
        # 但 `$\` 引用本身已消耗一个反斜杠，前一个反斜杠要与后面的
        # 反斜杠配对（`*\$\\:` 的两个反斜杠让冒号仍是分隔符），
        # 插入哨兵会拆散配对、把冒号错误转义掉。
        if (out and out[-1].endswith("\\") and i + 2 < n
                and nxt != "\\"):
            out.append("\x03")
        # 未定义的单字符变量展开为空。
        i += 2
    return "".join(out)


_MAKE_AUTOMATIC_REF_CHARS = frozenset("@%<?^+*|")
"""目标/赋值读取期的自动变量：尚未绑定到具体目标，展开为空。"""


def _make_expand_automatic_refs(text: str) -> str:
    """把自动变量引用展开为空（`$@` / `$<` / `$^` 等）。

    `_MAKE_VAR_REF` 只认字母数字下划线组成的单字符变量名，`$@` 这类
    引用在函数参数、条件表达式内部不会被常规展开；不处理会让
    `$(addsuffix $@,test)` 漏探测 test，或让 `$(word $@,a b)` 跳过
    make 的读取期报错。recipe 行不会被本函数处理（recipe 里的自动变量
    在执行期才有值）。
    """
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "$" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "$":
                out.append("$$")
                i += 2
                continue
            if nxt in _MAKE_AUTOMATIC_REF_CHARS:
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _make_expand_computed_refs(text: str,
                                variables: Dict[str, Optional[str]],
                                simple: Dict[str, bool],
                                depth: int = 0) -> str:
    """展开变量名本身由变量展开得到的引用（`$($(A))`）。

    make 先展开 `$(...)` 里的内容，再把结果当变量名查表；未定义时展开为
    空。`_MAKE_VAR_REF` 只认不含空白/括号的简单变量名，无法匹配
    `$($(A))`，若不补这一步，`A = B; B = test` 这种间接目标会漏探测，
    而 `$($(A) test foo)`（变量名为 "test foo ..."，未定义）又会被当成
    字面目标误探测。
    """
    if depth > 20 or "$" not in text:
        return text
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("$$", i):
            out.append("$$")
            i += 2
            continue
        if text[i] != "$" or i + 1 >= n or text[i + 1] not in "({":
            out.append(text[i])
            i += 1
            continue
        opener = text[i + 1]
        closer = ")" if opener == "(" else "}"
        depth = 1
        k = i + 2
        while k < n:
            ch = text[k]
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if depth:
            # 未闭合的引用留给上层按 make 解析错误处理。
            out.append(text[i:])
            break
        content = text[i + 2:k]
        inner = _make_expand_automatic_refs(content)
        inner = _make_expand_computed_refs(inner, variables, simple,
                                           depth + 1)
        try:
            inner = _make_expand_refs(inner, variables, simple)
        except _MakeRequiredIncludeError:
            out.append(text[i:k + 1])
            i = k + 1
            continue
        if "$" in inner:
            # 还有 shell/未知变量，无法确定变量名；保留原样。
            out.append(text[i:k + 1])
            i = k + 1
            continue
        function = re.match(r"([A-Za-z0-9_-]+)[ \t]", inner.lstrip(" \t"))
        if function is not None and function.group(1) in _MAKE_FUNCTIONS:
            out.append(text[i:k + 1])
            i = k + 1
            continue
        if ":" in inner:
            # 替换引用等语法不能当成普通变量名；留给已有逻辑处理。
            out.append(text[i:k + 1])
            i = k + 1
            continue
        if inner not in variables:
            # 未定义的变量名按 make 语义展开为空。
            i = k + 1
            continue
        value = variables[inner]
        if value is None:
            # shell 赋值等未知值：保留原样，无法静态求值。
            out.append(text[i:k + 1])
        else:
            if not simple.get(inner):
                try:
                    value = _make_expand_refs(value, variables, simple)
                except _MakeRequiredIncludeError:
                    out.append(text[i:k + 1])
                    i = k + 1
                    continue
            out.append(_make_expand_computed_refs(
                value, variables, simple, depth + 1))
        i = k + 1
    return "".join(out)


def _make_expand_immediate_value(
        value: str, variables: Dict[str, Optional[str]],
        simple: Dict[str, bool],
        repo: Optional[Path] = None,
        overrides: Optional[set] = None) -> str:
    """按 make 读取期语义展开 `:=`/`+=`/`!=` 的右值。

    这些赋值会在读取时立即展开右值，静态函数的参数错误（如
    `$(wordlist foo,,x)`）会让 make 直接停止解析；只展开变量引用会把
    错误函数留到探测末尾，导致后面存在的 test 目标被误判成可运行套件。
    """
    for _ in range(20):
        before = value
        value = _make_expand_automatic_refs(value)
        value = _make_expand_value(value, variables, simple)
        # 与目标行同理：参数边界按原文确定，静态函数要赶在变量/条件
        # 展开之前处理，否则变量展开为空后留下的参数值空白会被当成
        # 函数名后的语法空白丢掉。
        if repo is not None:
            value = _make_expand_include_functions(
                value, repo, variables, simple, overrides)
        value = _make_expand_condition_functions(
            value, variables, simple, repo)
        value = _make_expand_foreach(value, variables, simple, repo)
        value = _make_expand_metadata_functions(value, variables, simple)
        value = _make_expand_error_functions(value)
        value = _make_expand_side_effect_functions(
            value, variables, simple, repo, overrides)
        value = _make_expand_call_functions(
            value, variables, simple, repo, overrides)
        # eval 在读取期立即执行；`X := $(eval x)` 会先解析参数行 `x`
        # 并报 missing separator，不能把它留成普通变量值。
        value = _make_expand_eval_functions(
            value, variables, simple, repo, overrides)
        value = _make_expand_refs(value, variables, simple, repo=repo)
        if repo is not None:
            value = _make_expand_include_functions(
                value, repo, variables, simple, overrides)
        value = _make_expand_computed_refs(value, variables, simple)
        value = _make_resolve_single_char_refs(value, variables, simple)
        value = _make_expand_refs(value, variables, simple, repo=repo)
        if value == before:
            break
    return value


def _make_apply_assignment(match: re.Match,
                           variables: Dict[str, Optional[str]],
                           simple: Dict[str, bool],
                           overrides: Optional[set] = None,
                           repo: Optional[Path] = None) -> None:
    name, op, raw = match.groups()
    # `override` 标记的变量不会再被后续普通赋值/undefine 覆盖；只有另一条
    # 带 override 的赋值才能改它。make 在读取阶段就按这个优先级决定最终
    # 值，忽略它会让 `override A = test` 后的 `A = $(B)` 把 test 目标
    # 展开成空，漏掉实际可运行的套件。
    prefix = match.group(0)[:match.start(1)]
    _make_apply_assignment_parts(name, op, raw, prefix,
                                 variables, simple, overrides, repo)


def _make_apply_assignment_parts(
        name: str, op: str, raw: str, prefix: str,
        variables: Dict[str, Optional[str]],
        simple: Dict[str, bool],
        overrides: Optional[set] = None,
        repo: Optional[Path] = None) -> None:
    """按已展开的变量名/运算符更新变量表（动态变量名路径复用）。"""
    if overrides is None:
        overrides = set()
    is_override = "override" in prefix.split()
    if name in overrides and not is_override:
        return
    # make 的 `?=` 只在变量尚未定义时生效；override ?= 命中已定义变量时
    # 也不会把该变量升级成 override（后续普通赋值仍可覆盖）。
    if op == "?=" and name in variables:
        return
    if is_override:
        overrides.add(name)
    # make 保留注释前的尾随空白（`T = test # c` 的值是 `test `），
    # 它会在 `$(T)-unit:` 里把目标拆成 test 与 -unit；rstrip 会漏掉 test。
    raw = _make_strip_value_comment(raw)
    if op == "!=":
        # `!=` 先展开右值再交给 shell；静态函数的参数错误仍在读取期
        # 直接终止 make，不能因为不保存 shell 结果就跳过展开。
        _make_expand_immediate_value(raw, variables, simple, repo,
                                     overrides)
        variables[name] = None
        simple[name] = False
    elif op == "?=":
        variables[name] = raw
        simple[name] = False
    elif op == "+=":
        if name not in variables:
            variables[name] = raw
            simple[name] = False
        elif variables[name] is not None:
            value = raw
            if simple.get(name):
                value = _make_expand_immediate_value(
                    value, variables, simple, repo, overrides)
            # make 只在旧值非空且追加值非空时插入一个分隔空格；两侧的
            # 尾随空白都属于变量值本身（`X += bar ` 的值是 `foo bar `），
            # strip() 会把它吃掉，进而让 ifeq 等条件判断出错。
            if not variables[name]:
                variables[name] = value
            elif value:
                variables[name] = variables[name] + " " + value
    elif op in (":=", "::="):
        variables[name] = _make_expand_immediate_value(
            raw, variables, simple, repo, overrides)
        simple[name] = True
    else:
        variables[name] = raw
        simple[name] = False


def _make_apply_define(name: str, op: str, body: str,
                       variables: Dict[str, Optional[str]],
                       simple: Dict[str, bool],
                       overrides: Optional[set] = None,
                       is_override: bool = False,
                       repo: Optional[Path] = None) -> None:
    """按 define 名称后的赋值运算符更新变量表。

    make 4.3 支持 `define X ?=` / `+=` / `:=` / `::=` / `!=` / `=`；
    `?=` 在变量已定义时不覆盖，`+=` 追加而不是替换。原先把运算符从
    名称里截掉后一律替换，会让 `A = foo` 后的 `define A ?= test` 把 A
    错改成 test，探测到并不存在的 test 目标。
    """
    if not name:
        return
    if overrides is None:
        overrides = set()
    if name in overrides and not is_override:
        return
    if op == "?=" and name in variables:
        return
    if is_override:
        overrides.add(name)
    if op == "!=":
        _make_expand_immediate_value(body, variables, simple, repo,
                                     overrides)
        variables[name] = None
        simple[name] = False
    elif op == "+=":
        if name not in variables:
            variables[name] = body
            simple[name] = False
        elif variables[name] is not None:
            value = body
            if simple.get(name):
                value = _make_expand_immediate_value(
                    value, variables, simple, repo, overrides)
            if not variables[name]:
                variables[name] = value
            elif value:
                variables[name] = variables[name] + " " + value
    elif op in (":=", "::="):
        variables[name] = _make_expand_immediate_value(
            body, variables, simple, repo, overrides)
        simple[name] = True
    else:
        variables[name] = body
        simple[name] = False


def _make_assignment_name_bad_escape(token: str) -> bool:
    r"""赋值名顶层是否含 `\ ` / `\:` / `\#` 这类非法转义。

    函数参数里的反斜杠由函数自己解释，不属于变量名语法；只扫描变量
    引用之外，避免 `$(patsubst a\ b,test,$$) = x` 被误判成 missing
    separator。
    """
    i = 0
    n = len(token)
    while i < n:
        ch = token[i]
        if ch == "$" and i + 1 < n and token[i + 1] in "({":
            opener = token[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 1
            j = i + 2
            while j < n and depth:
                if token[j] == opener:
                    depth += 1
                elif token[j] == closer:
                    depth -= 1
                j += 1
            if depth:
                return False
            i = j
            continue
        if ch == "\\" and i + 1 < n and token[i + 1] in " \t:#":
            return True
        i += 1
    return False


def _make_dynamic_assignment_name(body: str) -> Optional[str]:
    """返回 `$($(A)) = x` 这类含嵌套引用的赋值变量名。

    `_MAKE_DYNAMIC_VAR_ASSIGNMENT` 的单元只支持一层 `$(...)`；变量名
    本身由变量展开得到（`$($(A))` / `${${A}}`）时正则匹配不到，赋值
    会被当成普通行，展开为空的名字也不会触发 make 的 fatal 错误。
    这里只负责切出变量名 token，真正的展开交给调用方。
    """
    rest = body.lstrip(" \t")
    while True:
        modifier = re.match(
            r"(?:export|override|private)(?:[ \t]+|$)", rest)
        if modifier is None:
            break
        rest = rest[modifier.end():]
    n = len(rest)
    i = 0
    has_ref = False
    while i < n:
        ch = rest[i]
        # 顶层变量名可以含未转义的 `;`（`A;B=x` 是合法赋值）；它只在
        # 规则头的目标之后才开始 recipe。空白/冒号/井号/等号仍然结束
        # 变量名。
        if ch in " \t:#=":
            break
        if ch == "\\":
            i += 2
            continue
        if ch == "$" and i + 1 < n and rest[i + 1] in "({":
            has_ref = True
            stack = [")" if rest[i + 1] == "(" else "}"]
            j = i + 2
            while j < n and stack:
                cj = rest[j]
                if cj == "$" and j + 1 < n and rest[j + 1] in "({":
                    stack.append(")" if rest[j + 1] == "(" else "}")
                    j += 2
                    continue
                if cj == stack[-1]:
                    stack.pop()
                j += 1
            if stack:
                return None
            i = j
            continue
        if ch == "$":
            has_ref = True
            i += 2
            continue
        i += 1
    if not has_ref or i == 0:
        return None
    token = rest[:i]
    j = i
    while j < n and rest[j] in " \t":
        j += 1
    # GNU make 4.3 不把 `:::=` 当作赋值运算符；动态变量名后跟
    # `:::=`（`$(X):::=x`）仍按规则头解析，不能整行吞成赋值。
    if not any(rest.startswith(op, j)
               for op in ("::=", ":=", "?=", "+=", "!=", "=")):
        return None
    # 转义空白/冒号/井号不能进入顶层变量名（`A\:B=x` / `A\ B=x`
    # 会让 make 报 missing separator），即使变量名里还有合法引用。
    # 函数参数里的转义空白不属于变量名语法。
    if _make_assignment_name_bad_escape(token):
        return None
    # `X$(Y)?=1` / `X$(Y)+=1` / `X$(Y)!=1` 的运算符前半截会被扫描
    # 进 token；剥掉它交给调用方按原行识别完整运算符。
    if rest[j:j + 1] == "=" and token[-1:] in ("?", "+", "!"):
        token = token[:-1]
    return token


def _make_expand_assignment_name(
        name: str,
        variables: Dict[str, Optional[str]],
        simple: Dict[str, bool],
        repo: Optional[Path] = None,
        overrides: Optional[set] = None) -> str:
    """按 make 读取期语义展开赋值语句左侧的变量名。

    变量名里的静态函数/条件函数可能展开为空（`$(strip ) = x` /
    `$(if ,x) = x`），make 会报 empty variable name；只展开普通变量
    引用会把函数原文当成非空名字，误判成合法赋值。条件函数必须与静态
    函数交替展开，且未生效分支不能提前求值。value/foreach/call 与
    info/warning 同样会在读取期展开并可能得到空名字
    （`$(foreach v,,x) = 1` / `$(info x) = 1`）。
    """
    for _ in range(20):
        before = name
        name = _make_expand_automatic_refs(name)
        # 静态函数先于普通引用：参数边界按原文确定，foreach/call 的局部
        # 变量也不能在绑定前被当成外层变量清空（`$(foreach v,a,$(v))`
        # 必须展开成 a，而不是先清空 `$(v)` 得到空名字）。
        if repo is not None:
            name = _make_expand_include_functions(
                name, repo, variables, simple, overrides)
        name = _make_expand_value(name, variables, simple)
        name = _make_expand_foreach(name, variables, simple, repo)
        name = _make_expand_call_functions(
            name, variables, simple, repo, overrides)
        name = _make_resolve_single_char_refs(name, variables, simple)
        name = _make_expand_refs(name, variables, simple, repo=repo)
        name = _make_expand_condition_functions(
            name, variables, simple, repo)
        name = _make_expand_eval_functions(
            name, variables, simple, repo, overrides)
        name = _make_expand_metadata_functions(
            name, variables, simple, overrides)
        name = _make_expand_error_functions(name)
        name = _make_expand_side_effect_functions(
            name, variables, simple, repo, overrides)
        name = _make_expand_refs(name, variables, simple, repo=repo)
        if repo is not None:
            name = _make_expand_include_functions(
                name, repo, variables, simple, overrides)
            name = _make_expand_refs(name, variables, simple)
        name = _make_expand_computed_refs(name, variables, simple)
        name = _make_resolve_single_char_refs(name, variables, simple)
        if name == before:
            break
    return name


def _make_scan_assignment(body: str,
                          variables: Dict[str, Optional[str]],
                          simple: Dict[str, bool],
                          overrides: Optional[set] = None,
                          repo: Optional[Path] = None) -> Optional[str]:
    """处理一行赋值/undefine；是赋值时返回展开后的行，否则返回 None。"""
    if overrides is None:
        overrides = set()
    stripped_body = _make_strip_comment(body)
    # undefine 的名称同样在读取期展开，且可以包含空白/等号等字符
    # （`undefine $(strip X)` / `undefine X Y`）。按固定变量名正则匹配
    # 会漏掉函数形式：名称展开为空时 make 报 empty variable name，探测
    # 却继续把后面的 test 目标当成可运行套件。
    undef = re.match(
        r"^[ ]*(?:(?:override|export|private)[ \t]+)*undefine"
        r"(?:[ \t]+(.*?))?[ \t]*$", stripped_body)
    if undef is not None:
        raw_name = undef.group(1) or ""
        name = _make_expand_assignment_name(
            raw_name, variables, simple, repo, overrides)
        # 与普通赋值不同，undefine 的名称只含空白也是 empty variable
        # name（`undefine $(subst a, ,a)`），不能只用真值判断。名字里
        # 只剩未知引用（`undefine $(shell ...)`）时输出可能为空，同样
        # 无法确认套件可运行。
        if (not name.strip()
                or _make_unknown_name_may_be_empty(name)):
            raise _MakeRequiredIncludeError("empty variable name")
        # 普通 undefine 不能删除 override 变量；override undefine 才行。
        if name in overrides and "override" not in (
                stripped_body[:undef.start(1)].split()):
            return body
        variables.pop(name, None)
        simple.pop(name, None)
        overrides.discard(name)
        return body
    if _MAKE_EMPTY_UNDEFINE.match(stripped_body):
        raise _MakeRequiredIncludeError("empty variable name")
    # `?=x` / `+=x` / `!=x` 这类运算符开头的行是空变量名，make 直接
    # 报错；普通赋值正则会把运算符首字符当成变量名（名为 `?` / `+` /
    # `!`），必须优先按空名字拒绝。
    if _MAKE_TRULY_EMPTY_VAR_ASSIGNMENT.match(
            _make_strip_comment(body)):
        raise _MakeRequiredIncludeError("empty variable name")
    match = _MAKE_VAR_ASSIGNMENT.match(body)
    expanded = body
    if match is None and "$" in body:
        computed_name = _make_dynamic_assignment_name(body)
        if computed_name is not None:
            # 只有原行本身是「动态变量名 + 赋值运算符」时才展开后重试；
            # `$(T) foo=bar test:` 原行是目标列表，展开后以 foo=bar 开头
            # 也不能反过来当成变量赋值。
            #
            # 变量名里的单字符引用（`$x` / `$:` / `$#`）同样在读取阶段
            # 展开；展开为空（`$x = 1`、`$(UNDEFINED) += 1`）时 make
            # 直接报 `empty variable name`。静态函数与条件函数也在读取
            # 期展开（`$(strip ) = x` 会变成空名字），只按普通变量引用
            # 展开会把函数原文当成合法名字。
            name = _make_expand_assignment_name(
                computed_name, variables, simple, repo, overrides)
            if (not name
                    or _make_unknown_name_may_be_empty(name)):
                raise _MakeRequiredIncludeError("empty variable name")
            # 从原行里取出赋值运算符与其后的值；不能整行展开，递归变量
            # 的值应当在被引用时再展开。
            j = body.find(computed_name) + len(computed_name)
            while j < len(body) and body[j] in " \t":
                j += 1
            op = next((candidate for candidate in
                       (":::=", "::=", ":=", "?=", "+=", "!=", "=")
                       if body.startswith(candidate, j)), "=")
            raw = body[j + len(op):]
            _make_apply_assignment_parts(
                name, op, raw, body[:body.find(computed_name)],
                variables, simple, overrides, repo)
            return body
    if match is None:
        if _MAKE_EMPTY_VAR_ASSIGNMENT.match(_make_strip_comment(expanded)):
            # `$(UNDEFINED) = x` 展开后是空变量名，make 在读取阶段直接报错。
            raise _MakeRequiredIncludeError("empty variable name")
        return None
    _make_apply_assignment(match, variables, simple, overrides, repo)
    return expanded


def _make_scan_assignments(text: str,
                           variables: Dict[str, Optional[str]],
                           simple: Dict[str, bool],
                           overrides: Optional[set] = None,
                           repo: Optional[Path] = None) -> None:
    """按出现顺序把文本里的单行赋值应用到变量表（recipe 行除外）。"""
    if overrides is None:
        overrides = set()
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if not body.startswith("\t"):
            _make_scan_assignment(body, variables, simple, overrides, repo)


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


def _make_target_assignment_parts(rest: str) -> Tuple[str, Optional[str]]:
    """拆出规则头冒号后的 target-specific 赋值名原文与运算符。"""
    pos = 0
    n = len(rest)
    while True:
        while pos < n and rest[pos] in " \t":
            pos += 1
        modifier = re.match(r"(?:export|private|override)[ \t]+", rest[pos:])
        if modifier is None:
            break
        pos += modifier.end()
    start = pos
    while pos < n:
        ch = rest[pos]
        if ch == "$" and pos + 1 < n and rest[pos + 1] in "({":
            opener = rest[pos + 1]
            closer = ")" if opener == "(" else "}"
            depth = 1
            pos += 2
            while pos < n and depth:
                if rest[pos] == "\\":
                    pos += 2
                    continue
                if rest[pos] == "(" and opener == "(":
                    depth += 1
                elif rest[pos] == "{" and opener == "{":
                    depth += 1
                elif rest[pos] == closer:
                    depth -= 1
                pos += 1
            continue
        if ch == "\\" and pos + 1 < n and rest[pos + 1] not in " \t#:=":
            pos += 2
            continue
        if ch in " \t#:=;+?!":
            break
        pos += 1
    prefix = rest[start:pos]
    while pos < n and rest[pos] in " \t":
        pos += 1
    op_match = re.match(r"(?:::=|::=|:=|[+?]?=|!=)", rest[pos:])
    if not prefix or op_match is None:
        return "", None
    return prefix, op_match.group(0)


def _make_raw_rule_is_target_assignment(
        rest: str,
        variables: Dict[str, Optional[str]],
        simple: Dict[str, bool],
        repo: Optional[Path] = None,
        overrides: Optional[set] = None) -> bool:
    """原始规则头冒号后是否会被 make 当成 target-specific 赋值。

    GNU make 在展开前就决定第一个 token（跳过 export/private/override
    修饰符）是不是赋值名，并展开该 token 判断其后是否紧跟赋值运算符。
    `test: $(U) X=1` 的第一个 token 展开为空，后面的 X=1 只是前置依赖；
    `test: $(U)override X=1` 的第一个 token 展开为 override，但后面不是
    运算符，也仍是依赖。变量引用与赋值名粘在同一 token
    （`$(U)X=1` / `$(T)=1`）才是赋值。
    """
    prefix, op = _make_target_assignment_parts(rest)
    if op is None:
        return False
    try:
        # 赋值名同样按 make 语义展开：静态/条件/foreach/call/value 等
        # 函数可能展开成空串，此时 make 报 empty variable name
        # （`test:$(if ,x)=1` / `test:$(foreach v,,x)=1`），不能因为
        # 原文非空就当成合法赋值。复用普通赋值名的完整展开逻辑，避免
        # 两条路径对函数覆盖不一致。
        name = _make_expand_assignment_name(
            prefix, variables, simple, repo, overrides)
    except _MakeRequiredIncludeError:
        return False
    if (not name
            or _make_unknown_name_may_be_empty(name)):
        # 原始规则头的 target-specific 赋值变量名展开为空（如
        # `test:$(X)=1`，X 未定义）时 make 报 empty variable name。
        # 必须在这里拒绝：整行展开后会变成 `test:=1`，下游会把它
        # 误当成合法的变量赋值而放过，随后把 test 探测成可运行套件。
        raise _MakeRequiredIncludeError("empty variable name")
    return True


def _make_validate_ignored_rule_deps(
        rest: str, variables: Dict[str, Optional[str]],
        simple: Dict[str, bool], overrides: Optional[set],
        repo: Optional[Path] = None) -> None:
    r"""校验行首 `\;` 被忽略的规则里依赖列表的读取期展开。

    `\;foo: $(error x)` 不定义目标，但 make 仍会展开依赖并执行其中的
    eval；`$(error x)` / `$(word x,a)` / `$(eval foo: a:b)` 都会让读取
    立即失败。原实现直接跳过整行，后面的 test 目标被误判成可运行套件。
    用临时立即赋值承载依赖文本：它不按规则头校验 `a:b`（make 对这类
    被忽略的行也不报错），但会走完整的读取期展开/求值路径。临时变量
    名在结束后恢复，eval 对真实变量的副作用照常保留。
    """
    temp_name = "__xuen_ignored_rule_deps__"
    marker = object()
    saved_value = variables.get(temp_name, marker)
    saved_simple = simple.get(temp_name, marker)
    saved_override = temp_name in overrides if overrides is not None else False
    try:
        _make_scan_assignment(temp_name + " := " + rest, variables, simple,
                              overrides, repo)
    finally:
        if saved_value is marker:
            variables.pop(temp_name, None)
        else:
            variables[temp_name] = saved_value
        if saved_simple is marker:
            simple.pop(temp_name, None)
        else:
            simple[temp_name] = saved_simple
        if overrides is not None:
            if saved_override:
                overrides.add(temp_name)
            else:
                overrides.discard(temp_name)


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
    overrides: set = set()
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
            name_text, define_op = _make_define_header(
                _make_strip_value_comment(define_match.group(1) or ""))
            name = _make_expand_refs(name_text, variables, simple)
            define_prefix = body[:body.find("define")].split()
            define_override = "override" in define_prefix
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
            _make_apply_define(name, define_op, "\n".join(body_lines),
                               variables, simple, overrides, define_override,
                               repo)
            # define 块本身不定义目标，但 make 读取时会清空当前目标。
            out.append(_MAKE_CONTEXT_RESET + newline)
            continue
        expanded = _make_scan_assignment(
            body, variables, simple, overrides, repo)
        if expanded is not None:
            # 赋值/undefine 行不定义目标。输出成哨兵注释，防止变量展开
            # 后的目标行（如 `$(T) foo=bar test:`，T 为空）被误认成赋值；
            # 同时让后续 recipe 上下文检查知道这里清空过当前目标。
            out.append(_MAKE_CONTEXT_RESET + newline)
            i += 1
            continue
        if body.lstrip().startswith("#"):
            out.append(line)
            i += 1
            continue
        if (_MAKE_NON_RULE_DIRECTIVE.match(body) is not None
                or _MAKE_EXPORT_DIRECTIVE.match(body) is not None):
            # include/vpath/export 等指令的参数在读取期展开；其中的
            # `$(eval x)` 会立即解析参数行并失败。赋值形式的 export 已在
            # 上面按赋值处理，这里只校验非赋值指令。
            _make_expand_eval_functions(
                body, variables, simple, repo, overrides)
        # 行尾注释不是 eval 调用的一部分，但 eval 仍会在读取期展开；
        # `$(eval x) #c := $$` 的 `#` 之后是注释，`$(eval x)` 仍需执行。
        eval_args = _make_standalone_eval_args(
            _make_strip_comment(body))
        if eval_args is not None:
            # eval 的参数先原样作为 Makefile 行插入，交给同一轮主循环按
            # 顺序展开/应用（参数里的赋值也要影响后续行）。eval 行本身
            # 不建立当前目标，插入后补一个上下文重置哨兵。
            injected: List[str] = []
            for argument in eval_args:
                for eval_line in argument.splitlines():
                    injected.append(eval_line + newline)
            lines[i:i + 1] = injected + [_MAKE_CONTEXT_RESET + newline]
            continue
        stripped_body = body.lstrip(" \t")
        if stripped_body.startswith("\\;"):
            special_colon = _make_unescaped_colon(body, 0)
            if special_colon >= 0:
                if not _make_has_recipe_separator(
                        body[special_colon + 1:], skip_refs=True):
                    # 行首 `\;` 在没有原文同行分隔符时会让 make 忽略
                    # 整行，不定义任何目标；后续 tab 行会报 recipe
                    # commences before first target。整行虽被忽略，依赖
                    # 列表仍会在读取期展开，其中的 error / eval / 函数
                    # 参数错误照样会让 make 直接失败。
                    _make_validate_ignored_rule_deps(
                        body[special_colon + 1:], variables, simple,
                        overrides, repo)
                    out.append(_MAKE_CONTEXT_RESET + newline)
                    i += 1
                    continue
                indent = body[:len(body) - len(stripped_body)]
                stripped_body = stripped_body
                while stripped_body.startswith("\\;"):
                    stripped_body = stripped_body[2:]
                body = indent + stripped_body
        # `&` 后紧跟变量引用的 grouped target 写法在变量展开为空时仍按
        # 普通目标名处理（`test&$(T):` 是目标 test&，不是 grouped test）。
        # 插入一个非空白哨兵，避免展开后误判成 `test&:`。
        early_colon = _make_unescaped_colon(body, 0)
        if (early_colon >= 0
                and _MAKE_EXPORT_DIRECTIVE.match(body) is None
                and _MAKE_NON_RULE_DIRECTIVE.match(body) is None):
            raw_targets = body[:early_colon]
            # 规则头左侧在读取期立即展开；其中的 eval 参数会先作为
            # Makefile 行解析，`$(eval x):` 的 `x` 没有分隔符，make 在
            # 读取阶段就失败。只校验冒号左侧，避免把 target-specific
            # 赋值的延迟右侧（如 `test: A=$(eval x)`）提前求值。
            cleaned_targets = _make_expand_eval_functions(
                raw_targets, variables, simple, repo, overrides)
            if cleaned_targets != raw_targets:
                # eval 返回空串，但其中的赋值会影响同一行后续的目标名：
                # `$(eval X=test)$(X):` 展开后是 `test:`，必须用去掉
                # eval 的文本继续探测。
                body = cleaned_targets + body[early_colon:]
                early_colon = len(cleaned_targets)
                raw_targets = cleaned_targets
            raw_rest_start = early_colon + 1
            if (raw_rest_start < len(body)
                    and body[raw_rest_start] == ":"):
                raw_rest_start += 1
            raw_targets_stripped = raw_targets.rstrip(" \t")
            target_prefix, target_op = _make_target_assignment_parts(
                body[raw_rest_start:])
            if target_op is not None:
                # target-specific 赋值的变量名同样在读取期立即展开，
                # 即使右侧是延迟的 `=`；`test: $(eval x) = x` 里的
                # eval 参数 `x` 没有分隔符，make 直接报错。
                _make_expand_eval_functions(
                    target_prefix, variables, simple, repo, overrides)
            else:
                # 不是 target-specific 赋值时，冒号后的依赖列表在读取期
                # 展开；同行 recipe（分号后）不在读取期展开，不能提前
                # 校验其中的 eval。
                header_rest = body[raw_rest_start:]
                header_end = _make_rule_header_rest_end(header_rest)
                _make_expand_eval_functions(
                    header_rest[:header_end], variables, simple, repo,
                    overrides)
                # 目标列表展开为空时 make 忽略整行，连前置依赖都不会
                # 展开：`$(X): $(word x,a)` 在 X 为空时仍可运行 test，
                # 提前展开依赖会把必然执行的 test 误判成读取失败。
                # 目标列表本身的展开错误仍要抛出（make 确实会展开它）。
                # 展开顺序与主流程一致：条件先于 foreach，未生效分支
                # 里的函数不能提前求值。
                expanded_targets = _make_expand_value(
                    raw_targets, variables, simple)
                expanded_targets = _make_expand_condition_functions(
                    expanded_targets, variables, simple, repo)
                expanded_targets = _make_expand_foreach(
                    expanded_targets, variables, simple, repo)
                expanded_targets = _make_resolve_single_char_refs(
                    expanded_targets, variables, simple)
                expanded_targets = _make_expand_refs(
                    expanded_targets, variables, simple, repo=repo)
                for _ in range(20):
                    before_targets = expanded_targets
                    expanded_targets = _make_expand_value(
                        expanded_targets, variables, simple)
                    expanded_targets = _make_expand_condition_functions(
                        expanded_targets, variables, simple, repo)
                    expanded_targets = _make_expand_foreach(
                        expanded_targets, variables, simple, repo)
                    expanded_targets = _make_expand_refs(
                        expanded_targets, variables, simple, repo=repo)
                    if repo is not None:
                        expanded_targets = _make_expand_include_functions(
                            expanded_targets, repo)
                        expanded_targets = _make_expand_refs(
                            expanded_targets, variables, simple, repo=repo)
                    expanded_targets = _make_expand_computed_refs(
                        expanded_targets, variables, simple)
                    expanded_targets = _make_resolve_single_char_refs(
                        expanded_targets, variables, simple)
                    if expanded_targets == before_targets:
                        break
                expanded_targets = expanded_targets.strip(" \t")
                if (expanded_targets == ""
                        or (expanded_targets == "&"
                            and raw_targets.endswith("&"))):
                    # make 把空目标列表当成可挂 recipe 的空规则：后续
                    # tab 行合法但不会影响任何具名目标，输出一个空规则
                    # 保留这个上下文，不能当作赋值清空当前目标。
                    out.append(":" + newline)
                    i += 1
                    continue
            if target_op in (":=", "::=", "!=", ":::="):
                # target-specific 立即赋值的目标列表非空时，右侧也在
                # 读取期展开；`%: X := $(eval x)` 会先执行 eval 并失败。
                # 目标列表展开为空时 make 连右侧都忽略，不能提前报错。
                immediate_targets = _make_expand_assignment_name(
                    raw_targets, variables, simple, repo, overrides)
                immediate_targets = immediate_targets.strip(" \t")
                if immediate_targets not in ("", "&"):
                    rest = body[raw_rest_start:]
                    name_at = rest.find(target_prefix)
                    op_at = rest.find(
                        target_op, name_at + len(target_prefix))
                    if op_at >= 0:
                        value = _make_strip_value_comment(
                            rest[op_at + len(target_op):])
                        _make_expand_eval_functions(
                            value, variables, simple, repo, overrides)
            if (target_op is not None
                    and raw_targets.lstrip(" \t") not in ("", "&")
                    and not raw_targets_stripped.endswith(("&", "$"))
                    and _make_unescaped_colon(raw_targets, 0) < 0):
                # target-specific 赋值不定义目标，但赋值右侧并非都在读取
                # 期展开：`=`/`?=`/`+=` 延迟到变量被使用时；目标列表展开
                # 为空时 make 连 `:=`/`!=` 的右侧也忽略。提前整行展开会
                # 把右侧静态函数的 fatal 错误误报成读取错误，漏掉后面的
                # 合法 test 目标。
                expanded_targets = _make_expand_assignment_name(
                    raw_targets, variables, simple, repo, overrides)
                expanded_targets = expanded_targets.strip(" \t")
                if _make_unescaped_colon(expanded_targets, 0) >= 0:
                    # 目标名展开后带未转义冒号（`$(basename a:b): A=x`
                    # 展开成 `a:b: A=x`）时，make 按 static pattern rule
                    # 解析并报 target pattern contains no '%'。
                    raise _MakeRequiredIncludeError(
                        "target pattern contains no '%'")
                if _make_expanded_targets_end_with_colon(
                        expanded_targets):
                    raise _MakeRequiredIncludeError("missing target pattern")
                targets_empty = expanded_targets == "" or (
                    expanded_targets == "&"
                    and raw_targets.rstrip(" \t").endswith("&"))
                if targets_empty:
                    # 目标列表展开为空时 make 按空规则处理，后续 tab 行
                    # 合法且不会清空当前目标；输出空规则而不是赋值哨兵，
                    # 避免把 `$(T): X=1` 后面的 recipe 误报成首个目标
                    # 前的 recipe。
                    out.append(":" + newline)
                    i += 1
                    continue
                if target_op in ("=", "?=", "+="):
                    needs_escaped_check = (
                        _make_targets_have_internal_escaped_semicolon(
                            raw_targets)
                        and not _make_has_recipe_separator(
                            body[raw_rest_start:], skip_refs=True))
                    if (_make_raw_rule_is_target_assignment(
                            body[raw_rest_start:], variables, simple,
                            repo, overrides)
                            and not needs_escaped_check):
                        out.append(_MAKE_CONTEXT_RESET + newline)
                        i += 1
                        continue
        _make_check_top_level_call_args(body)
        # grouped 标记只在原始文本里紧贴规则分隔符的 `&` 才算；由变量/
        # 函数展开产生的尾部 `&` 属于目标名本身（`$(addsuffix &,test):`
        # 定义目标 test&）。这里记录原始状态，展开后再保护产生出的 &。
        raw_grouped_colon = _make_unescaped_colon(body, 0)
        raw_grouped_marker = False
        if raw_grouped_colon > 0 and body[raw_grouped_colon - 1] == "&":
            pos = raw_grouped_colon - 2
            # `\&` 仍被 make 当成 grouped 标记（反斜杠只影响目标名，
            # 不吃掉 & 的分隔语义）；只有紧邻的 `$&` 是单字符变量
            # 引用，不属于标记。`$$&` 里的 `$$` 是字面美元符，后面的
            # & 仍是 grouped 标记，因此按 `$` 个数的奇偶判断引用。
            dollars = 0
            while pos >= 0 and body[pos] == "$":
                dollars += 1
                pos -= 1
            single_ref = dollars % 2 == 1
            raw_grouped_marker = not single_ref
        expand_input = re.sub(r"&(?=\$[({])", "&\x01", body)
        expanded = _make_expand_value(
            expand_input, variables, simple)
        # 静态函数必须在展开变量引用之前处理：参数边界按原文确定，
        # `$(subst $x ,...)` 里 `$x` 展开为空后剩下的空格属于参数值，
        # 先展开变量会让静态函数误把它当成函数名后的语法空白丢掉。
        # 它也要先于条件函数：`$(addsuffix $(if x, foo, bar), test)`
        # 的参数空白由静态函数按原文保留。
        if repo is not None:
            expanded = _make_expand_include_functions(
                expanded, repo, variables, simple, overrides)
        # 条件函数必须先于 foreach/变量展开：if 参数的源码空白在展开前
        # 去掉，而展开结果里的空白（如 foreach 空 body）是值的一部分。
        expanded = _make_expand_condition_functions(
            expanded, variables, simple, repo)
        expanded = _make_expand_foreach(
            expanded, variables, simple, repo)
        # call 的参数边界同样按原文确定；必须在普通变量引用展开前处理，
        # 否则 `${a,b}` 会先被当成变量名整体展开，跨括号类型留下的
        # `${a` 片段也就不再暴露 make 的 unterminated reference 错误。
        expanded = _make_expand_call_functions(
            expanded, variables, simple, repo, overrides)
        expanded = _make_expand_refs(
            expanded, variables, simple, repo=repo)
        # 目标名/依赖里的静态条件函数（如 `$(if ...)`）也要按 make
        # 语义展开；否则本来能定义 test 目标的规则会漏检。条件函数与
        # 静态函数要交替展开到不动点：先条件后静态才能正确处理
        # `$(strip $(or ,test))`，而条件参数里也可能嵌套静态函数。
        for _ in range(20):
            before = expanded
            expanded = _make_expand_value(
                expanded, variables, simple)
            if repo is not None:
                expanded = _make_expand_include_functions(
                    expanded, repo, variables, simple, overrides)
            expanded = _make_expand_condition_functions(
                expanded, variables, simple, repo)
            expanded = _make_expand_foreach(
                expanded, variables, simple, repo)
            expanded = _make_expand_call_functions(
                expanded, variables, simple, repo, overrides)
            expanded = _make_expand_metadata_functions(
                expanded, variables, simple, overrides)
            expanded = _make_expand_error_functions(expanded)
            expanded = _make_expand_side_effect_functions(
                expanded, variables, simple, repo, overrides)
            expanded = _make_expand_refs(
                expanded, variables, simple, repo=repo)
            expanded = _make_expand_refs(
                expanded, variables, simple, repo=repo)
            if expanded == before:
                break
        expanded = _make_expand_computed_refs(expanded, variables, simple)
        # make 在展开前判定 target-specific 赋值：原始行第一个变量名
        # token 展开为空、或其后不是运算符时，后面的 `X=1` 只是前置
        # 依赖。整行展开后不能把它误认成赋值；插入哨兵让下游赋值识别
        # 失败，test 目标仍按规则头探测。
        raw_colon = _make_unescaped_colon(body, 0)
        expanded_colon = _make_unescaped_colon(expanded, 0)
        if (raw_colon >= 0
                and _MAKE_EXPORT_DIRECTIVE.match(body) is None
                and _MAKE_NON_RULE_DIRECTIVE.match(body) is None):
            # 原始规则头的 target-specific 赋值变量名展开为空时 make
            # 直接报 empty variable name；必须在整行展开丢失冒号/空格
            # 之前判定（`test:$(X)=1` 展开后是 `test:=1`）。
            # 行首 export/vpath 等指令里的冒号/等号只是参数文本，不是
            # 规则头（`export test:$(X)=1` 仍能执行后面的 test 目标）。
            raw_targets = body[:raw_colon]
            skip = raw_targets.lstrip(" \t") in ("", "&")
            double_colon = (raw_colon + 1 < len(body)
                            and body[raw_colon + 1] == ":")
            if (not skip and double_colon
                    and _make_target_list_only_variable_refs(raw_targets)):
                # `$::$(X)=1` 这类目标列表只有变量引用、展开为空，
                # 后面的 `$(X)=1` 不是 target-specific 赋值。
                skip = True
            if (not skip
                    and _make_target_list_has_bare_trailing_dollar(raw_targets)):
                # `foo$:$(X)=1` 的 `$:` 会吃掉规则分隔符，后面的内容按
                # recipe/赋值处理，不再是 target-specific 赋值。双冒号
                # `foo $::$(X)=1` 的第二个冒号仍是规则分隔符，且目标前缀
                # 有字面名字时，后面仍是 target-specific 赋值。
                prefix = raw_targets[:-1]
                if (not double_colon
                        or (_make_target_text_only_refs(prefix)
                            and ("$" in prefix
                                 or prefix.strip(" \t") == ""))):
                    skip = True
            if not skip:
                expanded_targets = _make_expand_value(
                    raw_targets, variables, simple)
                # 条件先于 foreach：未生效分支里的 foreach 参数错误
                # 不能让 make 失败，也不能把分支里的逗号当成目标名。
                expanded_targets = _make_expand_condition_functions(
                    expanded_targets, variables, simple, repo)
                expanded_targets = _make_expand_foreach(
                    expanded_targets, variables, simple, repo)
                expanded_targets = _make_resolve_single_char_refs(
                    expanded_targets, variables, simple)
                expanded_targets = _make_expand_refs(
                    expanded_targets, variables, simple, repo=repo)
                # 目标列表也可能由条件/静态函数组成：`$(if ,x):$(Y)=1`
                # 的目标展开为空，make 接受后面的赋值；不展开会把非空
                # 原文当成目标，误报 empty variable name。
                for _ in range(20):
                    before_targets = expanded_targets
                    expanded_targets = _make_expand_value(
                        expanded_targets, variables, simple)
                    expanded_targets = _make_expand_condition_functions(
                        expanded_targets, variables, simple, repo)
                    expanded_targets = _make_expand_foreach(
                        expanded_targets, variables, simple, repo)
                    expanded_targets = _make_expand_refs(
                        expanded_targets, variables, simple, repo=repo)
                    if repo is not None:
                        expanded_targets = _make_expand_include_functions(
                            expanded_targets, repo)
                        expanded_targets = _make_expand_refs(
                            expanded_targets, variables, simple, repo=repo)
                    expanded_targets = _make_expand_computed_refs(
                        expanded_targets, variables, simple)
                    expanded_targets = _make_resolve_single_char_refs(
                        expanded_targets, variables, simple)
                    if expanded_targets == before_targets:
                        break
                # 目标列表本身展开为空（`$(X):$(Y)=1` / `$x:...`）时
                # make 接受空目标，不会报空变量名。只有原文以字面 `&`
                # 结尾时才是 grouped 标记；`&$x` / `&$(G)` 展开成 `&`
                # 时仍是普通目标，后面的空变量名照样报错（前面已按原文
                # 判断过整体就是 `&` 的情况）。
                expanded_targets = expanded_targets.strip(" \t")
                if _make_expanded_targets_end_with_colon(
                        expanded_targets):
                    # `$(join test,:):` 展开成 `test::`，但第一个冒号来自
                    # 目标名，make 报 missing target pattern；字面 `test::`
                    # 是合法的双冒号规则，不能在展开后的文本上区分。
                    raise _MakeRequiredIncludeError("missing target pattern")
                skip = expanded_targets == "" or (
                    expanded_targets == "&"
                    and raw_targets.endswith("&"))
            if not skip:
                # 只跨过规则分隔符本身（`:` 或 `::`）。再多的冒号属于
                # 目标模式/赋值运算符，`foo::: X=1` 是 make 读取错误，
                # 不能因为后面看似 `X=1` 就把整行当合法赋值吞掉。
                #
                # 目标列表以裸 `$` 结尾时，raw_colon 处的冒号已被 `$:`
                # 吃掉，真正的规则分隔符从下一字符开始：`x$::$(X)=1`
                # 余下的是单冒号，`x$:::$(X)=1` 则是双冒号。按原文冒号
                # 位置只跨一个会把 `:$(X)=1` 当成剩余文本，漏掉空变量名
                # 错误（make 报 empty variable name）。
                rest_start = raw_colon + 1
                if _make_target_list_has_bare_trailing_dollar(raw_targets):
                    if body.startswith("::", rest_start):
                        rest_start += 2
                    elif body.startswith(":", rest_start):
                        rest_start += 1
                elif (rest_start < len(body)
                        and body[rest_start] == ":"):
                    rest_start += 1
                if (_make_raw_rule_is_target_assignment(
                        body[rest_start:], variables, simple, repo,
                        overrides)
                        and not (
                            _make_has_escaped_semicolon(raw_targets)
                            and not _make_has_recipe_separator(
                                body[raw_colon + 1:], skip_refs=True))):
                    # target-specific 赋值不定义可执行目标。原文可能因
                    # 变量名展开成空白（`test:$(if x, ,)=1`）而在整行
                    # 展开后不再符合赋值形态，继续输出会被下游当成非法
                    # 规则头拒绝掉后面合法的 test；直接按赋值行处理，
                    # 同时用哨兵清空 recipe 上下文（与普通赋值一致）。
                    out.append(_MAKE_CONTEXT_RESET + newline)
                    i += 1
                    continue
        raw_bare_empty = False
        if raw_colon >= 0:
            raw_targets = body[:raw_colon]
            prefix = (raw_targets[:-1] if raw_targets.endswith("$")
                      else raw_targets)
            if (raw_colon + 1 < len(body)
                    and body[raw_colon + 1] == ":"
                    and ("$" in prefix
                         or prefix.strip(" \t") == "")
                    and _make_target_text_only_refs(raw_targets)):
                # `$::$(X)=1` 的目标列表展开为空，后面的赋值不是
                # target-specific 赋值，make 接受。
                raw_bare_empty = True
        if (raw_colon >= 0 and expanded_colon >= 0
                and not raw_bare_empty
                and _make_rule_is_target_specific(expanded, expanded_colon)
                and not _make_rule_is_target_specific(body, raw_colon)):
            rest_start = raw_colon + 1
            if (rest_start < len(body)
                    and body[rest_start] == ":"):
                rest_start += 1
            if not _make_raw_rule_is_target_assignment(
                    body[rest_start:], variables, simple, repo,
                    overrides):
                insert_at = expanded_colon + 1
                if (insert_at < len(expanded) and expanded[insert_at] == ":"):
                    insert_at += 1
                while insert_at < len(expanded) and expanded[insert_at] in " \t":
                    insert_at += 1
                expanded = expanded[:insert_at] + "\x02" + expanded[insert_at:]
        raw_rule_colon = _make_unescaped_colon(body, 0)
        if (raw_rule_colon >= 0
                and _MAKE_EXPORT_DIRECTIVE.match(body) is None
                and _MAKE_NON_RULE_DIRECTIVE.match(body) is None):
            expanded_rule_colon = _make_unescaped_colon(expanded, 0)
            raw_targets = body[:raw_rule_colon]
            if (expanded_rule_colon >= 0
                    and "=" in expanded[:expanded_rule_colon]
                    and "=" not in _make_name_without_refs(raw_targets)):
                # make 在展开前已把这一行判定为规则；目标名展开后即使
                # 含 `=`（`$(notdir a=b): a:b`）也不会重新变成变量赋值。
                # 用哨兵保留「这是规则」的信息，下游才能继续检查依赖里
                # 的第二个冒号并报 target pattern contains no '%'。
                expanded = (
                    expanded[:expanded_rule_colon].replace("=", "\x04")
                    + expanded[expanded_rule_colon:])
            elif (expanded_rule_colon >= 0
                    and _MAKE_VAR_ASSIGNMENT.match(expanded) is not None
                    and _MAKE_VAR_ASSIGNMENT.match(body) is None):
                # 原文是规则，但目标表达式展开后整行长得像赋值
                # （`$(join a::=b,):` 展开成 `a::=b:`）。make 在展开前
                # 已决定这是规则，不能按赋值跳过；遮住等号让下游继续
                # 检查 `=b:` 的空变量名错误，同时保留 test 目标词。
                expanded = expanded.replace("=", "\x04")
        expanded = _make_flatten_target_newlines(expanded)
        expanded = _make_resolve_single_char_refs(
            expanded, variables, simple)
        if not raw_grouped_marker:
            expanded_colon_now = _make_unescaped_colon(expanded, 0)
            if (expanded_colon_now > 0
                    and expanded[expanded_colon_now - 1] == "&"):
                # 展开出来的 & 不是 grouped 标记，用普通目标名哨兵保留，
                # 避免下游剥成 test 或误报「grouped target 缺 recipe」。
                expanded = (expanded[:expanded_colon_now - 1] + "\x05"
                            + expanded[expanded_colon_now:])
        if (_MAKE_EXPORT_DIRECTIVE.match(expanded)
                and not _MAKE_EXPORT_DIRECTIVE.match(body)):
            # 这是变量展开后才变成 export/unexport 的目标行；加哨兵避免
            # 下游把它误当成字面导出指令而漏掉同一目标列表里的 test。
            expanded = "\x01" + expanded
        if ("#" not in body
                or ("\\#" not in body
                    and "#" not in _make_name_without_refs(body))):
            # 注释在展开前就已切掉，变量值里的 # 是目标名的一部分，
            # 不能让下游把它当成注释起点而漏掉同一目标列表里的 test。
            # # 可能出现在变量引用内部（`$(notdir #c)` 的 # 不是注释
            # 起点），因此引用被遮住后没有 # 时也要替换；源文件里
            # 转义的 `\#` 仍按字面名字保留。
            expanded = expanded.replace("#", "\x01")
        if body.strip() and not expanded.strip():
            # 非空原文展开成空行（`$:` / `$(UNDEFINED)` / `$(info ...)`）
            # 会清空 make 的当前目标，后续 tab 行报 recipe commences
            # before first target；用哨兵保留「这里有一行非空输入」，
            # 字面空行/纯空白行则不影响 recipe 归属。
            expanded = _MAKE_CONTEXT_RESET
        if not body.startswith("\t") and expanded.startswith("\t"):
            # recipe 行与否按原文首字符判定；`$<\ttest:` 这类原文不是
            # recipe、展开后却以 tab 开头的行仍是规则头（tab 只是目标
            # 列表里的空白）。保留 tab 会让下游按 recipe 跳过，漏掉
            # 实际可执行的 test 目标。
            expanded = " " + expanded.lstrip("\t")
        expanded_rule_colon = _make_unescaped_colon(expanded, 0)
        raw_rule_colon = _make_unescaped_colon(body, 0)
        if (expanded_rule_colon >= 0
                and expanded[expanded_rule_colon:expanded_rule_colon + 2]
                == "::"
                and not (raw_rule_colon >= 0
                         and body[raw_rule_colon:raw_rule_colon + 2]
                         == "::")
                and expanded[:expanded_rule_colon].strip(" \t")
                and not expanded[:expanded_rule_colon].lstrip(
                    " \t").startswith(":")):
            # 原文只有单冒号，但目标表达式展开出的冒号紧挨规则分隔符
            # 形成 `::`（`foo $(if x,:,):` 展开成 `foo ::`）。make 把
            # 前一个冒号当成目标名的一部分，报 missing target pattern；
            # 字面 `foo ::` 已由 raw 双冒号分支排除。
            raise _MakeRequiredIncludeError("missing target pattern")
        if (raw_rule_colon >= 0 and expanded_rule_colon >= 0
                and _MAKE_EXPORT_DIRECTIVE.match(body) is None
                and _MAKE_NON_RULE_DIRECTIVE.match(body) is None
                and _make_targets_have_internal_escaped_semicolon(
                    body[:raw_rule_colon])
                and not _make_has_recipe_separator(
                    body[raw_rule_colon + 1:], skip_refs=True)):
            # 原始目标名内部的 \; 必须由同一逻辑行原文里的未转义分号
            # 提供 recipe 分隔符，否则 make 读取阶段就报 missing
            # separator。引用内部的 ; 和展开产生的 \; 都不算。
            raise _MakeRequiredIncludeError("missing separator")
        out.append(expanded + newline)
        i += 1
    return "".join(out)


_MAKE_INCLUDE_LINE = re.compile(
    r"^[ ]*(include|-include|sinclude)[ \t]+(.*)$")
_MAKE_CONDITIONAL_LINE = re.compile(
    r"^[ \t]*(ifeq|ifneq|ifdef|ifndef|else|endif)(?:[ \t]+(.*))?$")
_MAKE_DEFINE_LINE = re.compile(
    r"^[ \t]*(?:(?:override|export|private)[ \t]+)*define"
    # `define = x` / `define += x` 等是名为 define 的普通变量赋值，不是
    # define 指令；按指令处理会把后面的真实目标吞进 define 体，导致可
    # 运行的 test 套件漏检。`:::=` 不被 GNU make 4.3 当成赋值运算符。
    r"(?:[ \t]+(?!(?:::=|::=|:=|\?=|\+=|!=|=))(.*))?$")
# endef 后只要求有空白分隔；多余文本在生效分支只警告
# （extraneous text after 'endef' directive），仍会结束 define 块。
_MAKE_ENDEF_LINE = re.compile(r"^[ \t]*endef(?:[ \t].*)?$")
# 未生效条件分支里 make 对 define/endef 仍做词法配对，但只认没有尾随
# 文本的 endef；`endef foo` 不会结束 define，后面直到真正的 endef/EOF
# 都被吞掉。严格版用于非活动分支，保证探测与 make 行为一致。
_MAKE_ENDEF_LINE_STRICT = re.compile(
    r"^[ \t]*endef(?:[ \t]*(?:#.*)?)?$")
_MAKE_DEFINE_EMPTY_NAME = re.compile(r"^(?:::=|::=|:=|\?=|\+=|!=|=)")
_MAKE_DEFINE_OPERATORS = (":::=", "::=", ":=", "?=", "+=", "!=", "=")


def _make_define_header(text: str) -> Tuple[str, str]:
    """切分 define 行里的变量名与赋值运算符。

    GNU make 只在函数/变量引用之外识别 `=` / `:=` 等运算符：
    `define $(if x,A=B,C)` 的 `=` 属于函数参数，整个名称展开后是
    `A=B`；按第一个 `=` 粗暴截断会得到未闭合的 `$(if x,A`，把一个
    读取期完全合法的 Makefile 误判成不可用套件。引用只按与起始括号
    相同的字符配对，反斜杠后的字符不参与运算符识别。
    """
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if (ch == "$" and i + 1 < n and text[i + 1] in "({"):
            opener = text[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 1
            k = i + 2
            while k < n:
                ck = text[k]
                if ck == "\\":
                    k += 2
                    continue
                if ck == opener:
                    depth += 1
                elif ck == closer:
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            if depth:
                # 未闭合引用会由名称展开路径报错；这里保留原文即可。
                return text.strip(), "="
            i = k + 1
            continue
        if ch == "$":
            i += 2
            continue
        for op in _MAKE_DEFINE_OPERATORS:
            if text.startswith(op, i):
                return text[:i].rstrip(), op
        i += 1
    return text.strip(), "="


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
            # recipe 的续行属于 shell 命令，不能与非 recipe 续行一样合并；
            # 但物理续行本身不以 tab 开头，后续逐行扫描（missing
            # separator / recipe-before-first-target 等）会把它当成新的
            # Makefile 行，把 `\t@r\` + `ue` 这类合法 recipe 误判成
            # 非规则文本。给续行补上 tab 前缀，保持「recipe 行」身份，
            # 同时不改变拼接后的命令主体可供探测的部分。
            out.append(line)
            i += 1
            while _make_line_continues(body) and i < len(lines):
                nxt = lines[i]
                nbody = nxt.rstrip("\r\n")
                if nxt.startswith("\t"):
                    out.append(nxt)
                else:
                    out.append("\t" + nbody + nxt[len(nbody):])
                body = nbody
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


_MAKE_RECIPE_PREFIX_ASSIGNMENT = re.compile(
    r"^[ \t]*(?:(?:override|private|export)[ \t]+)*"
    r"\.RECIPEPREFIX[ \t]*(:::=|::=|:=|\?=|\+=|!=|=)[ \t]*(.*)$")


def _make_normalize_recipe_prefixes(text: str) -> str:
    """把 `.RECIPEPREFIX` 生效后的 recipe 行统一标记为制表符开头。

    后续所有规则扫描都按 GNU make 默认的 tab recipe 前缀实现；Makefile
    用 `.RECIPEPREFIX = >` 改写前缀时，真正的 recipe 行会被当成
    missing separator，含 test 的可运行套件因此被漏检。这里按顺序跟踪
    字面量 `.RECIPEPREFIX` 赋值并就地改写行首：当前前缀开头的行改成
    tab；前缀不是 tab 时，行首 tab 只是普通缩进，改成空格以免被误当
    recipe。只处理不含 `$` 的值；无法静态求值时保守保留原前缀。
    """
    lines = text.splitlines(keepends=True)
    out: List[str] = []
    prefix = "\t"
    value = ""
    value_simple = True
    # make 预定义了 .RECIPEPREFIX（空值），所以 `?=` 不会生效；只有
    # 显式 `undefine` 后才可能赋值，这里不跟踪该罕见写法。
    seen_assignment = True
    define_depth = 0
    conditional_depth = 0
    # 记录前面无条件的字面量赋值，供 `.RECIPEPREFIX = $(P)` 展开。
    # 只存不含 `$` 的值，避免在错误的时间展开延迟/递归变量。
    variables: Dict[str, str] = {}
    for line in lines:
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        if define_depth:
            if _MAKE_DEFINE_LINE.match(body) is not None:
                define_depth += 1
            elif _MAKE_ENDEF_LINE.match(body) is not None:
                define_depth -= 1
            out.append(line)
            continue
        if prefix != "\t" and body.startswith(prefix):
            # GNU make 只对默认 tab 前缀放过首个目标前的空/注释 recipe；
            # 自定义前缀的这类行仍报 recipe commences before first target。
            # 改写成非注释的 no-op，避免被首个目标前的空白规则误放行。
            rest = body[1:]
            if not rest.strip() or rest.lstrip(" \t").startswith("#"):
                out.append("\t:" + ending)
            else:
                out.append("\t" + rest + ending)
            continue
        if prefix != "\t" and body.startswith("\t"):
            out.append(" " + body[1:] + ending)
            continue
        if body.startswith("\t"):
            out.append(line)
            continue
        if _MAKE_DEFINE_LINE.match(body) is not None:
            define_depth = 1
            out.append(line)
            continue
        conditional = _MAKE_CONDITIONAL_LINE.match(body)
        if conditional is not None:
            if conditional.group(1) == "endif":
                if conditional_depth:
                    conditional_depth -= 1
            else:
                conditional_depth += 1
            out.append(line)
            continue
        match = _MAKE_RECIPE_PREFIX_ASSIGNMENT.match(body)
        if match is not None and conditional_depth == 0:
            op = match.group(1)
            raw = _make_strip_value_comment(match.group(2)).strip(" \t")
            # make 只在立即赋值（`:=`/`::=`）以及当前值是立即值时展开
            # 右侧；`=` 保留原文，`$(P)` 的首字符 `$` 本身就是 recipe
            # 前缀，不能提前展开成 P 的值。
            expand_raw = op in (":=", "::=", ":::=") or (
                op == "+=" and value_simple)
            if expand_raw and "$" in raw:
                expanded = raw
                for _ in range(20):
                    before = expanded
                    expanded = _make_expand_refs(
                        expanded, variables, {})
                    expanded = _make_expand_value(
                        expanded, variables, {})
                    if expanded == before:
                        break
                raw = expanded
            if op in ("=", ":=", "::=", ":::="):
                value = raw
                value_simple = op != "="
                seen_assignment = True
            elif op == "?=":
                if not seen_assignment:
                    value = raw
                    value_simple = True
                    seen_assignment = True
            elif op == "+=":
                value += raw
                seen_assignment = True
            prefix = value[0] if value else "\t"
        elif conditional_depth == 0:
            assignment = _MAKE_VAR_ASSIGNMENT.match(body)
            if assignment is not None:
                name, op, raw = assignment.groups()
                raw = _make_strip_value_comment(raw)
                if name != ".RECIPEPREFIX" and op != "!=" and "$" not in raw:
                    if op == "?=":
                        variables.setdefault(name, raw)
                    elif op == "+=":
                        old = variables.get(name)
                        if old is None:
                            variables[name] = raw
                        elif old and raw:
                            variables[name] = old + " " + raw
                        elif old:
                            variables[name] = old
                        else:
                            variables[name] = raw
                    else:
                        variables[name] = raw
        out.append(line)
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
            # 反斜杠不转义条件里的右括号：`ifeq (\,\)` 的两个值都是
            # 单个反斜杠，条件为真；跳过 `\)` 会找不到外层右括号。
            # 括号写法的参数边界只按圆括号配对，裸花括号不参与：
            # `ifeq ({a,b},{a,b})` 在逗号处分成 `{a` 与 `b},{a,b}`，条件
            # 为假，不能把花括号里的逗号当成嵌套。
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    close = i
                    break
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
            # 与参数边界一致，只有圆括号参与配对；`ifeq ({a,b},{a,b})`
            # 的第一个逗号在裸花括号内，仍是参数分隔符。
            if ch == "(":
                depth += 1
            elif ch == ")":
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


_MAKE_CONDITION_FUNCTIONS = frozenset({"if", "or", "and"})


def _make_find_condition_function(text: str, pos: int):
    """找下一个可静态求值的 if/or/and 调用，返回 (start, end, name, args)。"""
    i = pos
    while i + 1 < len(text):
        if text[i] == "$" and text[i + 1] == "$":
            i += 2
            continue
        if text[i] != "$" or text[i + 1] not in "({":
            i += 1
            continue
        opener = text[i + 1]
        closer = ")" if opener == "(" else "}"
        depth = 1
        k = i + 2
        while k < len(text):
            ch = text[k]
            # 引用只按与起始括号相同的字符配对；另一种括号嵌套
            #（`$(...${...}...)`）里的右括号仍会结束外层引用。
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if depth:
            return None
        j = i + 2
        while j < len(text) and (text[j].isalnum() or text[j] in "_-"):
            j += 1
        name = text[i + 2:j]
        if name in _MAKE_CONDITION_FUNCTIONS and (
                j >= len(text) or text[j] in " \t"):
            return i, k + 1, name, text[j:k].lstrip(" \t")
        if ((name == "foreach" or name == "call")
                and j < len(text) and text[j] in " \t"):
            # foreach 的循环变量、call 的参数变量在当前作用域里还不存在。
            # 不能先展开它们 body 里的 if/or/and：那会用外层变量表求值，
            # `$(foreach v,test,$(if $(v),test,y))` 会被误算成 y。交给
            # 对应的展开器绑定局部变量后再处理。只有函数名后紧跟空白才是
            # 调用；`$(call,...)` / `$(foreach,...)` 是普通变量引用，里面
            # 嵌套的 if/or/and 仍按 make 语义在变量名展开时求值。
            i = k + 1
            continue
        i += 1
    return None


def _make_split_all_function_args(args: str) -> List[str]:
    return _make_split_function_args(args, 1000000)


def _make_expand_condition_arg(
        text: str, variables: Dict[str, Optional[str]],
        simple: Dict[str, bool], repo: Optional[Path],
        depth: int, overrides: Optional[set] = None) -> Optional[str]:
    """展开条件函数的一个参数；仍有无法静态求值的引用时返回 None。"""
    value = text
    for _ in range(20):
        before = value
        value = _make_expand_automatic_refs(value)
        # 静态函数先于变量引用展开：参数边界按原文确定，变量展开为空后
        # 留下的空格可能属于参数值（`$(subst $x ,...)`），不能丢。
        if repo is not None:
            # 静态函数的参数错误（如 wordlist 非法下标）是读取期 fatal
            # 错误，即使在 if 条件里也必须向上抛；吞掉会把必然失败的
            # Makefile 误判成可运行套件。
            value = _make_expand_include_functions(
                value, repo, variables, simple, overrides)
        # value/foreach 必须在普通变量引用之前展开：foreach 的循环变量
        # 尚未绑定，先做引用展开会把 `$(foreach v,test,$(v))` 的循环体
        # 清空；value 返回的原始文本也不应被再次展开。
        value = _make_expand_value(value, variables, simple)
        # foreach 也必须等条件函数选中分支后再展开：它可能出现在 if 的
        # 条件里，先展开会把循环体产生的空白当成源码空白丢掉，改变
        # `$(if $(foreach x,test, ),then,else)` 的真假。
        value = _make_expand_foreach(value, variables, simple, repo)
        value = _make_expand_call_functions(
            value, variables, simple, repo, overrides)
        # eval 会在读取期立即展开参数并解析；条件参数里的
        # `$(eval x)` 会让 make 直接报 missing separator，不能当成
        # 未解析引用留给条件比较。
        value = _make_expand_eval_functions(
            value, variables, simple, repo, overrides)
        value = _make_expand_refs(value, variables, simple, repo=repo)
        # 先展开条件函数再展开静态函数：静态函数扫描会改写 if/or/and
        # 参数内部的内容，顺序反过来会让 `$(if cond,$(addsuffix ...))`
        # 的参数先在未判定分支时被展开，甚至把未生效分支的语法错误
        # 提前暴露出来。
        value = _make_expand_condition_functions(
            value, variables, simple, repo, depth + 1, overrides)
        value = _make_expand_metadata_functions(
            value, variables, simple, overrides)
        value = _make_expand_error_functions(value)
        value = _make_expand_side_effect_functions(
            value, variables, simple, repo, overrides)
        value = _make_expand_refs(value, variables, simple, repo=repo)
        if repo is not None:
            value = _make_expand_include_functions(
                value, repo, variables, simple, overrides)
        value = _make_expand_refs(value, variables, simple, repo=repo)
        if value == before:
            break
    if "$" in value.replace("$$", ""):
        return None
    return value


def _make_expand_condition_functions(
        text: str, variables: Dict[str, Optional[str]],
        simple: Dict[str, bool], repo: Optional[Path],
        depth: int = 0, overrides: Optional[set] = None) -> str:
    """展开条件里可静态求值的 `$(if ...)` / `$(or ...)` / `$(and ...)`。

    三个函数都短路：if 只展开生效分支，or 在第一个非空参数处停止，
    and 在第一个空参数处停止。未生效分支里的 shell/eval 等无法静态
    求值的调用不能连累整个表达式（make 本来也不会展开它们）。
    """
    if depth > 20 or "$(" not in text and "${" not in text:
        return text
    pos = 0
    while True:
        call = _make_find_condition_function(text, pos)
        if call is None:
            return text
        start, end, name, raw = call
        arity = 3 if name == "if" else 1000000
        parts = _make_split_function_args(raw, arity, text[start + 1])
        if name == "if" and len(parts) < 2:
            # `$(if x)` 只有一个参数时 make 报 insufficient number of
            # arguments 并停止解析，后面的 test 目标不会执行。参数不足
            # 必须在这里直接拒绝，保留原文会被后续展开当成非空变量名。
            raise _MakeRequiredIncludeError("if: missing argument")
        if name == "if":
            # 条件与 or/and 的参数原文空白由 make 的参数解析去掉；展开
            # 结果自身的空白属于值本身。then/else 连原文空白也保留。
            cond = _make_expand_condition_arg(
                parts[0].strip(" \t"), variables, simple, repo, depth,
                overrides)
            if cond is None:
                pos = end
                continue
            selected = parts[1] if cond else (
                parts[2] if len(parts) > 2 else "")
            result = _make_expand_condition_arg(
                selected, variables, simple, repo, depth, overrides)
            if result is None:
                pos = end
                continue
        elif name == "or":
            result = ""
            unresolved = False
            for part in parts:
                value = _make_expand_condition_arg(
                    part.strip(" \t"), variables, simple, repo, depth,
                    overrides)
                if value is None:
                    unresolved = True
                    break
                if value:
                    result = value
                    break
            if unresolved:
                pos = end
                continue
        else:  # and
            result = ""
            unresolved = False
            for part in parts:
                value = _make_expand_condition_arg(
                    part.strip(" \t"), variables, simple, repo, depth,
                    overrides)
                if value is None:
                    unresolved = True
                    break
                if not value:
                    result = ""
                    break
                result = value
            if unresolved:
                pos = end
                continue
        text = text[:start] + result + text[end:]
        pos = start + len(result)


def _make_expand_condition_text(text: str,
                                variables: Dict[str, Optional[str]],
                                simple: Dict[str, bool],
                                repo: Optional[Path],
                                overrides: Optional[set] = None) -> str:
    for _ in range(20):
        before = text
        text = _make_expand_automatic_refs(text)
        # 静态函数参数错误是 fatal 的，必须在 info/warning 被删掉之前
        # 检查：`ifeq ($(info $(word x,a b)),)` 不能当成空条件。
        if repo is not None:
            text = _make_expand_include_functions(
                text, repo, variables, simple, overrides)
        text = _make_expand_condition_functions(
            text, variables, simple, repo, overrides=overrides)
        # value/foreach 要先于普通引用展开，否则 foreach 循环变量会被
        # 当成外层未定义变量清空（`ifeq ($(foreach v,test,$(v)),test)`）。
        text = _make_expand_value(text, variables, simple)
        text = _make_expand_foreach(text, variables, simple, repo)
        text = _make_expand_refs(text, variables, simple, repo=repo)
        text = _make_expand_metadata_functions(
            text, variables, simple, overrides)
        text = _make_expand_error_functions(text)
        text = _make_expand_side_effect_functions(
            text, variables, simple, repo, overrides)
        text = _make_expand_call_functions(
            text, variables, simple, repo, overrides)
        # ifeq/ifneq 的比较值在读取期展开，其中的 eval 会先解析参数行；
        # `ifeq ($(eval x),a)` 里的 `x` 让 make 直接报 missing separator。
        text = _make_expand_eval_functions(
            text, variables, simple, repo, overrides)
        if repo is not None:
            text = _make_expand_include_functions(text, repo)
        if text == before:
            break
    return text


def _make_eval_condition(kind: str, rest: str,
                         variables: Dict[str, Optional[str]],
                         simple: Dict[str, bool],
                         repo: Optional[Path] = None,
                         overrides: Optional[set] = None) -> bool:
    # 条件行里的 # 注释与变量赋值同口径：奇数个反斜杠转义 #，偶数个
    # 开始注释。`ifeq ($(X),a\#b)` 的右值实际是 a#b（反斜杠被吃掉），
    # 不能按普通文本原样保留。
    rest = _make_strip_value_comment(rest).strip()
    if kind in ("ifdef", "ifndef"):
        name = _make_expand_condition_text(rest, variables, simple,
                                           repo, overrides).rstrip()
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
    left = _make_expand_condition_text(left, variables, simple, repo,
                                       overrides)
    right = _make_expand_condition_text(right, variables, simple, repo,
                                        overrides)
    # 括号写法的语法空白已在 _make_ifeq_args 里、变量展开前去掉；
    # 引号写法保留引号内的空白（ifeq "a " "a" 不相等）。
    equal = left == right
    return equal if kind == "ifeq" else not equal


def _make_apply_conditional(kind: str, rest: str, stack: List[dict],
                            variables: Dict[str, Optional[str]],
                            simple: Dict[str, bool],
                            repo: Optional[Path] = None,
                            overrides: Optional[set] = None) -> None:
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
                                            variables, simple, repo,
                                            overrides)
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
    cond = (_make_eval_condition(kind, rest, variables, simple, repo,
                                 overrides)
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
                             aliases: Optional[Dict[str, str]] = None,
                             overrides: Optional[set] = None) -> str:
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
    if overrides is None:
        overrides = set()
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
                # `define X = x` 只警告并定义 X，赋值符后的文本不是名称；
                # 运算符只认引用之外的那个。
                name_text, define_op = _make_define_header(
                    _make_strip_value_comment(
                        define_match.group(1) or ""))
                # 名称里的静态/条件/foreach/call/value/info 等函数同样
                # 会在读取期展开；`define $(strip )` / `define $(info x)`
                # 展开为空时 make 报 empty variable name，只展开普通引用
                # 会把函数原文当成非空名称，漏掉必然的读取失败。
                define_name = _make_expand_assignment_name(
                    name_text, variables, simple, repo, overrides)
                # 只有原始名称（或展开结果）为空才是空变量名；函数展开
                # 结果恰好以 `=` 等运算符开头（`define $(findstring =,a=b)`）
                # 时 make 会定义名为 `=` 的变量，不能误判成空名。名字里
                # 只剩未知引用（`define $(shell ...)`）时输出可能为空。
                if (not define_name.strip()
                        or _make_unknown_name_may_be_empty(define_name)):
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
                # define 定义的是递归变量，体里的换行原样保留。带
                # override 的 define 会锁定变量，之后普通 define/赋值
                # 不能覆盖它；普通 define 也不能覆盖已有的 override 变量。
                define_override = (
                    "override" in body[:body.find("define")].split())
                _make_apply_define(
                    define_name, define_op, "\n".join(body_lines),
                    variables, simple, overrides, define_override, repo)
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
                # 赋值运算符必须原样保留给第二遍：`define A ?=` 与
                # `define A` 在变量已定义时结果不同，丢掉 ?= 会让第二遍
                # 无条件覆盖，重新引入误报。
                op_suffix = "" if define_op == "=" else " " + define_op
                out.append(("override " if define_override else "")
                           + f"define {target_name}{op_suffix}\n")
                for body_line in body_lines:
                    out.append(body_line + "\n")
                out.append("endef\n")
            continue
        if active and _MAKE_ENDEF_LINE.match(body):
            # 生效分支里未处于 define 块中的 endef 是游离指令：make 报
            # missing separator 并停止解析。未生效分支里的 endef 会被
            # 直接忽略（不会报错），不能据此拒绝后面的 test 目标。
            # 但 `endef = x` 是普通变量赋值、`endef test:` 是目标列表，
            # 它们只在第一个词上碰巧叫 endef，make 不会当成指令。
            if (_MAKE_VAR_ASSIGNMENT.match(body) is None
                    and _make_unescaped_colon(body, 0) < 0):
                raise _MakeRequiredIncludeError("extraneous endef")
        conditional = _MAKE_CONDITIONAL_LINE.match(body)
        if conditional is not None:
            _make_apply_conditional(conditional.group(1),
                                    conditional.group(2) or "", stack,
                                    variables, simple, repo, overrides)
            i += 1
            continue
        if stack and not stack[-1]["active"]:
            i += 1
            continue
        # 行尾注释不是 eval 调用的一部分，但 eval 仍会在读取期展开；
        # `$(eval x) #c := $$` 的 `#` 之后是注释，`$(eval x)` 仍需执行。
        eval_args = _make_standalone_eval_args(
            _make_strip_comment(body))
        if eval_args is not None:
            # eval 的参数此刻已按读取期语义展开，随后才作为 Makefile
            # 行解析。必须在这里就地插入，让其中的 include 与条件指令
            # 走同一套处理：只留给第二遍展开会漏读 eval include 的
            # 目标，也会漏掉 `$(eval include missing.mk)` 这种必然
            # 让 make 失败的必需 include。
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            injected: List[str] = []
            for argument in eval_args:
                expanded_arg = _make_expand_condition_arg(
                    argument, variables, simple, repo, 0, overrides)
                if expanded_arg is None:
                    # 含 shell 等无法静态求值的引用：保留原文交给第二遍
                    # 的保守路径，不能猜它的展开结果。
                    expanded_arg = argument
                for eval_line in expanded_arg.splitlines():
                    injected.append(eval_line + newline)
            lines[i:i + 1] = injected + [_MAKE_CONTEXT_RESET + newline]
            continue
        include = _MAKE_INCLUDE_LINE.match(body)
        if include is not None and _MAKE_VAR_ASSIGNMENT.match(body) is not None:
            # `include =` / `include := x` 是名为 include 的普通变量赋值，
            # 不是 include 指令（-include/sinclude 同理）。按指令解析会把
            # 运算符当成必需文件名，误报缺失 include。
            include = None
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
            # include 参数与普通读取期文本一样会展开 value/foreach/call/
            # 条件/静态函数；只展开普通引用会把
            # `include $(foreach f,a.mk b.mk,$(f))` / `$(value FILES)` /
            # `$(call files)` 当成字面文件名，漏读真正的目标文件。
            # 与条件参数同一顺序，循环到不动点，避免嵌套函数残留。
            args = _make_strip_comment(include.group(2))
            for _ in range(20):
                before = args
                args = _make_expand_automatic_refs(args)
                # 静态函数要先于 info/warning 删除：make 会先展开函数
                # 参数再丢弃输出，`include $(info $(word x,a b))` 的
                # 非法下标仍是读取期 fatal 错误。
                args = _make_expand_include_functions(
                    args, repo, variables, simple, overrides)
                args = _make_expand_value(args, variables, simple)
                args = _make_expand_foreach(
                    args, variables, simple, repo)
                args = _make_expand_call_functions(
                    args, variables, simple, repo, overrides)
                args = _make_expand_refs(
                    args, variables, simple, repo=repo)
                args = _make_expand_condition_functions(
                    args, variables, simple, repo)
                args = _make_expand_metadata_functions(
                    args, variables, simple, overrides)
                args = _make_expand_error_functions(args)
                args = _make_expand_side_effect_functions(
                    args, variables, simple, repo, overrides)
                args = _make_expand_refs(
                    args, variables, simple, repo=repo)
                args = _make_expand_include_functions(
                    args, repo, variables, simple, overrides)
                args = _make_expand_refs(
                    args, variables, simple, repo=repo)
                if args == before:
                    break
            # include 指令本身会清空 make 的当前目标：被 include 文件开头
            # 的 tab 行、以及 include 之后紧跟的 tab 行都不是任何规则的
            # recipe。哨兵注释在展开阶段之后仍可被上下文检查识别。
            out.append(_MAKE_CONTEXT_RESET + "\n")
            for name in _make_include_names(args):
                display = _make_unescape_name(name)
                absolute_name = Path(display).is_absolute()
                for path in _make_include_paths(name, repo):
                    try:
                        key = path.resolve()
                        if key in seen:
                            continue
                        # 不能要求 is_file：`include /dev/null` 是常见
                        # 写法，字符设备可读且内容为空，make 正常接受。
                        # 限制读取长度，避免 /dev/zero、/dev/full 这类
                        # 无穷设备把探测卡死；普通大文件仍按 2MB 上限
                        # 跳过内容（只影响静态目标探测，不会执行它们）。
                        try:
                            if path.is_dir():
                                raise IsADirectoryError(str(path))
                            with path.open("rb") as handle:
                                raw = handle.read(2_000_001)
                        except OSError:
                            # make 对目录即使 -include 也报错；普通文件
                            # 缺失/权限不足时只有必需 include 才终止，
                            # -include / sinclude 按语义忽略。
                            if path.is_dir() or directive == "include":
                                raise _MakeRequiredIncludeError(display)
                            continue
                        if len(raw) > 2_000_000:
                            continue
                        included = raw.decode("utf-8-sig", errors="replace")
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
                            simple, aliases, overrides))
                        out.append("\n")
                    finally:
                        # 只把「正在处理」的文件留在 seen 里，防止 include
                        # 环无限递归；同一文件在前后两次 include 中仍应
                        # 按 make 语义各处理一次（条件分支可能因变量变化
                        # 而不同）。
                        seen.discard(key)
            out.append(_MAKE_CONTEXT_RESET + "\n")
            i += 1
            continue
        out.append(line)
        _make_scan_assignment(body, variables, simple, overrides, repo)
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
        # 嵌套模块是独立的包边界，父模块的 `go test ./...` 不会进入；
        # 只命中子模块时 go 会报 matched no packages 并以退出码 1 失败。
        current = Path(dirpath)
        if current != repo and (current / "go.mod").is_file():
            dirnames[:] = []
            continue
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
            text = _make_normalize_recipe_prefixes(text)
            if _make_has_missing_separator_line(text):
                return None
            if _make_has_bare_trailing_dollar_rule(text):
                return None
            text = _make_expand_simple_vars(text, repo)
            # 展开后的非规则行同样会在读取阶段报 missing separator
            #（`$(X) $(Y)` 这类变量组成的无冒号行），展开前扫描看不到。
            if _make_has_missing_separator_line(text, expanded=True):
                return None
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
