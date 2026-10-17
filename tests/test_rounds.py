"""轮次守卫单元测试：快照、候选/最佳分离、验证级联、用户/AI 评分、还原语义。"""
import json
import shutil
from pathlib import Path

import pytest

from xuen import state
from xuen.config import Config
from xuen.rounds import (
    RoundGuard,
    SuiteResult,
    detect_test_suite,
    parse_score,
    resolve_repo,
)
from xuen.sink import SECTION_ARTIFACT, SECTION_IDEA, Sink


class RecordingSink(Sink):
    """记录所有消息的静默 sink。"""

    def __init__(self):
        self.messages = []

    def _log(self, level, text):
        self.messages.append((level, text))

    def info(self, text): self._log("info", text)
    def ok(self, text): self._log("ok", text)
    def warn(self, text): self._log("warn", text)
    def err(self, text): self._log("err", text)

    def round_header(self, index, label):
        self._log("round", f"#{index} {label}")

    def agent_output(self, line): pass
    def agent_stderr(self, line): pass

    def section(self, name, content):
        self._log("section", f"{name}: {content[:40]}")


@pytest.fixture
def ws(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "research.md"
    state.ensure_state_file(state_path, "测试任务")
    return workspace, state_path


def make_cfg(**rounds_overrides) -> Config:
    cfg = Config()
    cfg.agent.command = 'echo "$prompt"'
    for k, v in rounds_overrides.items():
        setattr(cfg.rounds, k, v)
    return cfg


def make_guard(workspace, state_path, sink=None, judge=None, suite_runner=None,
               **rounds_overrides) -> RoundGuard:
    cfg = make_cfg(**rounds_overrides)
    guard = RoundGuard(cfg, "测试任务", state_path, workspace,
                       sink or RecordingSink(),
                       judge=judge, suite_runner=suite_runner)
    return guard


def write_idea(state_path, text):
    state.update_section_file(state_path, state.SECTION_IDEA, text)


def write_artifact(state_path, text):
    state.update_section_file(state_path, state.SECTION_ARTIFACT, text)


def read_idea(state_path):
    return state.get_section(state_path.read_text(encoding="utf-8"),
                             state.SECTION_IDEA)


def events(guard):
    return guard._read_events()


def cand_files(guard):
    return sorted(p.name for p in guard.dir.glob("cand-*.md"))


# ---------------------------------------------------------------- 基线与心跳
def test_start_creates_baseline(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    assert (guard.dir / "best.md").exists()
    assert guard.best["round"] == 0
    assert guard.best["verifier"] == "baseline"
    evs = events(guard)
    assert evs and evs[0]["event"] == "baseline"


def test_start_reuses_existing_best(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    first_best = guard.best["id"]
    # 第二次启动（模拟 xuen 重启）：不重建基线，历史只增不改
    guard2 = make_guard(workspace, state_path)
    guard2.start()
    assert guard2.best["id"] == first_best
    evs = events(guard2)
    assert [e["event"] for e in evs].count("baseline") == 1


def test_heartbeat_when_no_change(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    assert guard.on_round_end(1) == "heartbeat"
    assert cand_files(guard) == []
    assert guard.stats.heartbeat == 1
    assert guard.stats.candidates == 0


# ---------------------------------------------------------------- AI 评分
def test_ai_adopt_promotes_candidate(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="ai",
                       judge=lambda p: (True, "更深入了\n评分: 8"))
    guard.start()
    write_idea(state_path, "新想法：双曲空间初始化")
    result = guard.on_round_end(1)
    assert result == "adopted"
    # 候选晋升为最佳：best.json 记录该轮；research.md 保留候选内容
    assert guard.best["round"] == 1
    assert guard.best["verifier"] == "ai"
    assert guard.best["score"] == 8.0
    assert read_idea(state_path) == "新想法：双曲空间初始化"
    assert (guard.dir / "best.md").read_text(encoding="utf-8") \
        == state_path.read_text(encoding="utf-8")
    assert len(cand_files(guard)) == 1


def test_ai_reject_restores_best_and_keeps_snapshot(ws):
    """核心回归：被拒绝的候选绝不留在循环状态里，但快照必须保留。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="ai",
                       judge=lambda p: (True, "退步了\n评分: 3"))
    guard.start()
    write_idea(state_path, "更差的想法")
    write_artifact(state_path, "更差的产物")
    result = guard.on_round_end(1)
    assert result == "rejected"
    # research.md 被还原为基线（（暂无）），下一轮从最佳出发
    assert read_idea(state_path) == "（暂无）"
    assert state.get_section(state_path.read_text(encoding="utf-8"),
                             state.SECTION_ARTIFACT) == "（暂无）"
    # 最佳仍是基线
    assert guard.best["round"] == 0
    # 但候选快照留档（任何一轮的产物都不再丢失）
    assert len(cand_files(guard)) == 1
    snap = (guard.dir / cand_files(guard)[0]).read_text(encoding="utf-8")
    assert "更差的想法" in snap
    # 事件序列：candidate → verdict(rejected) → restored
    kinds = [e["event"] for e in events(guard)]
    assert kinds == ["baseline", "candidate", "verdict", "restored"]


def test_ai_unparseable_score_pends(ws):
    """评分解析不出 = 无法下结论 → 挂起（既不采纳也不丢弃）。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="ai",
                       judge=lambda p: (True, "我拒绝打分"))
    guard.start()
    write_idea(state_path, "某个想法")
    assert guard.on_round_end(1) == "pending"
    assert read_idea(state_path) == "（暂无）"
    assert guard.best["round"] == 0
    assert len(cand_files(guard)) == 1


def test_ai_judge_infrastructure_failure_pends(ws):
    """评审员超时/非零退出 ≠ 候选差：挂起等待用户，绝不误拒。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="ai",
                       judge=lambda p: (False, "timeout"))
    guard.start()
    write_idea(state_path, "某个想法")
    assert guard.on_round_end(1) == "pending"


def test_ai_judge_registered_as_current_agent(ws, monkeypatch):
    """评审期间 sink.agent 必须指向评审员：TUI 退出才能终止正在跑的评审，
    否则 kill 落到已结束的主 agent 上，评审进程会孤儿化跑到超时。"""
    from xuen import agents

    workspace, state_path = ws
    sink = RecordingSink()
    sentinel = object()
    sink.agent = sentinel
    seen = []
    real_run = agents.ShellAgent.run

    def spy_run(self, prompt):
        seen.append(getattr(sink, "agent", None))
        return real_run(self, prompt)

    monkeypatch.setattr(agents.ShellAgent, "run", spy_run)
    guard = make_guard(workspace, state_path, sink=sink, verify="ai",
                       judge_command='printf "评分: 9\\n"')
    guard.start()
    write_idea(state_path, "某个想法")
    assert guard.on_round_end(1) == "adopted"
    assert len(seen) == 1
    assert seen[0] is not None and seen[0] is not sentinel
    assert sink.agent is sentinel  # 评审结束后恢复原引用


def test_ai_score_threshold_boundary(ws):
    """评分恰好等于阈值也算采纳（>= adopt_score）。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="ai", adopt_score=7.0,
                       judge=lambda p: (True, "评分: 7"))
    guard.start()
    write_idea(state_path, "临界想法")
    assert guard.on_round_end(1) == "adopted"
    guard2 = make_guard(workspace, state_path, verify="ai", adopt_score=7.1,
                        judge=lambda p: (True, "评分: 7"))
    guard2.start()
    write_idea(state_path, "又一临界想法")
    assert guard2.on_round_end(2) == "rejected"


# ---------------------------------------------------------------- 结构损坏
def test_corrupt_markers_auto_rejected(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    # 外部 agent 把标记行弄丢：内容无法被安全读取，守卫直接拒绝
    state_path.write_text("# 只剩标题，标记全没了\n", encoding="utf-8")
    assert guard.on_round_end(1) == "rejected"
    verdicts = [e for e in events(guard) if e["event"] == "verdict"]
    assert verdicts[0]["verifier"] == "guard"
    # research.md 被重建为最佳内容
    assert read_idea(state_path) == "（暂无）"


# ---------------------------------------------------------------- 测试级联
def test_detect_test_suite_pytest(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    suite = detect_test_suite(tmp_path)
    assert suite is not None and "pytest" in suite


def test_detect_test_suite_none(tmp_path):
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make(tmp_path):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text("test:\n\techo ok\n", encoding="utf-8")
    suite = detect_test_suite(tmp_path)
    assert suite == ["make", "test"]


def _fake_npm(monkeypatch):
    """让 npm 探测分支无视本机是否装了 npm（只伪造 npm 的 which 结果）。"""
    real_which = shutil.which

    def which(name, *args, **kwargs):
        if name == "npm":
            return "/usr/bin/npm"
        return real_which(name, *args, **kwargs)

    monkeypatch.setattr("xuen.rounds.shutil.which", which)


def test_detect_test_suite_npm(tmp_path, monkeypatch):
    _fake_npm(monkeypatch)
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "vitest run"}}', encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["npm", "test"]


def test_detect_test_suite_npm_placeholder_ignored(tmp_path, monkeypatch):
    _fake_npm(monkeypatch)
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "echo \\"Error: no test specified\\" && exit 1"}}',
        encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("pkg", [
    '["not", "an", "object"]',   # 顶层不是对象：.get 不存在
    '{"scripts": ["npm test"]}',  # scripts 是数组：.get 不存在
    '{"scripts": "npm test"}',    # scripts 是字符串
    '{"scripts": {"test": 123}}',  # test 不是字符串
    "null",
])
def test_detect_test_suite_npm_malformed_shape_ignored(tmp_path, monkeypatch,
                                                       pkg):
    """JSON 合法但结构不对的 package.json 不能抛 AttributeError：探测异常
    会让 on_round_end 跳过验证，未验证候选滞留循环状态。"""
    _fake_npm(monkeypatch)
    (tmp_path / "package.json").write_text(pkg, encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_guard_survives_malformed_package_json(ws, tmp_path, monkeypatch):
    """端到端：脏 package.json 下守卫正常给出「无法验证 → 挂起」，
    并把挂起候选还原出循环状态（绝不因探测崩溃放行候选）。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        '{"scripts": ["npm test"]}', encoding="utf-8")
    _fake_npm(monkeypatch)
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="tests", repo=str(repo))
    guard.start()
    write_idea(state_path, "脏 package.json 下的想法")
    assert guard.on_round_end(1) == "pending"
    assert read_idea(state_path) == "（暂无）"


def test_resolve_repo_explicit_wins(tmp_path, tmp_path_factory):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (tmp_path / ".git").mkdir()  # 假 git 根（只查存在性）
    explicit = tmp_path / "elsewhere"
    explicit.mkdir()
    assert resolve_repo(str(explicit), workspace) == explicit.resolve()
    assert resolve_repo("", workspace) == tmp_path.resolve()
    # 非 git 环境：退化为工作区本身（必须在任何 .git 之外的独立临时目录）
    lone_root = tmp_path_factory.mktemp("nogit")
    lone = lone_root / "ws"
    lone.mkdir()
    assert resolve_repo("", lone) == lone.resolve()


def test_tests_mode_adopt_on_green(ws, tmp_path):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_ok.py").write_text("", encoding="utf-8")
    results = {"n": 0}

    def fake_suite(argv, cwd, timeout):
        results["n"] += 1
        return SuiteResult(available=True, ok=True, reason="exit 0")

    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="tests",
                       repo=str(repo), suite_runner=fake_suite)
    guard.start()
    write_idea(state_path, "绿测试下的想法")
    assert guard.on_round_end(1) == "adopted"
    assert results["n"] == 1
    assert guard.best["verifier"] == "tests"


def test_tests_mode_reject_on_red(ws, tmp_path):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_bad.py").write_text("", encoding="utf-8")

    def fake_suite(argv, cwd, timeout):
        return SuiteResult(available=True, ok=False, reason="退出码 1",
                           detail="assert False")

    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="tests",
                       repo=str(repo), suite_runner=fake_suite)
    guard.start()
    write_idea(state_path, "红测试下的想法")
    assert guard.on_round_end(1) == "rejected"
    assert read_idea(state_path) == "（暂无）"
    verdict = [e for e in events(guard) if e["event"] == "verdict"][0]
    assert verdict["verifier"] == "tests"


def test_tests_mode_pending_when_no_suite(ws, tmp_path):
    """显式 tests 但没有可运行套件：无法验证 → 挂起等待用户评分。"""
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="tests", repo=str(repo))
    guard.start()
    write_idea(state_path, "无从验证的想法")
    assert guard.on_round_end(1) == "pending"
    assert read_idea(state_path) == "（暂无）"


def test_auto_mode_prefers_tests_over_fallback(ws, tmp_path):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_x.py").write_text("", encoding="utf-8")
    called = {"suite": 0, "judge": 0}

    def fake_suite(argv, cwd, timeout):
        called["suite"] += 1
        return SuiteResult(available=True, ok=False, reason="退出码 2")

    def fake_judge(prompt):
        called["judge"] += 1
        return True, "评分: 9"

    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="auto", fallback="ai",
                       repo=str(repo), suite_runner=fake_suite,
                       judge=fake_judge)
    guard.start()
    write_idea(state_path, "想法")
    assert guard.on_round_end(1) == "rejected"   # 测试说了算，AI 不参与
    assert called == {"suite": 1, "judge": 0}


def test_auto_mode_falls_back_to_ai_without_suite(ws, tmp_path):
    repo = tmp_path / "empty"
    repo.mkdir()
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="auto", fallback="ai",
                       repo=str(repo),
                       judge=lambda p: (True, "评分: 8"))
    guard.start()
    write_idea(state_path, "想法")
    assert guard.on_round_end(1) == "adopted"
    assert guard.best["verifier"] == "ai"


def test_verify_off_adopts_without_verification(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "快照防丢失模式")
    assert guard.on_round_end(1) == "adopted"
    assert guard.best["verifier"] == "none"
    assert read_idea(state_path) == "快照防丢失模式"


# ---------------------------------------------------------------- 用户评分
def test_verify_user_ignores_ai_fallback(ws):
    """verify=user 必须走用户评分：fallback（默认 ai）只服务 auto 模式，
    不能顶替用户的显式选择，否则候选会被 AI 静默打分而非等待用户。"""
    workspace, state_path = ws
    called = {"judge": 0}

    def fake_judge(prompt):
        called["judge"] += 1
        return True, "评分: 9"

    guard = make_guard(workspace, state_path, verify="user", fallback="ai",
                       judge=fake_judge)
    guard.start()
    write_idea(state_path, "用户还没看过的想法")
    assert guard.on_round_end(1) == "pending"
    assert called["judge"] == 0
    assert guard.best["round"] == 0
    assert read_idea(state_path) == "（暂无）"


def test_auto_fallback_user_waits_for_user(ws, tmp_path):
    """auto + fallback=user：无测试套件时挂起等用户评分，不得调用 AI 评审。"""
    repo = tmp_path / "empty"
    repo.mkdir()
    called = {"judge": 0}

    def fake_judge(prompt):
        called["judge"] += 1
        return True, "评分: 9"

    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="auto", fallback="user",
                       repo=str(repo), judge=fake_judge)
    guard.start()
    write_idea(state_path, "等待用户评分的想法")
    assert guard.on_round_end(1) == "pending"
    assert called["judge"] == 0
    assert guard.best["round"] == 0


def test_user_pending_then_late_adoption_restores_candidate(ws):
    """异步用户评分：挂起候选拿到高分后，前进式晋升并写回状态文件。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "被搁置的好想法")
    write_artifact(state_path, "被搁置的好产物")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    # 循环期间状态被还原为最佳，好想法暂不进入下一轮
    assert read_idea(state_path) == "（暂无）"

    # 用户稍后在 verdicts.txt 补分（>= 阈值）
    (guard.dir / "verdicts.txt").write_text(
        f"# 我的评分\n{cid} 9 想法更有深度\n", encoding="utf-8")
    guard.finish()  # 收尾时兑现
    assert guard.best["id"] == cid
    assert guard.best["verifier"] == "user"
    assert guard.best["round"] == 1
    # 前进式采纳：内容写回 research.md，下一轮从它继续
    assert read_idea(state_path) == "被搁置的好想法"
    assert state.get_section(state_path.read_text(encoding="utf-8"),
                             state.SECTION_ARTIFACT) == "被搁置的好产物"
    kinds = [e["event"] for e in events(guard)]
    assert kinds[-2] == "verdict" and kinds[-1] == "restored"
    late = [e for e in events(guard) if e["event"] == "verdict"][-1]
    assert late.get("late") is True


