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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import state
from .agents import ShellAgent
from .config import Config
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
_SCORE_PATTERNS = (
    re.compile(r"评\s*分\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)"),
    re.compile(r"[Ss]core\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)"),
)


# ----------------------------------------------------------------------
# 小工具
def _atomic_write(path: Path, text: str) -> None:
    """tmp + os.replace 原子写：读端永远不会看到半截文件。"""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


@dataclass
class SuiteResult:
    """一次测试套件运行的结果。available=False 表示套件根本没能运行
    （运行时缺命令等），与「跑了但失败」（ok=False）必须区分：
    前者不能给候选下结论，只能转兜底评分或挂起。"""
    available: bool
    ok: bool = False
    reason: str = ""
    detail: str = ""


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


def detect_test_suite(repo: Path) -> Optional[List[str]]:
    """按 pytest → make test → npm test → go test 的顺序探测可运行套件。

    返回 argv 列表；没有任何可运行套件时返回 None（此时「不能用测试
    验证」，由调用方转用户/AI 评分）。探测只做静态存在性检查，不真正
    执行测试，代价极低，每轮重探一次也没问题（工作区里新出现 tests/
    的下一轮就会被纳入测试验证）。
    """
    if not repo.is_dir():
        return None
    # 1) pytest：仓库根或 tests/ 下有 test_*.py / *_test.py，且本机装了 pytest
    py_tests = [p for pat in ("test_*.py", "*_test.py")
                for p in list(repo.glob(pat)) + list((repo / "tests").glob(pat))]
    if py_tests and _find_spec("pytest"):
        return [sys.executable, "-m", "pytest", "-q"]
    # 2) make test：Makefile 里定义了 test 目标
    makefile = repo / "Makefile"
    if makefile.is_file() and shutil.which("make"):
        try:
            if re.search(r"(?m)^test[a-zA-Z0-9_.-]*\s*:", makefile.read_text(encoding="utf-8", errors="replace")):
                return ["make", "test"]
        except OSError:
            pass
    # 3) npm test：package.json 声明了非占位的 test 脚本
    pkg = repo / "package.json"
    if pkg.is_file() and shutil.which("npm"):
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8", errors="replace")).get("scripts") or {}
            test_cmd = scripts.get("test")
            if isinstance(test_cmd, str) and test_cmd.strip() \
                    and "no test specified" not in test_cmd:
                return ["npm", "test"]
        except (OSError, ValueError):
            pass
    # 4) go test
    if any(repo.glob("*.go")) and shutil.which("go"):
        return ["go", "test", "./..."]
    return None


