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
    """一次测试套件运行的结果。available=False 表示套件根本没能运行
    （运行时缺命令等），与「跑了但失败」（ok=False）必须区分：
    前者不能给候选下结论，只能转兜底评分或挂起。
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
})


def _is_pytest_file(name: str) -> bool:
    return (name.endswith(".py")
            and (name.startswith("test_") or name.endswith("_test.py")))


def _has_pytest_file(repo: Path) -> bool:
    for dirpath, dirnames, filenames in os.walk(repo):
        # 与 pytest 默认 norecursedirs 对齐：点目录、build/dist、虚拟环境
        # 和依赖目录不会被 `pytest -q` 收集，只按它们探测会得到「有测试
        # 套件」的假阳性，随后运行 pytest 以「未收集到测试」退出。
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in _PYTEST_SKIP_DIRS]
        if any(_is_pytest_file(name) for name in filenames):
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
    # 2) make test：Makefile 里定义了 test 目标。只认精确的 test 目标：
    #    test-unit / test-ci 之类后缀目标不算——探测命中后会执行
    #    `make test`，而 Makefile 里根本没有 test 目标时 make 以退出码 2
    #    失败，run_suite 会把它当成「测试失败」拒绝候选，连 auto 模式的
    #    兜底评分（user/ai）都被跳过；该场景应属「没有可运行套件」。
    #    变量赋值（test := / ?= / += / != / ::=）与 test: = x 这类空变量名
    #    同样不是目标：make test 会以退出码 2 失败，必须按无套件处理。
    #    负向前瞻吞掉冒号后任意个冒号再接 = 的写法（::= / :::=）。
    makefile = repo / "Makefile"
    if makefile.is_file() and shutil.which("make"):
        try:
            if re.search(r"(?m)^[ ]*test[ \t]*:(?![\t ]*:*=)",
                         makefile.read_text(encoding="utf-8", errors="replace")):
                return ["make", "test"]
        except OSError:
            pass
    # 3) npm test：package.json 声明了非占位的 test 脚本
    pkg = repo / "package.json"
    if pkg.is_file() and shutil.which("npm"):
        try:
            # JSON 合法但结构不对（顶层是 list、scripts 是 list/str 等）
            # 都按「没有 npm 套件」处理：这类脏数据不能把探测整个打断
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            scripts = data.get("scripts") if isinstance(data, dict) else None
            test_cmd = scripts.get("test") if isinstance(scripts, dict) else None
            if isinstance(test_cmd, str) and test_cmd.strip() \
                    and "no test specified" not in test_cmd:
                return ["npm", "test"]
        except (OSError, ValueError):
            pass
    # 4) go test：go.mod 模块下任意位置（根目录或 cmd/、internal/ 等
    #    子包）有 .go 文件。没有 go.mod 时不管 .go 在根目录还是子目录都
    #    不算：从仓库根执行 `go test ./...` 在模块模式下会因找不到 go.mod
    #    失败，探测成套件只会把「没有可用测试」误记成测试失败。
    if (shutil.which("go") and (repo / "go.mod").is_file()
            and any(p.is_file() for p in repo.rglob("*.go"))):
        return ["go", "test", "./..."]
    return None


# 套件停止轮询间隔：0.2s 足以让 TUI 的 q / Ctrl+C 及时兑现，又不空转 CPU
_SUITE_POLL_SECONDS = 0.2


def run_suite(argv: List[str], repo: Path, timeout: float,
              stop: Optional[Callable[[], bool]] = None) -> SuiteResult:
    """运行测试套件。退出码 0 = 通过；非 0 = 失败；超时 = 失败（保守：
    宁可不采纳候选，也不让超时的测试把可能损坏的产物放进最佳）。

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
        return SuiteResult(available=True, ok=True, reason="exit 0", detail=detail)
    tail = "\n".join(detail.splitlines()[-15:])
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
        # 本会话已计入 adopted 的候选 id。集合成员是计数是否生效的权威
        # 依据：中断可能落在「统计 +1」与「settled 标记」之间，单看 int
        # 无法区分是否已计入；_count_adopted 可据此幂等对账
        self._adopted_ids: set = set()
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

    def _recover_best(self) -> Dict:
        """best.md 存在但 best.json 缺失/损坏：恢复最佳元数据并回写。

        正常提交顺序下 best.json 先于 best.md 落盘（见 start/_commit_best），
        只有外部删除/损坏 best.json 才会出现该组合。优先从 history.jsonl 的
        最后一条基线/采纳事件重建（历史只读，不追加事件）；历史也不可用时
        按 best.md 合成一条基线并补记 baseline 事件。恢复结果回写 best.json，
        后续启动直接命中；写盘失败只告警（元数据在内存中已可用，守卫照常
        工作——降级原则）。
        """
        best: Optional[Dict] = None
        baseline_only = False
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
            # 历史行被外部编辑/其他工具写入时字段类型可能损坏（id 是列表、
            # round 是字符串、score 是文本……）：与 best.json 的加载校验
            # （_valid_best）用同一口径，类型不对的事件不能恢复成最佳
            # 元数据——否则回写的 best.json 下次启动仍会被拒绝，每次都走
            # 恢复分支；非字符串 id 还会让展示/事件关联出现异常值
            if not _valid_best(best):
                best = None  # 历史记录字段损坏：继续向前找
                continue
            break
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
        if baseline_only:
            self.sink.warn("rounds/best.json 与 history.jsonl 均不可用："
                           f"已按 best.md 重建基线最佳（{best['id']}）")
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
            # 从历史或 best.md 恢复，而不是把 best 永远停在 unknown
            self.best = loaded if loaded else self._recover_best()
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
                _atomic_write(self.best_json,
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

    def finish(self) -> None:
        try:
            self._apply_user_verdicts()
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            self.sink.warn(f"应用待决用户评分失败（忽略）：{e}")
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
            self.stats.rejected += 1
            self._settled_cids.add(cid)
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
            self.stats.rejected += 1
            self._settled_cids.add(cid)
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
        self.stats.pending += 1
        self._pending_ids.add(cid)
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

    def _count_adopted(self, cid: str) -> None:
        """把候选计入 adopted；集合成员是幂等对账的提交点。"""
        self._adopted_ids.add(cid)
        self.stats.adopted = len(self._adopted_ids)
        self._settled_cids.add(cid)

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
                       f"（改动区块：{'、'.join(changed)}）；"
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
            if cid in self._pending_ids:
                self._pending_ids.discard(cid)
                self.stats.pending -= 1
            if adopted:
                self.best = best
                self._count_adopted(cid)
            else:
                self.stats.rejected += 1
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