def test_user_late_low_score_keeps_best(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "被搁置的差想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 2\n", encoding="utf-8")
    guard.finish()
    assert guard.best["round"] == 0
    assert read_idea(state_path) == "（暂无）"


def test_verdicts_only_applied_once(ws):
    """同一候选的评分不会被重复应用（verdict 事件即「已决」标记）。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "想法A")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9\n", encoding="utf-8")
    guard.finish()
    n_verdicts = len([e for e in events(guard) if e["event"] == "verdict"])
    guard.finish()  # 再收尾一次
    assert len([e for e in events(guard) if e["event"] == "verdict"]) \
        == n_verdicts


def test_verdicts_bad_lines_ignored(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    assert guard._read_verdicts() == {}
    (guard.dir / "verdicts.txt").write_text(
        "# 注释\n\nonly-one-token\nid-but-not-a-number abc\n", encoding="utf-8")
    v = guard._read_verdicts()
    assert "only-one-token" not in v
    assert v["id-but-not-a-number"][0] is None


def test_verdicts_non_finite_score_not_adopted(ws):
    """nan/inf 不是合法评分：不能因 min/max 夹取而变成 10 分被采纳。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    (guard.dir / "verdicts.txt").write_text(
        "cand-nan nan\ncand-inf inf\ncand-ninf -inf\n", encoding="utf-8")
    v = guard._read_verdicts()
    assert v["cand-nan"][0] is None
    assert v["cand-inf"][0] is None
    assert v["cand-ninf"][0] is None

    # 端到端：待评分候选被补一行 nan，收尾兑现时绝不能晋升为最佳
    write_idea(state_path, "被搁置的想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} nan\n", encoding="utf-8")
    guard.finish()
    assert guard.best["round"] == 0
    assert read_idea(state_path) == "（暂无）"