def run_suite(argv: List[str], repo: Path, timeout: float) -> SuiteResult:
    """运行测试套件。退出码 0 = 通过；非 0 = 失败；超时 = 失败（保守：
    宁可不采纳候选，也不让超时的测试把可能损坏的产物放进最佳）。"""
    try:
        proc = subprocess.run(
            argv, cwd=str(repo), timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return SuiteResult(available=True, ok=False,
                           reason=f"测试超时（>{timeout:g}s）")
    except (OSError, ValueError):
        # 探测时存在、运行时却拉不起来（PATH 变化 / 权限 ……）
        return SuiteResult(available=False, reason="测试命令无法启动")
    detail = (proc.stdout or "").strip()
    if proc.returncode == 0:
        return SuiteResult(available=True, ok=True, reason="exit 0", detail=detail)
    tail = "\n".join(detail.splitlines()[-15:])
    return SuiteResult(available=True, ok=False,
                       reason=f"退出码 {proc.returncode}", detail=tail)


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
    """

    def __init__(
        self,
        cfg: Config,
        task: str,
        state_path: Path,
        workspace: Path,
        sink: Sink,
        *,
        suite_runner: Callable[[List[str], Path, float], SuiteResult] = run_suite,
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
        self._hinted = False  # 「如何评分」提示只打印一次

    # ---- 基础设施 ----
    def _append_event(self, ev: Dict) -> None:
        ev = dict(ev)
        ev.setdefault("ts", _ts())
        with open(self.history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def _read_events(self) -> List[Dict]:
        events: List[Dict] = []
        try:
            text = self.history_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return events
        for line in text.splitlines():
            line = line.strip()
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
        try:
            data = json.loads(self.best_json.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        return {"id": "unknown", "round": -1, "verifier": "unknown",
                "score": None, "ts": ""}

    def _read_state_text(self) -> str:
        try:
            return self.state_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    def _sections(self, text: str) -> Tuple[str, str]:
        return (state.get_section(text, state.SECTION_IDEA),
                state.get_section(text, state.SECTION_ARTIFACT))

    def _new_id(self, round_no: int) -> str:
        base = f"{time.strftime('%Y%m%d-%H%M%S')}-r{round_no}"
        cid, seq = base, 2
        # 同一秒内多轮（快速测试/时钟回拨）也不允许 id 撞车：撞车会让
        # 旧候选被新快照覆盖——恰恰是本模块要根除的问题
        while (self.dir / f"{CAND_PREFIX}{cid}.md").exists():
            cid = f"{base}-{seq}"
            seq += 1
        return cid

    # ---- 生命周期 ----
    def start(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        if self.best_md.exists():
            self.best = self._load_best()
        else:
            # 首次运行：把当前 research.md 固化为基线最佳（哪怕还是脚手架）。
            # 有了基线，「第 1 轮候选被拒绝时还原到什么」才有明确答案。
            text = self._read_state_text() or state.scaffold(self.task)
            _atomic_write(self.best_md, text)
            self.best = {"id": f"baseline-{time.strftime('%Y%m%d-%H%M%S')}",
                         "round": 0, "verifier": "baseline", "score": None,
                         "ts": _ts()}
            _atomic_write(self.best_json,
                          json.dumps(self.best, ensure_ascii=False, indent=2))
            self._append_event({"event": "baseline", **self.best})
            self.sink.ok(f"轮次守卫：建立基线最佳 {self.best['id']}")
        self.sink.info(
            f"轮次守卫已启用：{self.dir}（每轮快照；候选需验证通过才晋升为最佳；"
            f"verify={self.cfg.rounds.verify}"
            + (f"，兜底评分={self.cfg.rounds.fallback}"
               if self.cfg.rounds.verify == "auto" else "")
            + "）")
        try:
            self._apply_user_verdicts()
        except OSError as e:
            self.sink.warn(f"应用待决用户评分失败（忽略，稍后重试）：{e}")

    def finish(self) -> None:
        try:
            self._apply_user_verdicts()
        except OSError as e:
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
        同时还原最佳——失败轮次留下的半截产物同样不能污染下一轮的起点。"""
        self.stats.rounds += 1
        self.stats.skipped += 1
        self._append_event({"event": "skipped", "round": round_no,
                            "reason": reason})
        self._restore_best(round_no, why=f"轮次失败（{reason}）")

    # ---- 每轮守卫主流程 ----
    def on_round_end(self, round_no: int) -> str:
        """一轮 agent 成功结束后调用；返回 adopted / rejected / pending /
        heartbeat / skipped 供调用方与测试断言。"""
        self.stats.rounds += 1
        text = self._read_state_text()
        if not text:
            # research.md 整个没了：没法当候选，也别让下一轮拿到空状态
            self.stats.skipped += 1
            self._append_event({"event": "skipped", "round": round_no,
                                "reason": "状态文件缺失或不可读"})
            self._restore_best(round_no, why="状态文件缺失")
            return "skipped"

        # 1) 结构检查：区块标记被外部 agent 弄坏的内容无法被安全读取，
        #    更不能进最佳——结构损坏直接拒绝（守卫级判定，无需测试/评分）
        if state._first_section(text, state.SECTION_IDEA) is None \
                or state._first_section(text, state.SECTION_ARTIFACT) is None:
            self.stats.candidates += 1
            cid = self._new_id(round_no)
            _atomic_write(self.dir / f"{CAND_PREFIX}{cid}.md", text)
            self._append_event({"event": "candidate", "id": cid,
                                "round": round_no, "corrupt": True})
            verdict = Verdict(verifier="guard", result="rejected",
                              reason="区块标记缺失或损坏，无法安全读取")
            self._append_event({"event": "verdict", "id": cid,
                                "round": round_no, **_verdict_fields(verdict)})
            self.stats.rejected += 1
            self.sink.err(f"候选 {cid} 被守卫拒绝：{verdict.reason}，已还原最佳")
            self._restore_best(round_no, why="结构损坏")
            return "rejected"

        # 2) 无改动 → 心跳（不产生候选，避免无意义快照淹没真正的轮次）
        cand_idea, cand_artifact = self._sections(text)
        best_text = self._read_best_md()
        best_idea, best_artifact = self._sections(best_text)
        if (cand_idea, cand_artifact) == (best_idea, best_artifact):
            self.stats.heartbeat += 1
            self._append_event({"event": "heartbeat", "round": round_no})
            return "heartbeat"

        # 3) 有改动 → 候选快照（先落盘：无论后续验证成败，本轮产物都不丢）
        self.stats.candidates += 1
        cid = self._new_id(round_no)
        _atomic_write(self.dir / f"{CAND_PREFIX}{cid}.md", text)
        changed = [n for n, (c, b) in {
            "idea": (cand_idea, best_idea),
            "artifact": (cand_artifact, best_artifact),
        }.items() if c != b]
        self._append_event({"event": "candidate", "id": cid,
                            "round": round_no, "changed": changed})
        self.sink.info(f"候选快照：{CAND_PREFIX}{cid}.md"
                       "（尚未验证，不代表最佳）")

        # 4) 验证 → 晋升 / 拒绝 / 挂起
        verdict = self._verify(round_no, cid)
        self._append_event({"event": "verdict", "id": cid,
                            "round": round_no, **_verdict_fields(verdict)})
        if verdict.result == "adopted":
            self._adopt(cid, round_no, verdict)
            return "adopted"
        if verdict.result == "rejected":
            self.stats.rejected += 1
            self.sink.warn(f"候选 {cid} 未通过（{verdesc(verdict)}），"
                           f"保留最佳并还原")
            self._restore_best(round_no, why="候选被拒绝")
            return "rejected"
        self.stats.pending += 1
        self._restore_best(round_no, why="候选待评分")
        self._hint_user_scoring(cid)
        return "pending"

    # ---- 验证决策 ----
    def _verify(self, round_no: int, cid: str) -> Verdict:
        mode = self.cfg.rounds.verify
        if mode == "off":
            return Verdict(verifier="none", result="adopted",
                           reason="verify=off：不验证，最新即最佳（快照照存）")

        if mode in ("auto", "tests"):
            suite = detect_test_suite(self.repo)
            if suite is not None:
                res = self._suite_runner(suite, self.repo,
                                         self.cfg.rounds.verify_timeout)
                if res.available:
                    if res.ok:
                        return Verdict(verifier="tests", result="adopted",
                                       reason="测试全部通过｜" + detail_field(res))
                    return Verdict(verifier="tests", result="rejected",
                                   reason="测试失败｜" + detail_field(res))
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
            adopted = score is not None and score >= self.cfg.rounds.adopt_score
            return Verdict(
                verifier="user", score=score,
                result="adopted" if adopted else "rejected",
                reason=f"用户评分 {score:g}" if score is not None else "评分无法解析",
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

    def _judge_prompt(self, round_no: int, cid: str) -> str:
        best_text = self._read_best_md()
        b_idea, b_artifact = self._sections(best_text)
        c_text = self._read_state_text()
        c_idea, c_artifact = self._sections(c_text)
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
    def _read_best_md(self) -> str:
        try:
            return self.best_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # best.md 损坏时按「空」处理：等价于基线脚手架，绝不能把
            # 损坏内容当最佳写回 research.md
            return state.scaffold(self.task)

    def _adopt(self, cid: str, round_no: int, verdict: Verdict) -> None:
        text = self._read_state_text()
        if text:
            _atomic_write(self.best_md, text)
        # best.json 记录的是「哪份快照是最佳」；研究循环只前进不改写历史，
        # 旧 best.md 内容已被这份覆盖前仍在各轮 cand-*.md / git 提交里留档
        self.best = {"id": cid, "round": round_no, "verifier": verdict.verifier,
                     "score": verdict.score, "ts": _ts(),
                     "reason": verdict.reason}
        _atomic_write(self.best_json,
                      json.dumps(self.best, ensure_ascii=False, indent=2))
        self.stats.adopted += 1
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
            want = state.get_section(best_text, name)
            have = state.get_section(cur, name) if cur else ""
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
        self._append_event({"event": "restored", "round": round_no,
                            "why": why, "best": self.best.get("id"),
                            "changed": changed})
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
            text = self.verdicts_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return out
        for line in text.splitlines():
            line = line.strip()
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
            out[cid] = (score, comment)
        return out

    def _apply_user_verdicts(self) -> None:
        """把 verdicts.txt 里的新评分应用到仍处「待评分」的候选上。
        采纳旧候选 = 前进式晋升（快照内容成为新最佳并写回 research.md），
        拒绝旧候选 = 只记账。这是异步用户评分的兑现通道。"""
        verdicts = self._read_verdicts()
        if not verdicts:
            return
        events = self._read_events()
        resolved: set = set()
        candidates: Dict[str, Dict] = {}
        for ev in events:
            ev_event = ev.get("event")
            cid = ev.get("id")
            if not cid:
                continue
            if ev_event == "candidate":
                candidates[cid] = ev
            elif ev_event == "verdict" and ev.get("result") != "pending":
                # 只有真正下了结论（采纳/拒绝）才算已决；「挂起」事件
                # 不算——挂起候选正是要等这里的补分来翻案的
                resolved.add(cid)
        for cid, score_comment in verdicts.items():
            if cid in resolved or cid not in candidates:
                continue
            score, comment = score_comment
            round_no = candidates[cid].get("round", 0)
            adopted = score is not None and score >= self.cfg.rounds.adopt_score
            verdict = Verdict(verifier="user", score=score,
                              result="adopted" if adopted else "rejected",
                              reason=(f"用户补评分 {score:g}"
                                      if score is not None else "评分无法解析"),
                              comment=comment)
            self._append_event({"event": "verdict", "id": cid,
                                "round": round_no, "late": True,
                                **_verdict_fields(verdict)})
            if adopted:
                # 前进式采纳旧快照：内容成为新最佳，并写回状态文件，
                # 下一轮直接从它继续（不改写 history.jsonl 的既有记录）
                cand_path = self.dir / f"{CAND_PREFIX}{cid}.md"
                try:
                    text = cand_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as e:
                    self.sink.warn(f"采纳旧候选 {cid} 失败（快照不可读）：{e}")
                    continue
                _atomic_write(self.best_md, text)
                self.best = {"id": cid, "round": round_no, "verifier": "user",
                             "score": score, "ts": _ts(), "late": True,
                             "reason": verdict.reason}
                _atomic_write(self.best_json,
                              json.dumps(self.best, ensure_ascii=False, indent=2))
                self.sink.ok(f"旧候选 {cid} 获用户补评 {score:g}，"
                             f"前进式晋升为最佳并写回状态文件")
                cur = self._read_state_text()
                for name in (state.SECTION_IDEA, state.SECTION_ARTIFACT):
                    want = state.get_section(text, name)
                    have = state.get_section(cur, name) if cur else ""
                    if want != have:
                        try:
                            state.update_section_file(self.state_path, name, want)
                        except (OSError, ValueError) as e:
                            self.sink.warn(f"写回区块失败（{name}）：{e}")
                self._append_event({"event": "restored", "round": round_no,
                                    "why": "旧候选被补评采纳", "best": cid,
                                    "changed": ["idea", "artifact"]})
            else:
                self.sink.info(f"旧候选 {cid} 获用户补评"
                               + (f" {score:g}" if score is not None else "")
                               + "，未达阈值，保持当前最佳")


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
