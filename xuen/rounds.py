"""轮次守卫（round guard）：每轮快照、候选/最佳分离、自动验证与评分。

背景：xuen 的研究循环里，外部 agent 每轮【整体覆盖】想法区/产物区，
下一轮无条件继承最新状态——一旦某轮产出了更差的方案，更好的前一轮
结果就被静默覆盖丢失。本模块在不改变循环主体的前提下加一道守卫：

  每轮结束
    │
    ├─ 无改动 → 记「心跳」，不产生候选
    ├─ 结构损坏（区块标记缺失）→ 直接拒绝，还原最佳
    ├─ 有改动 → 快照为候选 rounds/cand-<id>.md（候选 ≠ 最佳）
    │        │
    │        ├─ 验证（rounds.verify）：
    │        │    auto  有可运行测试套件就跑测试；没有则用 fallback
    │        │    tests 只跑测试（pytest → make → npm → go 级联）
    │        │    user  用户在 rounds/verdicts.txt 里异步评分
    │        │    ai    复用外部 agent 当评审员打分（可配便宜模型）
    │        │    off   不验证，最新即最佳（退化为「防丢失」模式）
    │        │
    │        ├─ 通过（测试全绿 / 评分 >= adopt_score）→ 前进式晋升为最佳
    │        │    （best.json 元数据 + best.md 镜像；不改写任何历史记录）
    │        └─ 失败 / 挂起 → research.md 还原为当前最佳
    │             —— 下一轮【永远从最佳出发】，更差的候选无法污染后续轮次
    │
    └─ 全部事件追加进 rounds/history.jsonl（审计用，只增不改）

实现上刻意保持简单的三个设计决定：

  * **内容权威单一**：每次晋升的最佳都有内容完全相同的候选快照
    （cand-<id>.md）；best.md 只是给人看 / 供 git diff 的镜像。读取
    最佳内容时先找快照、快照丢了才退回镜像，镜像损坏也不影响判定——
    因此落盘顺序不需要精心编排，也不需要「写一半回滚」的补偿逻辑。
  * **Makefile 不做静态解析**：Makefile 是否定义了 test 目标（写在
    ifeq 分支里、include 进来、eval 生成、模式规则……）由 GNU make
    自己在运行时回答；run_suite 把「No rule to make target 'test'」
    「Nothing to be done for 'test'」解释成「套件不可用」。静态解析
    数千行也回答不了的问题，交给 make 一条命令。
  * **守卫异常一律降级**：守卫自身出错（目录不可写、评审员崩了、
    评分解析不出……）最多丢当轮结论、挂起候选，绝不阻断研究循环；
    已落盘的最佳状态不会被破坏。

用户评分协议（非交互，兼容 CI / 后台循环）：
  在 <workspace>/rounds/verdicts.txt 里追加一行：
      <候选id> <0-10 分> [评语]
  例如： 20261017-031037-r5 8 想法区更有深度，产物区伪代码可落地
  守卫在每轮结束 / start / finish 时兑现待决评分：给旧候选补分并达到
  阈值时，该候选被「前进式」晋升为最佳并写回 research.md（等价于回滚
  到它，但不改写任何历史记录）；低于阈值则记为拒绝。
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
    # 前置负向断言：score 不能粘在英文单词尾部（「prescore: 3」里的
    # score 只是单词后缀，不是评分标签）
    re.compile(r"(?<![A-Za-z])score\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)",
               re.IGNORECASE),
)


# ----------------------------------------------------------------------
# 小工具
def _atomic_write(path: Path, text: str) -> None:
    """tmp + os.replace 原子写：读端永远不会看到半截文件。

    tmp 名带 PID：同一 workspace 并发运行两个 xuen 实例时，固定名 .tmp
    会被两边交错写入，os.replace 随后把撕裂内容发布成有效的
    best.json / best.md。"""
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
    成 True，`True > 0` 虽不报错但语义错误）。"""
    return isinstance(value, int) and not isinstance(value, bool)


_CID_RE = re.compile(r"[A-Za-z0-9_-]+\Z")


def _valid_cid(value: object) -> bool:
    """候选 id 是否可安全拼进快照文件名 `rounds/cand-<id>.md`。

    生成侧只会产出 [0-9A-Za-z_-]，但 best.json / history.jsonl /
    verdicts.txt 可能被外部编辑：id 含 NUL 或路径分隔符时拼出的路径会
    抛 ValueError 或越出 rounds 目录。凡不满足安全字符集的 id 一律按
    损坏元数据处理，绝不用它拼路径——守卫的降级原则要求损坏文件最多
    丢一次恢复机会，不能把整个守卫炸掉。"""
    return isinstance(value, str) and _CID_RE.match(value) is not None