# ---------------------------------------------------------------- 失败轮次
def test_round_failed_restores_best(ws):
    """agent 失败轮次的半截产物同样不能污染下一轮起点。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "超时前写了一半的想法")
    guard.on_round_failed(1, "超时")
    assert read_idea(state_path) == "（暂无）"
    kinds = [e["event"] for e in events(guard)]
    assert "skipped" in kinds and "restored" in kinds


# ---------------------------------------------------------------- 其它
def test_id_collision_gets_suffix(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.dir.mkdir(parents=True, exist_ok=True)
    id1 = guard._new_id(1)
    (guard.dir / f"cand-{id1}.md").write_text("x", encoding="utf-8")
    id2 = guard._new_id(1)
    assert id1 != id2


def test_next_round_starts_from_best_not_last_candidate(ws):
    """端到端语义：连续两轮，第一轮好、第二轮差 → 最终状态停在第一轮。"""
    workspace, state_path = ws
    scores = {"n": 0}

    def judge(prompt):
        scores["n"] += 1
        # 第一轮 8 分（好），之后 3 分（差）——模拟先升后降
        return True, "评分: 8" if scores["n"] == 1 else "评分: 3"

    guard = make_guard(workspace, state_path, verify="ai", judge=judge)
    guard.start()
    write_idea(state_path, "第一轮：好的方案")
    assert guard.on_round_end(1) == "adopted"
    write_idea(state_path, "第二轮：更差的方案")
    assert guard.on_round_end(2) == "rejected"
    # 更差的第二轮没有覆盖更好的第一轮
    assert read_idea(state_path) == "第一轮：好的方案"
    assert guard.best["round"] == 1
    assert len(cand_files(guard)) == 2   # 两轮快照都在


def test_parse_score_variants():
    assert parse_score("评语\n评分: 8") == 8.0
    assert parse_score("score: 7.5") == 7.5
    assert parse_score("评分：9/10") == 9.0
    assert parse_score("评分: 12") == 10.0          # 上限截断
    assert parse_score("评分: 3 ... 最终 score: 8.5") == 8.5  # 取最后一次
    assert parse_score("评分: -1") is None           # 负分不可解析→挂起
    assert parse_score("") is None
    assert parse_score("没有任何分数") is None