def _valid_best(data: object) -> bool:
    """best.json 的最小字段校验：id 为可作文件名的安全字符串、round 为
    真整数、score 为 None 或有限数值（NaN/inf 会让评分比较与 `:g`
    格式化失效）。"""
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
            if not math.isfinite(float(score)):
                return False
        except (OverflowError, ValueError):
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

    区分 None 与 ""：还原时直接比较会把「文件损坏但最佳区块也为空」
    误判成「无需还原」，research.md 的标记就永远修不回来。

    内容按写入规整形态返回（见 state.sanitize_section_content）：还原 /
    补评写回时 update_section_file 会剥掉内容里独占一行的区块标记
    字面量，比较时必须用同一形态，否则含标记字面量的最佳内容与磁盘上
    规整后的内容永远不相等——每轮都会误判为「仍有差异」并重复还原。"""
    if not text:
        return None
    content = state._first_section(text, name)
    if content is None:
        return None
    return state.sanitize_section_content(content)


def _structure_intact(text: str) -> bool:
    """两个区块的标记是否都能安全读出（见 state._first_section）。

    候选内容进入最佳前的最后一道结构闸门：快照落盘后可能被外部截断 /
    篡改（写盘中途崩溃、用户误编辑、并发实例），损坏内容绝不能进
    best.md，否则下一次还原会把空区块写回 research.md，静默丢掉当前
    最佳（「结构损坏不得进最佳」的核心不变量）。"""
    if not text:
        return False
    return (state._first_section(text, state.SECTION_IDEA) is not None
            and state._first_section(text, state.SECTION_ARTIFACT) is not None)


@dataclass
class SuiteResult:
    """一次测试套件运行的结果。available=False 表示套件没有可用的验证
    结论（运行时缺命令、pytest 未收集到测试、make 没有 test 目标……），
    与「跑了但失败」（ok=False）必须区分：前者不能给候选下结论，只能
    转兜底评分或挂起。stopped=True 表示运行被用户主动停止（TUI 按
    q / Ctrl+C）：套件已被整组终止，调用方不能再拉起兜底评审。"""
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
# 按它们探测会误判「本仓库有测试套件」，随后 pytest 从仓库根收集这些
# 文件，既慢又可能因第三方测试失败而拒绝所有候选。
_PYTEST_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", ".tox", ".nox", ".venv", "venv", ".env",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "build", "dist", "CVS", "_darcs", "{arch}",
})


def _is_pytest_file(name: str) -> bool:
    return (name.endswith(".py")
            and (name.startswith("test_") or name.endswith("_test.py")))


def _has_pytest_file(repo: Path) -> bool:
    for dirpath, dirnames, filenames in os.walk(repo):
        # 与 pytest 默认 norecursedirs 对齐：点目录、build/dist、虚拟环境、
        # 依赖目录与 *.egg 安装产物不会被 `pytest -q` 收集，只按它们探测
        # 会得到「有测试套件」的假阳性，随后 pytest 以退出码 5「无测试可
        # 收集」结束——那不是测试失败。
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in _PYTEST_SKIP_DIRS
            and not d.endswith(".egg")
        ]
        if any(_is_pytest_file(name) for name in filenames):
            return True
    return False


def _has_go_package(repo: Path) -> bool:
    """模块内是否有 `go test ./...` 会匹配到的 .go 文件。

    与 go 工具的忽略规则对齐：以 . 或 _ 开头的目录/文件名、testdata
    目录、任意层级的 vendor 目录都不会被 `./...` 匹配；嵌套模块
    （子目录有自己的 go.mod）是独立包边界。只命中这些位置的仓库会以
    「matched no packages」失败——不能探测成套件。"""
    for dirpath, dirnames, filenames in os.walk(repo):
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

    Makefile 分支【只看文件存在，不解析内容】：Makefile 是否定义了
    test 目标（写在 ifeq 分支里、include 进来、eval 生成、模式规则、
    grouped targets……）由 GNU make 自己在运行时回答——run_suite 会把
    「No rule to make target 'test'」「Nothing to be done for 'test'」
    解释成「套件不可用」，而不是测试失败。静态解析数千行 Makefile
    也回答不了的问题，交给 make 一条命令。"""
    if not repo.is_dir():
        return None
    # 1) pytest：仓库任意子目录有 test_*.py / *_test.py，且本机装了 pytest
    if _has_pytest_file(repo) and _find_spec("pytest"):
        return [sys.executable, "-m", "pytest", "-q"]
    # 2) make test：存在 Makefile。GNU make 按 GNUmakefile → makefile →
    #    Makefile 的顺序取第一个存在的文件（目录/悬空符号链接也算被
    #    选中，make 会以退出码 2 失败——按无套件处理）。
    makefile = next(
        (repo / name for name in ("GNUmakefile", "makefile", "Makefile")
         if os.path.lexists(repo / name)), None)
    if (makefile is not None and makefile.is_file()
            and shutil.which("make")):
        return ["make", "test"]
    # 3) npm test：package.json 声明了非占位的 test 脚本。用 which 解析
    #    出的完整路径而不是裸 "npm"：Windows 上 npm 实际是 npm.cmd，
    #    裸 "npm" 会以 WinError 2 启动失败。
    pkg = repo / "package.json"
    npm = shutil.which("npm") if pkg.is_file() else None
    if npm:
        try:
            # JSON 合法但结构不对（顶层 list、scripts 是 list/str 等）都按
            # 「没有 npm 套件」处理；utf-8-sig：npm 忽略 BOM，照常执行
            data = json.loads(pkg.read_text(encoding="utf-8-sig",
                                            errors="replace"))
            scripts = data.get("scripts") if isinstance(data, dict) else None
            test_cmd = scripts.get("test") if isinstance(scripts, dict) else None
            if isinstance(test_cmd, str) and test_cmd.strip() \
                    and "no test specified" not in test_cmd:
                return [npm, "test"]
        except (OSError, ValueError):
            pass
    # 4) go test：go.mod 模块下有 go 工具会匹配的 .go 文件。没有 go.mod
    #    时不管 .go 在哪都不算：`go test ./...` 在模块模式下会因找不到
    #    go.mod 失败。
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
    """argv 是否为本模块探测出的 go test 调用（go test ./...）。

    与 _is_make_test_run 同口径按 basename 判断：探测返回的是裸 "go"，
    但 Windows 上是 go.exe，测试接缝也可能传完整路径。"""
    return (len(argv) >= 2 and argv[1] == "test"
            and os.path.basename(argv[0]).lower() in ("go", "go.exe"))


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

    Makefile 的 test 目标写在 ifeq/ifdef 等条件分支里、而当前环境走的
    正是另一支时，`make test` 以退出码 2 报「No rule to make target
    'test'」。这与「make test 跑了但命令失败」同码，不能按测试失败
    拒绝候选——按套件不可用处理。只匹配目标名为 test 的报错。"""
    return _MAKE_MISSING_TEST_TARGET.search(detail) is not None


# 只认顶层 make（不带 [n] 前缀）：子 make 无事可做不代表外层没跑测试。
_MAKE_NOOP_TEST_TARGET = re.compile(
    r"(?m)^(?:make|gmake)(?:\.exe)?: "
    r"(?:Nothing to be done for [`'\"]test[`'\"]\.|"
    r"[`'\"]test[`'\"] is up to date\.)[ \t]*$")


def _make_noop_test_target(detail: str) -> bool:
    """make test 是否退出 0 但根本没有执行测试。

    空的 `test:` 目标、已存在的同名文件/目录都会让 make 以 0 退出并打印
    「Nothing to be done for 'test'」/「'test' is up to date」。这不是
    「测试全部通过」：未验证的候选会被直接采纳。按套件不可用处理，与
    pytest 退出码 5、go 全部 [no test files] 同口径。"""
    return _MAKE_NOOP_TEST_TARGET.search(detail) is not None


def _go_matched_no_packages(detail: str) -> bool:
    """go test 是否「没有匹配到任何包」（构建约束排除了全部包）。"""
    return ("matched no packages" in detail
            and "no packages to test" in detail)


_GO_NO_TEST_FILES_LINE = re.compile(
    r"^\?\s+\S+\s+\[no test files\]\s*$", re.MULTILINE)


def _go_no_tests_ran(detail: str) -> bool:
    """go test 是否一个测试都没跑（所有包都 [no test files] 且无 ok/FAIL）。

    与 pytest 退出码 5 同义：编译通过不等于测试验证，不能当成「测试
    全部通过」；混有真实测试的模块会打印 ok 行，不受影响。"""
    if not _GO_NO_TEST_FILES_LINE.search(detail):
        return False
    return not re.search(r"^(?:ok|FAIL)[ \t]", detail, re.MULTILINE)


def run_suite(argv: List[str], repo: Path, timeout: float,
              stop: Optional[Callable[[], bool]] = None) -> SuiteResult:
    """运行测试套件。退出码 0 = 通过；非 0 = 失败；超时 = 失败（保守：
    宁可不采纳候选，也不让超时的测试把可能损坏的产物放进最佳）。

    「没有可执行的验证」按套件不可用返回（available=False），不拒绝
    候选：pytest 退出码 5（未收集到测试）、go 的「matched no packages」
    与「全部包 [no test files]」、make 的「No rule to make target
    'test'」与「Nothing to be done」。

    stop：可选的「是否请求停止」回调。传入时按短间隔轮询，回调一旦为
    真就终止整个进程组并返回 stopped=True——TUI 里按 q / Ctrl+C 时若
    守卫正阻塞在套件上，用户主动退出才不会被误报成退出码 1。

    与 subprocess.run 的差异：自己拉起进程并借 procs.kill_process_tree
    整组终止，测试拉起的子孙进程不会泄漏；KeyboardInterrupt 等
    BaseException 也先收尾再传播。"""
    if stop is not None and stop():
        return SuiteResult(available=False, stopped=True,
                           reason="用户请求停止，未验证")
    # make 的诊断文本随 locale 变化（中文环境是「无需做任何事」），而
    # 判定正则按英文 GNU make 输出。只对 make 固定 C locale；pytest/
    # npm/go 仍继承用户 locale。
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
            # stdin 读键盘，测试套件若也读 stdin 会抢键。
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
                # communicate 在 TimeoutExpired 后可安全重试，输出不丢
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
        kill_process_tree(proc)
        _reap_suite(proc)
        raise
    if stopped:
        return SuiteResult(available=False, stopped=True,
                           reason="用户请求停止，未验证")
    detail = (out or "").strip()
    if proc.returncode == 0:
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
        return SuiteResult(available=False, ok=False,
                           reason="pytest 未收集到测试（退出码 5）",
                           detail=tail)
    if _is_go_test_run(argv) and _go_matched_no_packages(detail):
        return SuiteResult(available=False, ok=False,
                           reason="go 未匹配到任何包",
                           detail=tail)
    if _is_make_test_run(argv) and _make_missing_test_target(detail):
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
        self.best: Dict = {}
        self.stats = _Stats()
        self._suite_runner = suite_runner
        self._judge_override = judge
        # 本轮已快照、但还没有终结结论（adopted/rejected/pending）的候选
        # id：on_round_end 的异常路径据此把「已落盘但未定论」的候选挂起，
        # 汇总不会出现「候选 1、三个结论桶全 0」的自相矛盾
        self._round_cid: Optional[str] = None
        # 本会话挂起、可被 verdicts.txt 补分翻案的候选（pending 计数的
        # 唯一来源：补分兑现后从这里移走，统计与晋升日志保持一致）
        self._pending_ids: set = set()
        # 本会话已兑现的 verdicts 行（内存集合与事件写盘解耦：事件写盘
        # 失败时同一行评分也不会被下一次兑现重复应用）
        self._applied: set = set()
        # 本会话内已处理（完成或按失败记账）的轮次：KeyboardInterrupt
        # 可能晚于 on_round_end 到达，on_round_failed 再记一遍会让轮次
        # 数/跳过数虚增、审计日志为同一轮记出自相矛盾的事件
        self._handled_rounds: set = set()
        self._hinted = False  # 「如何评分」提示只打印一次
        self._warned_unknown: set = set()   # 未知候选 id：只警告一次
        self._warned_badscore: set = set()  # 评分解析不出：只警告一次

    # ---- 基础设施 ----
    def _append_event(self, ev: Dict) -> None:
        ev = dict(ev)
        ev.setdefault("ts", _ts())
        line = json.dumps(ev, ensure_ascii=False) + "\n"
        # 追加前确保文件以换行结尾：上一次写入若在 ENOSPC / 进程被杀时
        # 中途截断，残行会与新事件拼成一行、两条都解析失败（历史是
        # _apply_user_verdicts 的已决判定与最佳恢复的来源）。补一个换行
        # 让残行独立成行，新事件照常可读。
        with open(self.history_path, "a+b") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.seek(0, os.SEEK_END)
                    f.write(b"\n")
            f.write(line.encode("utf-8"))

    def _append_event_safe(self, ev: Dict) -> None:
        """审计事件追加；写盘失败只告警——判定/还原已生效，历史只影响
        审计。已决判定（adopted/rejected）的事件缺失时用内存集合
        _applied 兜底去重，同一评分不会被重复兑现。"""
        try:
            self._append_event(ev)
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            try:
                self.sink.warn(f"记录 {ev.get('event', '?')} 事件失败（忽略）：{e}")
            except Exception:  # noqa: BLE001
                pass
            if (ev.get("event") == "verdict"
                    and ev.get("result") in ("adopted", "rejected")
                    and _valid_cid(ev.get("id"))):
                self._applied.add(ev.get("id"))

    def _read_events(self) -> List[Dict]:
        events: List[Dict] = []
        try:
            raw = self.history_path.read_bytes()
        except OSError:
            return events
        # 坏行跳过（写盘中途被杀/磁盘满留下的半截行）：审计日志绝不因为
        # 个别损坏行整体不可读。只按 ASCII 换行切分（str.splitlines 还会
        # 在 U+2028 等 Unicode 行分隔符处切开，任务名/评语里含这些字符
        # 时一条合法 JSON 事件会被拆成两半并整体丢失）。
        for line in re.split(r"\r\n|\r|\n",
                             raw.decode("utf-8-sig", errors="replace")):
            line = line.strip().lstrip("\ufeff").strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict):
                events.append(ev)
        return events

    def _load_best(self) -> Dict:
        """读取 best.json；缺失/损坏/字段不合法（见 _valid_best）返回 {}。"""
        try:
            data = json.loads(self.best_json.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}
        return data if _valid_best(data) else {}

    def _best_from_history(self, *, require_snapshot: bool = False) -> Optional[Dict]:
        """从 history.jsonl 最后一条基线/采纳事件恢复最佳元数据。

        历史行被外部编辑时字段类型可能损坏：与 best.json 的加载校验
        （_valid_best）用同一口径。require_snapshot=True 时只返回候选
        快照仍完整可读的最佳（内容权威在快照，只有元数据没有意义）。"""
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
            if require_snapshot and self._snapshot_text(best.get("id")) is None:
                continue
            return best
        return None

    def _snapshot_text(self, cid: object) -> Optional[str]:
        """候选快照内容；id 非法 / 不可读 / 结构损坏返回 None。

        每个晋升过的最佳都有内容完全相同的快照（_adopt 与补评晋升写的
        是同一份被验证内容）——快照是最佳内容的权威来源。"""
        if not _valid_cid(cid):
            return None
        try:
            text = (self.dir / f"{CAND_PREFIX}{cid}.md").read_text(
                encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        return text if _structure_intact(text) else None

    def _mirror_text(self) -> Optional[str]:
        """best.md 镜像内容；缺失/损坏返回 None（绝不把损坏内容当最佳）。"""
        try:
            text = self.best_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        return text if _structure_intact(text) else None

    def _best_content(self) -> str:
        """当前最佳内容（心跳比较 / 还原 / 评审提示词）。

        权威来源是最佳对应的候选快照；基线没有快照，退回 best.md 镜像；
        两者都拿不到时退回脚手架，绝不把损坏内容当最佳写回 research.md。"""
        text = self._snapshot_text(self.best.get("id"))
        if text is not None:
            return text
        mirror = self._mirror_text()
        return mirror if mirror is not None else state.scaffold(self.task)

    def _heal_mirror(self, text: str) -> None:
        """镜像与权威内容不一致时回写（自愈；失败只告警不阻断）。"""
        try:
            if self._mirror_text() != text:
                _atomic_write(self.best_md, text)
        except OSError as e:
            self.sink.warn(f"best.md 镜像写盘失败（忽略）：{e}")

    def _read_state_text(self) -> str:
        try:
            # state.read_state_file 与其它读路径同一自愈口径：非法 UTF-8
            # 按替换符降级并回写修复。只有真正读不到（文件缺失/权限）才
            # 返回 "" 走 skipped——候选快照不留、产物丢失，违反「任何
            # 一轮的产物都落在 rounds/cand-<id>.md」的承诺。
            return state.read_state_file(self.state_path)
        except OSError:
            return ""

    def _sections(self, text: str) -> Tuple[str, str]:
        # 取「写入规整形态」：心跳/改动判定必须与 update_section_file
        # 落盘后的可读内容一致（见 _readable_section）
        return (state.sanitize_section_content(
                    state.get_section(text, state.SECTION_IDEA)),
                state.sanitize_section_content(
                    state.get_section(text, state.SECTION_ARTIFACT)))

    def _snapshot_candidate(self, round_no: int, text: str) -> str:
        """原子创建候选快照，返回实际占用的 id（撞车自动追加序号）。

        O_CREAT|O_EXCL 把「检查 + 占用」合并为一个原子操作：同一
        workspace 的两个实例同一秒、同一轮号也不会互相覆盖快照——候选
        快照是被拒/挂起候选事后在 verdicts.txt 翻案的唯凭据。写入失败
        时删除半截文件再传播。"""
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
        # ① 元数据：best.json 优先；缺失/损坏时从 history.jsonl 恢复
        #    （要求快照仍可读——内容权威在快照，只有元数据没有意义）
        self.best = (self._load_best()
                     or self._best_from_history(require_snapshot=True)
                     or {})
        # ② 内容：采纳过的最佳 → 其快照；基线（无快照）→ best.md 镜像
        content = self._snapshot_text(self.best.get("id"))
        if content is None:
            content = self._mirror_text()
        if self.best and content is not None:
            # 已有最佳：对齐镜像（自愈），进入正常循环
            self._heal_mirror(content)
        else:
            # 首次运行 / 元数据与内容全部丢失：把当前内容固化为基线最佳。
            # 元数据全丢但镜像还在时以镜像为基线内容（不把可能未验证的
            # 当前状态悄悄固化成基线）；镜像也丢才用当前 research.md。
            # 有了基线，「第 1 轮候选被拒绝时还原到什么」才有明确答案。
            text = (self._mirror_text() or self._read_state_text()
                    or state.scaffold(self.task))
            self.best = {"id": f"baseline-{time.strftime('%Y%m%d-%H%M%S')}",
                         "round": 0, "verifier": "baseline", "score": None,
                         "ts": _ts()}
            # best.json 先、best.md 后：best.md 是「基线已建立」的存在
            # 标志，必须最后落盘。反序会留下没有元数据的 best.md——
            # 下次启动读到未知 id，基线事件也永远不会补记。
            self._commit_best(text, self.best)
            self._append_event_safe({"event": "baseline", **self.best})
            self.sink.ok(f"轮次守卫：建立基线最佳 {self.best['id']}")
        self.sink.info(
            f"轮次守卫已启用：{self.dir}（每轮快照；候选需验证通过才晋升为最佳；"
            f"verify={self.cfg.rounds.verify}"
            + (f"，兜底评分={self.cfg.rounds.fallback}"
               if self.cfg.rounds.verify == "auto" else "")
            + "）")
        self._cash_verdicts_safe()
        # 进程可能在轮次中途被 kill/断电：research.md 已留下未验证内容，
        # 而 best 仍是上一个已提交最佳。启动时必须先把「当前状态」拨回
        # 最佳，否则下一轮 agent 会从半截内容继续。补分兑现可能刚把新
        # 最佳写回 research.md，故放在其后；内容一致时 _restore_best 是
        # 空操作，不会产生事件或虚增还原统计。
        try:
            self._restore_best(0, "启动时还原未完成轮次")
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            self.sink.warn(f"启动时还原最佳失败（忽略）：{e}")

    def finish(self) -> None:
        self._cash_verdicts_safe()
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
        """agent 启动/执行失败的轮次：不留候选（半截产物不可信），仅记账
        并还原最佳——失败轮次的半截产物同样不能污染下一轮的起点。

        中断（KeyboardInterrupt）可能晚于 on_round_end 到达：该轮已按
        完成轮次产出候选/心跳/判定，此时只补做一次「还原最佳」（通常
        是无变化的空操作），不再追加任何记账。"""
        if round_no in self._handled_rounds:
            self._restore_best(round_no, why=f"轮次失败（{reason}）")
            return
        self._handled_rounds.add(round_no)
        self.stats.rounds += 1
        self.stats.skipped += 1
        self._append_event_safe({"event": "skipped", "round": round_no,
                                 "reason": reason})
        self._restore_best(round_no, why=f"轮次失败（{reason}）")

    # ---- 每轮守卫主流程 ----
    def on_round_end(self, round_no: int) -> str:
        """一轮 agent 成功结束后调用；返回 adopted / rejected / pending /
        heartbeat / skipped 供调用方与测试断言。

        本轮判定完成后兑现一次待决用户评分（与 start/finish 同一通道）。
        「每轮结束时兑现」不能只落在会话首尾：`iterations: inf` 的长循环
        里用户补分将永远等不到兑现，后续轮次也不会从重新采纳的最佳
        继续。必须放在本轮快照与判定【之后】：提前兑现会先把旧候选写
        回 research.md，覆盖掉 agent 刚产出、尚未快照的本轮内容。"""
        self._handled_rounds.add(round_no)
        self.stats.rounds += 1
        self._round_cid = None
        try:
            result = self._round_end(round_no)
        except KeyboardInterrupt:
            # 中断轮次：候选已快照但无结论 → 挂起（不写 verdict 事件——
            # 不能把中断伪装成已决），还原最佳后向上传播
            cid = self._round_cid
            if cid is not None:
                self._pend(round_no, cid, "轮次被中断，候选挂起")
            else:
                self._restore_best(round_no, "轮次被中断")
            raise
        except Exception as e:  # noqa: BLE001 —— 守卫降级 + 统计一致
            # 验证/晋升/写盘失败：候选已快照 → 挂起（用户补分/重试仍可
            # 翻案）；快照都没成功 → 按跳过记账。绝不能只把异常抛给
            # runner——未计入结论桶的候选会让汇总自相矛盾
            cid = self._round_cid
            if cid is not None:
                self._append_event_safe(
                    {"event": "verdict", "id": cid, "round": round_no,
                     "verifier": "guard", "result": "pending", "score": None,
                     "reason": f"验证或晋升失败（{e}），候选挂起等待重试"})
                self._pend(round_no, cid, "验证或晋升失败，候选挂起")
            else:
                self.stats.skipped += 1
                self._append_event_safe(
                    {"event": "skipped", "round": round_no,
                     "reason": f"候选快照写盘失败：{e}"})
                self._restore_best(round_no, "候选快照写盘失败")
            raise
        finally:
            self._round_cid = None
        self._cash_verdicts_safe()
        return result

    def _round_end(self, round_no: int) -> str:
        text = self._read_state_text()
        if not text:
            # research.md 整个没了：没法当候选，也别让下一轮拿到空状态
            self.stats.skipped += 1
            self._append_event_safe({"event": "skipped", "round": round_no,
                                     "reason": "状态文件缺失或不可读"})
            self._restore_best(round_no, why="状态文件缺失")
            return "skipped"

        # 1) 结构检查：区块标记被外部 agent 弄坏的内容无法被安全读取，
        #    更不能进最佳——结构损坏直接拒绝（守卫级判定，无需测试/评分）
        if not _structure_intact(text):
            cid = self._snapshot_candidate(round_no, text)  # 损坏内容也留档
            self.stats.candidates += 1
            verdict = Verdict(verifier="guard", result="rejected",
                              reason="区块标记缺失或损坏，无法安全读取")
            self._append_event_safe({"event": "candidate", "id": cid,
                                     "round": round_no, "corrupt": True})
            self._append_event_safe({"event": "verdict", "id": cid,
                                     "round": round_no,
                                     **_verdict_fields(verdict)})
            self._applied.add(cid)
            self.stats.rejected += 1
            self.sink.err(f"候选 {cid} 被守卫拒绝：{verdict.reason}，已还原最佳")
            self._restore_best(round_no, why="结构损坏")
            return "rejected"

        # 2) 无改动 → 心跳（不产生候选，避免无意义快照淹没真正的轮次）
        cand_idea, cand_artifact = self._sections(text)
        best_idea, best_artifact = self._sections(self._best_content())
        if (cand_idea, cand_artifact) == (best_idea, best_artifact):
            self.stats.heartbeat += 1
            self._append_event_safe({"event": "heartbeat", "round": round_no})
            return "heartbeat"

        # 3) 有改动 → 候选快照（先落盘：无论后续验证成败，本轮产物都不丢）
        cid = self._snapshot_candidate(round_no, text)
        self.stats.candidates += 1
        self._round_cid = cid
        changed = [n for n, (c, b) in {
            "idea": (cand_idea, best_idea),
            "artifact": (cand_artifact, best_artifact),
        }.items() if c != b]
        self._append_event_safe({"event": "candidate", "id": cid,
                                 "round": round_no, "changed": changed})
        self.sink.info(f"候选快照：{CAND_PREFIX}{cid}.md"
                       "（尚未验证，不代表最佳）")

        # 4) 验证 → 晋升 / 拒绝 / 挂起
        verdict = self._verify(round_no, cid)
        if verdict.result == "adopted":
            # 先完成外部副作用（best.json / best.md 写盘）再记已决事件：
            # 写盘失败（磁盘满 / 目录只读）时保持「未决」——先记一条
            # adopted 会让补分通道永久跳过该候选，用户腾出磁盘后也再
            # 翻不了案
            self._adopt(cid, round_no, verdict)
            self._round_cid = None
            self._applied.add(cid)
            self._append_event_safe({"event": "verdict", "id": cid,
                                     "round": round_no,
                                     **_verdict_fields(verdict)})
            return "adopted"
        self._append_event_safe({"event": "verdict", "id": cid,
                                 "round": round_no, **_verdict_fields(verdict)})
        if verdict.result == "rejected":
            self._round_cid = None
            self._applied.add(cid)
            self.stats.rejected += 1
            self.sink.warn(f"候选 {cid} 未通过（{verdesc(verdict)}），"
                           f"保留最佳并还原")
            self._restore_best(round_no, why="候选被拒绝")
            return "rejected"
        # pending：候选等用户/后续补分（挂起不是终局判定，用户之后补分
        # 仍需能翻案，所以不进 _applied）
        self._pend(round_no, cid, "候选待评分")
        return "pending"

    def _pend(self, round_no: int, cid: str, why: str) -> None:
        """把候选计入「待评分」：还原最佳并提示用户评分方式。

        正常挂起（评审无结论）与验证/晋升失败共用此记账口径：候选快照
        都已落盘，统计必须与之一一对应，否则汇总自相矛盾、待评分候选
        数失真。"""
        self._pending_ids.add(cid)
        self.stats.pending = len(self._pending_ids)
        self._restore_best(round_no, why=why)
        self._hint_user_scoring(cid)

    # ---- 验证决策 ----
    def _run_suite(self, suite: List[str]) -> SuiteResult:
        """跑测试套件。默认运行器接上 sink.should_stop：TUI 按 q /
        Ctrl+C 时立即整组终止套件，否则守卫会在套件上阻塞到
        verify_timeout。注入的测试接缝保持三参数签名。"""
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
                    # 不能再转兜底评审——用户已经离开
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
                # 这行也会被永久跳过
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
        # 才能终止正在运行的评审（否则评审进程会脱离终端会话跑满
        # judge_timeout）
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
        一次，直接重读实时状态会让评审的是 A、晋升的是快照 B。快照在
        验证期间被删除/损坏时，调用方按「待评分」挂起，绝不能拿未验证
        的实时状态顶替。"""
        try:
            return (self.dir / f"{CAND_PREFIX}{cid}.md").read_text(
                encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise OSError(f"候选快照 {cid} 不可读：{e}") from e

    def _judge_prompt(self, round_no: int, cid: str) -> str:
        best_text = self._best_content()
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
    def _commit_best(self, text: Optional[str], best: Dict) -> None:
        """晋升落盘：best.json（元数据）→ best.md（镜像，最后落盘 =
        「基线已建立」的存在标志）。

        两个文件内容同源（同一份被验证过的快照文本），读取路径的内容
        权威是快照、镜像只是展示，因此 best.md 写失败最多让镜像滞后，
        不会产生「元数据与内容不一致」。调用方据异常保持候选「未决」：
        写盘恢复后补分/重试仍能兑现。"""
        if not text:
            # 没有任何被验证过的内容可写进最佳：只推进元数据会把最佳
            # 指向一份读不到内容的快照。按写盘失败同等处理
            raise OSError("候选快照不可读，无法写盘晋升最佳")
        _atomic_write(self.best_json,
                      json.dumps(best, ensure_ascii=False, indent=2))
        _atomic_write(self.best_md, text)

    def _adopt(self, cid: str, round_no: int, verdict: Verdict) -> None:
        # 晋升的必须是被验证过的候选快照本身：测试套件 / AI 评审可能跑
        # 很久，期间状态文件可能被外部再改一次。直接读当前状态会把未经
        # 验证的内容写进 best.md；快照不可读/结构损坏时抛异常，由
        # on_round_end 兜底挂起，绝不拿实时状态顶替
        text = self._read_candidate_text(cid)
        if not _structure_intact(text):
            raise OSError("候选快照区块标记损坏，无法晋升为最佳")
        best = {"id": cid, "round": round_no, "verifier": verdict.verifier,
                "score": verdict.score, "ts": _ts(),
                "reason": verdict.reason}
        # 两个文件都写盘成功后才提交内存状态与统计
        self._commit_best(text, best)
        self.best = best
        self.stats.adopted += 1
        self.sink.ok(f"第 {round_no} 轮候选通过验证（{verdesc(verdict)}），"
                     f"晋升为最佳（{cid}）")

    def _restore_best(self, round_no: int, why: str) -> List[str]:
        """把 research.md 的两个区块还原为当前最佳内容（前进式还原：
        不删任何文件、不改写历史，只把循环的「当前状态」拨回最佳）。
        返回实际被改回的区块名列表（无变化返回空表，不产生事件噪音）。"""
        best_text = self._best_content()
        cur = self._read_state_text()
        changed: List[str] = []
        for name, key in ((state.SECTION_IDEA, "idea"),
                          (state.SECTION_ARTIFACT, "artifact")):
            want = _readable_section(best_text, name)
            if want is None:
                # 最佳内容自身损坏时按「空内容」处理，但结构仍要修复回来
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
        self._append_event_safe({"event": "restored", "round": round_no,
                                 "why": why, "best": self.best.get("id"),
                                 "changed": changed})
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

    # ---- 用户评分（verdicts.txt）：渐进翻案通道 ----
    def _read_verdicts(self) -> Dict[str, Tuple[Optional[float], str]]:
        out: Dict[str, Tuple[Optional[float], str]] = {}
        try:
            raw = self.verdicts_path.read_bytes()
        except OSError:
            return out
        # utf-8-sig：带 BOM 的首行若不剥，cid 会变成 "\ufeff<cid>"，用户
        # 评分被静默忽略。errors="replace"：个别坏字节不能让整份评分文件
        # 静默失效——cid 与分数列都是 ASCII，坏字节只会出现在评语里
        text = raw.decode("utf-8-sig", errors="replace")
        # 只按 ASCII 换行切分（与 _read_events 同口径）：str.splitlines
        # 还会在 U+2028 等 Unicode 行分隔符处切开，评语里含这些字符时
        # 一行评分会被拆成两行——后半段若恰好以「cid 分数」开头，就会
        # 被解析成一条凭空出现的伪评分
        for line in re.split(r"\r\n|\r|\n", text):
            line = line.strip().lstrip("\ufeff").strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 2)
            if len(parts) < 2:
                continue
            cid, raw_score, comment = parts[0], parts[1], (
                parts[2].strip() if len(parts) > 2 else "")
            try:
                score = float(raw_score)
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
                # 同一候选写了两行、后一行分数打错时，不能让坏行覆盖
                # 前面已解析出的有效评分；后一行有效评分仍按最后一条
                # 覆盖（用户用新分数纠正旧分数的主要写法）
                continue
            out[cid] = (score, comment)
        return out

    def _cash_verdicts_safe(self) -> None:
        """兑现待决用户评分；失败只告警（守卫降级原则，稍后自动重试）。"""
        try:
            self._apply_user_verdicts()
        except Exception as e:  # noqa: BLE001 —— 守卫降级原则
            self.sink.warn(f"应用待决用户评分失败（忽略，稍后重试）：{e}")

    def _apply_user_verdicts(self) -> None:
        """把 verdicts.txt 里的新评分应用到仍处「待评分」的候选上。

        采纳旧候选 = 前进式晋升（快照内容成为新最佳并写回 research.md，
        等价于回滚到它，但不改写任何历史记录）；拒绝旧候选 = 只记账。
        采纳前会重新校验快照的区块结构（见 _structure_intact），损坏
        快照保持挂起。"""
        verdicts = self._read_verdicts()
        if not verdicts:
            return
        resolved: set = set()
        rounds_by_cid: Dict[str, object] = {}
        for ev in self._read_events():
            cid = ev.get("id")
            if not _valid_cid(cid):
                # 历史行被外部编辑时 id 可能是列表/字典等非字符串：拿它
                # 当键会抛 TypeError，让兑现通道整体失败
                continue
            if ev.get("event") == "candidate":
                rounds_by_cid[cid] = ev.get("round", 0)
            elif (ev.get("event") == "verdict"
                    and ev.get("result") in ("adopted", "rejected")):
                # 只有真正下了结论才算已决；「挂起」不算——挂起候选正是
                # 要等这里的补分来翻案的
                resolved.add(cid)
        # 当前最佳天然已经「已决」：不让用户后来的一行评分把当前最佳
        # 再采纳一次（统计重复）或记一条「拒绝当前最佳」的自相矛盾判定
        resolved.add(self.best.get("id"))
        for cid, (score, comment) in verdicts.items():
            if cid in resolved or cid in self._applied:
                continue
            if cid not in rounds_by_cid:
                # 引用了不存在的候选 id（抄错一个字符等）：静默忽略会让
                # 用户以为评分已提交，实际永远不生效。每个 id 只提示一次
                if cid not in self._warned_unknown:
                    self._warned_unknown.add(cid)
                    self.sink.warn(
                        f"rounds/verdicts.txt 里的候选 id「{cid}」不存在"
                        "（该行被忽略，请核对是否抄写错误）")
                continue
            if score is None:
                # 解析不出的行按「挂起」处理（既不采纳也不丢弃）：记为
                # 「已决」会把候选永久锁死，用户修正这行也再翻不了案
                if cid not in self._warned_badscore:
                    self._warned_badscore.add(cid)
                    self.sink.warn(f"候选 {cid} 的评分行无法解析（保持挂起）："
                                   f"请改为「{cid} <0-10分> [评语]」")
                continue
            round_no = rounds_by_cid[cid]
            if not _valid_round(round_no):
                # 历史行可能是合法 JSON 但类型不对的 round（字符串……）：
                # round 不可信时按 0 归一化，采纳本身照常兑现（候选 id 与
                # 快照仍然有效，不能因元数据坏而丢失产物）
                self.sink.warn(f"候选 {cid} 的历史轮次字段不可用"
                               f"（{round_no!r}），已按第 0 轮记账")
                round_no = 0
            adopted = score >= self.cfg.rounds.adopt_score
            text = None
            best: Dict = {}
            if adopted:
                # 先读快照、写盘成功，再记「已决」事件：写盘失败时保持
                # 挂起——已决事件会让本通道永久跳过该候选，用户腾出磁盘
                # 后也再翻不了案
                text = self._snapshot_text(cid)
                if text is None:
                    self.sink.warn(f"采纳旧候选 {cid} 失败（快照不可读或结构"
                                   "损坏，保持挂起）")
                    continue
                best = {"id": cid, "round": round_no, "verifier": "user",
                        "score": score, "ts": _ts(), "late": True,
                        "reason": f"用户补评分 {score:g}"}
                try:
                    self._commit_best(text, best)
                except OSError as e:
                    self.sink.warn(f"采纳旧候选 {cid} 失败（最佳写盘失败，"
                                   f"保持挂起）：{e}")
                    continue
            verdict = Verdict(verifier="user", score=score,
                              result="adopted" if adopted else "rejected",
                              reason=f"用户补评分 {score:g}",
                              comment=comment)
            self._append_event_safe({"event": "verdict", "id": cid,
                                     "round": round_no, "late": True,
                                     **_verdict_fields(verdict)})
            self._applied.add(cid)
            # 统计与改判同步：采纳/拒绝是「本次运行兑现的判定」的计数
            # （跨会话旧候选也计入，否则汇总会一边宣布晋升、一边报
            # 「采纳 0」）；pending 只回减本会话计入过待评分的候选
            self._pending_ids.discard(cid)
            self.stats.pending = len(self._pending_ids)
            if adopted:
                self.best = best
                self.stats.adopted += 1
                # 前进式采纳旧快照：内容写回 research.md，下一轮直接从它
                # 继续（不改写 history.jsonl 的既有记录）
                self._write_back(text, round_no)
                self.sink.ok(f"旧候选 {cid} 获用户补评 {score:g}，"
                             "前进式晋升为最佳")
            else:
                self.stats.rejected += 1
                self.sink.info(f"旧候选 {cid} 获用户补评 {score:g}，"
                               "未达阈值，保持当前最佳")

    def _write_back(self, text: str, round_no: int) -> None:
        """把晋升内容写回 research.md（与 restored 事件保持 1:1；无区块
        变化（状态文件已与快照一致）时不产生事件、不虚增统计）。"""
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
        if changed:
            self.stats.restored += 1
            self._append_event_safe({"event": "restored", "round": round_no,
                                     "why": "旧候选被补评采纳",
                                     "best": self.best.get("id"),
                                     "changed": changed})


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
