"""轮次守卫单元测试：快照、候选/最佳分离、验证级联、用户/AI 评分、还原语义。"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from xuen import rounds, state
from xuen.config import Config
from xuen.rounds import (
    RoundGuard,
    SuiteResult,
    detect_test_suite,
    parse_score,
    resolve_repo,
)
from xuen.sink import Sink


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


def test_baseline_partial_write_not_mistaken_as_established(ws, monkeypatch):
    """基线建立中途写盘失败：best.md 不能先落盘。

    best.md 是否存在是「基线已建立」的存在标志。反序（best.md 先成功、
    best.json 失败）会留下没有元数据的 best.md：下次启动走「复用已有
    最佳」分支读到未知 id，基线事件永远不会补记。内容源最后提交后，
    失败的下一次启动会重新建立完整基线。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)

    real_write = rounds._atomic_write

    def boom(path, text):
        if Path(path).name == rounds.BEST_MD_NAME:
            raise OSError("磁盘满（模拟）")
        return real_write(path, text)

    monkeypatch.setattr(rounds, "_atomic_write", boom)
    with pytest.raises(OSError):
        guard.start()
    assert not (guard.dir / rounds.BEST_MD_NAME).exists()

    # 写盘恢复后重试：建立真实基线，不把半截状态当成「已有最佳」
    monkeypatch.setattr(rounds, "_atomic_write", real_write)
    guard2 = make_guard(workspace, state_path)
    guard2.start()
    assert guard2.best["verifier"] == "baseline"
    assert guard2.best["round"] == 0
    assert [e["event"] for e in events(guard2)].count("baseline") == 1
    assert read_idea(state_path) == "（暂无）"


def test_atomic_write_tmp_is_pid_scoped(ws, monkeypatch):
    """临时文件名必须带 PID：并发实例绝不能互踩同一个 .tmp。

    回归：best.json / best.md 曾用固定名 <name>.tmp。同一 workspace 并发
    运行两个 xuen 实例时，两边会交错写同一临时文件，os.replace 把撕裂的
    内容发布成「有效」的最佳文件——best.json 解析失败退化成未知基线、
    best.md 碎裂后下一次还原把垃圾写回 research.md。words.txt 与
    write_section.py 的写入早已按 PID 隔离，守卫的原子写必须同口径。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()

    seen = []
    real_write = Path.write_text

    def spy(self, *args, **kwargs):
        seen.append(self.name)
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", spy)
    rounds._atomic_write(guard.best_json, "{}")
    rounds._atomic_write(guard.best_md, "x")

    pid = os.getpid()
    assert seen == [f"{rounds.BEST_JSON_NAME}.{pid}.tmp",
                    f"{rounds.BEST_MD_NAME}.{pid}.tmp"]
    assert guard.best_json.read_text(encoding="utf-8") == "{}"
    assert guard.best_md.read_text(encoding="utf-8") == "x"


def test_heartbeat_when_no_change(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    assert guard.on_round_end(1) == "heartbeat"
    assert cand_files(guard) == []
    assert guard.stats.heartbeat == 1
    assert guard.stats.candidates == 0


def test_marker_literal_content_reaches_heartbeat_after_restore(ws):
    """区块正文含独占一行的区块标记字面量时，还原后必须能回到心跳。

    回归：产物区正文里独占一行的 IDEA:START 是合法内容（重复 START 被
    解析器过滤为同区块字面量）。守卫还原时 update_section_file 会按写入
    协议剥掉这类标记行，而心跳/还原判定原先比较原样内容——最佳区永远
    带字面量、磁盘区永远没有，agent 不再改动也会每轮误生成候选快照、
    挂起并重复还原，永远无法心跳。
    """
    workspace, state_path = ws
    literal = state.start_marker(state.SECTION_IDEA)
    with_literal = f"伪代码 v1\n{literal}\n写入协议字面量"
    # 基线直接落盘（绕过写入协议，模拟外部 agent 直接编辑出含字面量的区块）
    state_path.write_text(
        f"# 研究\n\n{state.start_marker(state.SECTION_IDEA)}\n想法 v1\n"
        f"{state.end_marker(state.SECTION_IDEA)}\n\n"
        f"{state.start_marker(state.SECTION_ARTIFACT)}\n{with_literal}\n"
        f"{state.end_marker(state.SECTION_ARTIFACT)}\n",
        encoding="utf-8")
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    assert state.get_section((guard.dir / "best.md").read_text(encoding="utf-8"),
                             state.SECTION_ARTIFACT) == with_literal

    # 第 1 轮：标记交叉错乱的候选被守卫拒绝，research.md 还原为最佳；
    # 写入协议把产物区正文里的标记字面量规整掉
    state_path.write_text(
        f"# 研究\n\n{state.start_marker(state.SECTION_IDEA)}\n想法 v2\n"
        f"{state.start_marker(state.SECTION_ARTIFACT)}\n产物 v2\n"
        f"{state.end_marker(state.SECTION_IDEA)}\n"
        f"{state.end_marker(state.SECTION_ARTIFACT)}\n",
        encoding="utf-8")
    assert guard.on_round_end(1) == "rejected"
    assert state.get_section(state_path.read_text(encoding="utf-8"),
                             state.SECTION_ARTIFACT) \
        == "伪代码 v1\n写入协议字面量"
    restored = guard.stats.restored
    assert len(cand_files(guard)) == 1

    # 第 2、3 轮：agent 不再改动 → 心跳；不得再生成候选 / 挂起 / 重复还原
    assert guard.on_round_end(2) == "heartbeat"
    assert guard.on_round_end(3) == "heartbeat"
    assert guard.stats.heartbeat == 2
    assert guard.stats.candidates == 1
    assert guard.stats.pending == 0
    assert guard.stats.restored == restored
    assert len(cand_files(guard)) == 1
    assert [e["event"] for e in events(guard) if e.get("round") in (2, 3)] \
        == ["heartbeat", "heartbeat"]


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


def test_ai_adopt_promotes_verified_snapshot_not_live_state(ws):
    """验证期间状态文件被外部再改时，晋升的必须是被验证过的候选快照。

    回归：晋升原先重读当前状态文件写入 best.md，而 AI 评审/测试套件可能
    跑很久，期间外部 agent 若又改了 research.md，未经验证的内容会被当成
    最佳（best.json 却记录候选 id）；下一轮候选被拒时 _restore_best 会把
    这份未验证内容还原进研究循环，候选/最佳分离被破坏。
    """
    workspace, state_path = ws

    def judge(prompt):
        # 模拟评审员进程/测试套件跑动期间外部又改写了状态文件
        write_idea(state_path, "评审期间被外部改掉的内容")
        return True, "评分: 9"

    guard = make_guard(workspace, state_path, verify="ai", judge=judge)
    guard.start()
    write_idea(state_path, "被验证通过的候选")
    assert guard.on_round_end(1) == "adopted"
    cid = guard.best["id"]
    # best.md 必须与候选快照一致，而不是验证期间被改写的当前状态
    assert read_idea(guard.best_md) == "被验证通过的候选"
    assert read_idea(guard.dir / f"cand-{cid}.md") == "被验证通过的候选"

    # 端到端：下一轮更差的候选被拒后，还原到的是验证过的候选，而不是
    # 评审期间混进来的未验证内容
    guard2 = make_guard(workspace, state_path, verify="ai",
                        judge=lambda p: (True, "评分: 3"))
    guard2.start()
    write_idea(state_path, "更差的第二轮想法")
    assert guard2.on_round_end(2) == "rejected"
    assert read_idea(state_path) == "被验证通过的候选"


def test_ai_judge_prompt_shows_candidate_snapshot_not_live_state(ws, tmp_path):
    """AI 评审员看到的候选必须与晋升物一致（同为候选快照）。

    回归：_judge_prompt 原先重读 research.md 作为候选内容，而晋升
    （_adopt / _apply_user_verdicts）读的是 cand-<id>.md。测试套件与 AI
    评审串联时，套件跑动期间状态文件若被外部再改一次（后台进程收尾、
    用户手改、并发的另一实例），评审员给改后的实时内容打分，分却被用来
    采纳从未被验证过的快照内容——「评审的是 A、晋升的是 B」，候选/最佳
    分离的验证不变量被破坏。
    """
    workspace, state_path = ws
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    seen = {}

    def suite(suite_argv, repo_path, timeout):
        # 模拟套件运行期间外部又改写了状态文件（快照已落盘、评审未开始）
        write_idea(state_path, "套件运行期间被外部改掉的内容")
        return SuiteResult(available=False, reason="模拟套件不可用")

    def judge(prompt):
        seen["prompt"] = prompt
        return True, "评分: 9"

    guard = make_guard(workspace, state_path, verify="auto",
                       repo=str(repo), judge=judge, suite_runner=suite)
    guard.start()
    write_idea(state_path, "被快照的候选")
    assert guard.on_round_end(1) == "adopted"
    # 评审员必须看到快照内容，而不是套件期间的实时改动
    assert "被快照的候选" in seen["prompt"]
    assert "套件运行期间被外部改掉的内容" not in seen["prompt"]
    # 晋升的候选快照本身仍是唯一内容源
    assert read_idea(guard.best_md) == "被快照的候选"


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


def test_corrupt_markers_restored_even_when_best_sections_empty(ws):
    """最佳区块内容为空时，损坏的 research.md 依然必须被还原出标记行。

    回归：还原原先按 get_section 的字符串相等判断「无需还原」，而区块缺失
    与内容为空都读成 ""——最佳区块为空时损坏文件被误判为无需还原，之后
    每一轮都从无标记的坏文件出发，结构检查永远拒绝、循环再也回不到最佳。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    # 采纳一个两个区块都为空的最佳（agent 有权把区块覆盖为空）
    write_idea(state_path, "")
    write_artifact(state_path, "")
    assert guard.on_round_end(1) == "adopted"

    state_path.write_text("# 只剩标题，标记全没了\n", encoding="utf-8")
    assert guard.on_round_end(2) == "rejected"
    text = state_path.read_text(encoding="utf-8")
    # 标记行必须已修复（读取为空串而不是 None），内容与最佳一致
    assert state._first_section(text, state.SECTION_IDEA) == ""
    assert state._first_section(text, state.SECTION_ARTIFACT) == ""
    assert [e["event"] for e in events(guard)][-1] == "restored"


def test_late_adoption_writes_back_and_repairs_empty_sections(ws):
    """补评采纳的候选区块为空、且当前状态文件损坏时，仍要写回并修复结构。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "")
    write_artifact(state_path, "")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]

    # 候选挂起期间外部 agent 把当前状态文件的标记弄丢
    state_path.write_text("# 只剩标题，标记全没了\n", encoding="utf-8")
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 采纳\n", encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    text = state_path.read_text(encoding="utf-8")
    assert state._first_section(text, state.SECTION_IDEA) == ""
    assert state._first_section(text, state.SECTION_ARTIFACT) == ""


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


def test_detect_test_suite_make_suffixed_target_only_is_not_a_suite(tmp_path):
    """只有 test-unit / test-ci 之类后缀目标不算 make 套件：探测命中会执行
    `make test`，而 Makefile 并没有 test 目标、make 以退出码 2 失败，
    会被误判为「测试失败」拒绝候选（该场景应属「没有可运行套件」）。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text("test-unit:\n\techo unit\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_exact_target_alongside_suffixed(tmp_path):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test-unit:\n\techo unit\ntest:\n\techo ok\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


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


# ------------------------------------------ 套件运行的用户停止（q / Ctrl+C）
def _pid_dead(pid):
    for _ in range(10):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def test_run_suite_green_and_red(tmp_path):
    green = rounds.run_suite(
        [sys.executable, "-c", "print('ok')"], tmp_path, 30.0)
    assert (green.available, green.ok) == (True, True)
    assert "ok" in green.detail
    red = rounds.run_suite(
        [sys.executable, "-c", "import sys; print('bad'); sys.exit(3)"],
        tmp_path, 30.0)
    assert (red.available, red.ok) == (True, False)
    assert red.reason == "退出码 3"
    assert "bad" in red.detail


def test_run_suite_stop_terminates_suite_promptly(tmp_path):
    """用户停止（TUI 按 q / Ctrl+C）必须立即终止套件并返回未验证：
    修复前守卫会阻塞到 verify_timeout（默认 600s），run_tui 只等 20s，
    用户主动退出被误报成退出码 1，pytest 还作为孤儿继续跑。"""
    pid_file = tmp_path / "suite.pid"
    code = ("import os, time;"
            f"open({str(pid_file)!r}, 'w').write(str(os.getpid()));"
            "time.sleep(30)")
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] >= 2  # 套件确实拉起并跑过一个轮询周期后才停止

    t0 = time.monotonic()
    res = rounds.run_suite([sys.executable, "-c", code], tmp_path, 60.0,
                           stop=stop)
    assert time.monotonic() - t0 < 15.0
    assert res.available is False and res.stopped is True
    assert "用户" in res.reason
    assert pid_file.exists()  # 不是启动失败，而是被杀掉
    if os.name == "posix":
        assert _pid_dead(int(pid_file.read_text()))


def test_run_suite_unstartable_command(tmp_path):
    res = rounds.run_suite(["/nonexistent-xuen-suite-cmd"], tmp_path, 10.0)
    assert (res.available, res.stopped) == (False, False)
    assert res.reason == "测试命令无法启动"


def test_run_suite_timeout_kills_long_suite(tmp_path):
    pid_file = tmp_path / "suite.pid"
    code = ("import os, time;"
            f"open({str(pid_file)!r}, 'w').write(str(os.getpid()));"
            "time.sleep(30)")
    t0 = time.monotonic()
    res = rounds.run_suite([sys.executable, "-c", code], tmp_path, 0.5)
    assert time.monotonic() - t0 < 15.0
    assert (res.available, res.ok) == (True, False)
    assert "测试超时" in res.reason
    if os.name == "posix":
        assert _pid_dead(int(pid_file.read_text()))


def test_default_suite_runner_gets_stop_callback(ws, tmp_path, monkeypatch):
    """默认（未注入）运行器要拿到 sink.should_stop 回调，q 才能终止套件。"""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_ok.py").write_text("", encoding="utf-8")
    seen = {}

    def fake_run_suite(argv, repo_path, timeout, stop=None):
        seen["stop"] = stop
        return SuiteResult(available=True, ok=True, reason="exit 0")

    monkeypatch.setattr(rounds, "run_suite", fake_run_suite)
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="tests", repo=str(repo))
    guard.start()
    write_idea(state_path, "默认接缝也要可停止")
    assert guard.on_round_end(1) == "adopted"
    assert getattr(seen["stop"], "__self__", None) is guard.sink
    assert seen["stop"]() is False  # RecordingSink 默认不请求停止


def test_stopped_suite_does_not_fall_back_to_judge(ws, tmp_path, monkeypatch):
    """套件被用户停止后不能再拉起兜底评审：用户已经离开，新进程只会让
    run_tui 的等待再次超时、把主动退出误报成失败退出码。"""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_ok.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(
        rounds, "run_suite",
        lambda argv, repo_path, timeout, stop=None:
        SuiteResult(available=False, stopped=True, reason="用户请求停止，未验证"))
    called = {"judge": 0}

    def fake_judge(prompt):
        called["judge"] += 1
        return True, "评分: 9"

    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="auto", fallback="ai",
                       repo=str(repo), judge=fake_judge)
    guard.start()
    write_idea(state_path, "停止期间的候选")
    assert guard.on_round_end(1) == "pending"
    assert called["judge"] == 0


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


def test_auto_mode_make_without_exact_test_target_falls_back(ws, tmp_path):
    """Makefile 只有 test-unit 目标（无 test 目标）时不能因 `make test` 报
    错而拒绝候选：应视为没有可运行套件，转 auto 的兜底评分（ai）。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Makefile").write_text("test-unit:\n\techo unit only\n",
                                   encoding="utf-8")
    called = {"suite": 0}

    def fake_suite(argv, cwd, timeout):
        called["suite"] += 1
        return SuiteResult(available=True, ok=False, reason="退出码 2")

    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="auto", fallback="ai",
                       repo=str(repo), suite_runner=fake_suite,
                       judge=lambda p: (True, "评分: 8"))
    guard.start()
    write_idea(state_path, "想法")
    assert guard.on_round_end(1) == "adopted"
    assert guard.best["verifier"] == "ai"
    assert called["suite"] == 0


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


def test_pending_verdict_cashed_in_at_end_of_each_round(ws):
    """评分必须在每轮结束时兑现，而不是只等整个会话收尾。

    回归：_apply_user_verdicts 只在 start()/finish() 调用（文档承诺
    「守卫在每轮开始/结束时兑现」）。`iterations: inf` 的长循环里用户
    补分将永远等不到兑现，后续轮次也不会从重新采纳的最佳继续。修复后
    每轮结束兑现一次，且必须在【本轮快照与判定之后】：提前兑现会把旧
    候选写回 research.md、覆盖 agent 刚产出且尚未快照的本轮内容。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "第一轮的好想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    assert read_idea(state_path) == "（暂无）"

    # 用户在循环运行中补分（此时循环远未收尾）
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 采纳\n", encoding="utf-8")
    # 第二轮 agent 产出普通内容：本轮候选照常快照、判定、还原；
    # 随后本轮结束时的兑现把第一轮的好想法写回，成为下一轮起点
    write_idea(state_path, "第二轮的一般想法")
    assert guard.on_round_end(2) == "pending"
    assert guard.best["id"] == cid
    assert guard.best["verifier"] == "user"
    assert read_idea(state_path) == "第一轮的好想法"
    # 本轮候选先落盘（快照不因随后兑现的旧候选而丢失）
    assert len(cand_files(guard)) == 2
    kinds = [e["event"] for e in events(guard)]
    assert kinds[-2] == "verdict" and kinds[-1] == "restored"


def test_midloop_cashin_keeps_current_round_candidate_snapshot(ws):
    """每轮兑现旧评分不得吞掉本轮产物：快照必须先于兑现落盘。

    回归保护：若把兑现放在本轮判定【之前】，旧候选会先写回
    research.md，agent 刚产出的内容被覆盖且没有快照——违反 README
    「任何一轮的产物都落在 rounds/cand-<id>.md，永不丢失」。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "旧的好想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9\n", encoding="utf-8")

    write_idea(state_path, "本轮全新的想法")
    assert guard.on_round_end(2) == "pending"
    snaps = [p.read_text(encoding="utf-8")
             for p in sorted(guard.dir.glob("cand-*.md"))]
    assert any("本轮全新的想法" in s for s in snaps)


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


def test_late_verdict_moves_candidates_out_of_pending_stats(ws):
    """补分兑现必须同步迁移轮次统计。

    回归：_apply_user_verdicts 只晋升/记账、不更新 stats，导致同一会话里
    候选先计入「待评分」，被补分采纳/拒绝后仍留在待评分桶——finish()
    一边宣布「前进式晋升为最佳」，一边报「采纳 0 / 拒绝 0 / 待评分 N」。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "候选一")
    assert guard.on_round_end(1) == "pending"
    write_idea(state_path, "候选二")
    assert guard.on_round_end(2) == "pending"
    assert guard.stats.pending == 2
    ids = [e["id"] for e in events(guard) if e["event"] == "candidate"]
    (guard.dir / "verdicts.txt").write_text(
        f"{ids[0]} 9 采纳\n{ids[1]} 2\n", encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == ids[0]
    s = guard.stats
    # 一个挂起候选被采纳、一个被拒绝：桶数必须随改判迁移
    assert (s.adopted, s.rejected, s.pending) == (1, 1, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    # 晋升回写也是一次实际还原：与 history 里的 restored 事件一一对应
    assert s.restored == len([e for e in events(guard)
                              if e["event"] == "restored"])


def test_carryover_late_adoption_counted_in_finish(ws):
    """上一会话挂起的候选由新会话 start() 兑现补分时，汇总必须报告这次
    采纳，而不是「采纳 0」——那与本会话自己打印的「前进式晋升为最佳」
    日志自相矛盾；跨会话候选也绝不能把 pending 减成负数。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "被搁置的好想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9\n", encoding="utf-8")

    sink = RecordingSink()
    guard2 = make_guard(workspace, state_path, sink, verify="user")
    guard2.start()          # 新会话启动时兑现上轮遗留的补分
    assert guard2.best["id"] == cid
    assert guard2.stats.adopted == 1
    assert guard2.stats.pending == 0
    guard2.finish()
    summary = [m for _, m in sink.messages if "汇总" in m]
    assert summary and "采纳 1" in summary[-1]
    assert "采纳 0" not in summary[-1]


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


def test_verdicts_bom_tolerated(ws):
    """带 BOM 的评分行（Windows 记事本保存）不能静默失效。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "带 BOM 也要能翻案的想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    (guard.dir / "verdicts.txt").write_bytes(
        b"\xef\xbb\xbf" + f"{cid} 9 很好\n".encode("utf-8"))
    v = guard._read_verdicts()
    assert v[cid][0] == 9.0
    guard.finish()
    assert guard.best["id"] == cid
    assert guard.stats.adopted == 1


def test_unknown_verdict_cid_warns_once(ws):
    """抄错的候选 id 必须给出提示（且只提示一次），不能静默吞掉评分。"""
    workspace, state_path = ws
    sink = RecordingSink()
    guard = make_guard(workspace, state_path, sink, verify="user")
    guard.start()
    write_idea(state_path, "想法")
    assert guard.on_round_end(1) == "pending"
    (guard.dir / "verdicts.txt").write_text("20990101-000000-r1 9\n",
                                            encoding="utf-8")
    guard.finish()
    guard.finish()
    warns = [m for lvl, m in sink.messages if lvl == "warn" and "不存在" in m]
    assert len(warns) == 1


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


def test_user_verdict_malformed_line_pends_in_round(ws):
    """轮内就看到坏评分行时按挂起处理：解析不出 ≠ 用户拒绝。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    guard.dir.mkdir(parents=True, exist_ok=True)
    (guard.dir / "verdicts.txt").write_text("cand-x abc 手滑\n", encoding="utf-8")
    v = guard._user_verdict("cand-x")
    assert v.result == "pending" and v.score is None


def test_user_unparseable_score_stays_pending_and_can_be_fixed(ws):
    """评分行打错不能被当成拒绝：候选保持挂起，改好该行仍能翻案。

    回归：解析不出的用户评分若记成「已决」（rejected），用户修正这行
    后的正确评分会被 history 里的 verdict 事件永久挡住（resolved），
    旧快照再也无法前进式晋升——违反 README「解析不出按挂起处理」。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "值得补评的想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    # 手滑：分数写成了汉字（解析不出）
    (guard.dir / "verdicts.txt").write_text(f"{cid} 八分 手滑\n", encoding="utf-8")
    guard.finish()
    assert guard.best["round"] == 0
    # 没有产生任何「已决」结论，候选仍可翻案
    assert [e["result"] for e in events(guard) if e["event"] == "verdict"] \
        == ["pending"]
    # 修正这行后收尾兑现：旧候选前进式晋升
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 改好了\n", encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    assert guard.best["verifier"] == "user"
    assert read_idea(state_path) == "值得补评的想法"


def test_late_adoption_snapshot_unreadable_stays_pending(ws):
    """快照不可读时不能记「已决」：修复快照后仍能兑现晋升。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "快照待采纳")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    snap = guard.dir / f"cand-{cid}.md"
    saved = snap.read_text(encoding="utf-8")
    snap.unlink()
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9\n", encoding="utf-8")
    guard.finish()
    # 快照读不到：不采纳、也不记 adopted 事件把候选锁死
    assert guard.best["round"] == 0
    assert not [e for e in events(guard)
                if e["event"] == "verdict" and e.get("result") == "adopted"]
    # 快照恢复后再次兑现：正常晋升
    snap.write_text(saved, encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid


def test_late_adoption_best_write_failure_stays_pending(ws, monkeypatch):
    """最佳写盘失败时不能记「已决」：腾出磁盘后仍能兑现晋升。

    回归：_apply_user_verdicts 先写 verdict 事件再写 best.md/best.json。
    best 写盘抛 OSError（磁盘满 / 目录只读）时事件已把候选锁死——resolved
    集合此后永久跳过它（「应用失败稍后重试」不再可能），汇总还会虚报
    「采纳 1」而最佳仍是旧内容、research.md 也没写回。写盘成功前不能
    记已决事件、不能改判统计、不能改 self.best；与快照读取同一口径。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "写盘失败也要保住的想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 采纳\n", encoding="utf-8")

    real_write = rounds._atomic_write

    def boom(path, text):
        if Path(path).name == rounds.BEST_MD_NAME:
            raise OSError("磁盘满（模拟）")
        return real_write(path, text)

    monkeypatch.setattr(rounds, "_atomic_write", boom)
    guard.finish()  # 兑现失败：降级告警，候选保持挂起
    assert guard.best["round"] == 0
    assert guard.stats.adopted == 0
    assert guard.stats.pending == 1
    assert read_idea(state_path) == "（暂无）"
    assert not [e for e in events(guard)
                if e["event"] == "verdict" and e.get("result") == "adopted"]

    # 写盘恢复后再次兑现：同一评分必须还能兑现（候选没有被锁死）
    monkeypatch.setattr(rounds, "_atomic_write", real_write)
    guard.finish()
    assert guard.best["id"] == cid
    assert guard.best["verifier"] == "user"
    assert guard.stats.adopted == 1
    assert guard.stats.pending == 0
    assert read_idea(state_path) == "写盘失败也要保住的想法"


def test_adopted_round_best_write_failure_not_marked_resolved(ws, monkeypatch):
    """本轮采纳但 best 写盘失败：候选不能先被记成「已决」。

    回归：_process_round_end 先记 verdict(adopted) 事件、后调 _adopt 写
    best.md/best.json。写盘抛 OSError（磁盘满 / 目录只读）时事件已把候选
    锁死——_apply_user_verdicts 的 resolved 集合此后永久跳过它，用户腾出
    磁盘后补分也再翻不了案，审计日志还留下一条未兑现的 adopted。与
    _apply_user_verdicts 的修复同一口径：外部副作用成功前不能留下不可
    撤销的结论（不记已决事件、不改统计、不改 self.best）。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "写盘失败也要保住的想法")

    real_write = rounds._atomic_write

    def boom(path, text):
        if Path(path).name == rounds.BEST_MD_NAME:
            raise OSError("磁盘满（模拟）")
        return real_write(path, text)

    monkeypatch.setattr(rounds, "_atomic_write", boom)
    with pytest.raises(OSError):
        guard.on_round_end(1)
    assert guard.best["round"] == 0
    assert guard.stats.adopted == 0
    assert not [e for e in events(guard)
                if e["event"] == "verdict" and e.get("result") == "adopted"]

    # 写盘恢复后用补分通道仍能晋升：候选没有被那条未兑现的已决事件锁死
    monkeypatch.setattr(rounds, "_atomic_write", real_write)
    cid = [e for e in events(guard) if e["event"] == "candidate"][-1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 补分采纳\n",
                                            encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    assert guard.stats.adopted == 1
    assert read_idea(state_path) == "写盘失败也要保住的想法"


def test_partial_best_write_content_source_last(ws, monkeypatch):
    """best.md 先写成功、best.json 失败时，候选内容绝不能泄漏为还原源。

    回归：_adopt / _apply_user_verdicts 原来先写 best.md 再写 best.json。
    best.json 写盘失败（磁盘满 / 目录只读）时异常已抛出、self.best /
    统计 / best.json 都还指向旧最佳，但 best.md（_restore_best /
    _read_best_md 的唯一内容来源）已被替换成未经完整晋升的候选内容——
    下一轮候选被拒时还原的就是这份「未采纳」内容，候选/最佳分离被破坏。
    修复后内容源最后提交：best.json 失败时 best.md 原样不动。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    baseline_best = guard.best["id"]
    baseline_md = (guard.dir / rounds.BEST_MD_NAME).read_text(encoding="utf-8")
    write_idea(state_path, "不该泄漏成最佳的候选")

    real_write = rounds._atomic_write

    def boom(path, text):
        if Path(path).name == rounds.BEST_JSON_NAME:
            raise OSError("磁盘满（模拟）")
        return real_write(path, text)

    monkeypatch.setattr(rounds, "_atomic_write", boom)
    with pytest.raises(OSError):
        guard.on_round_end(1)
    assert guard.best["id"] == baseline_best
    assert guard.stats.adopted == 0
    # 内容源停在旧最佳：还原 / 心跳比较不会再看到候选内容
    assert (guard.dir / rounds.BEST_MD_NAME).read_text(
        encoding="utf-8") == baseline_md
    assert json.loads((guard.dir / rounds.BEST_JSON_NAME).read_text(
        encoding="utf-8"))["id"] == baseline_best
    assert not [e for e in events(guard)
                if e["event"] == "verdict" and e.get("result") == "adopted"]

    # 写盘恢复后候选仍可被补分采纳（没有被半截提交锁死）
    monkeypatch.setattr(rounds, "_atomic_write", real_write)
    cid = [e for e in events(guard) if e["event"] == "candidate"][-1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 补分采纳\n",
                                            encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    assert read_idea(state_path) == "不该泄漏成最佳的候选"


def test_partial_best_md_failure_keeps_content_and_rolls_back_json(
        ws, monkeypatch):
    """best.json 先落盘、best.md 失败：元数据要回滚，内容源保持旧最佳。

    反序提交下 best.json 已成功而 best.md 失败时，如果放任元数据超前，
    重启后的 _load_best 会把「最佳」指向一份内容仍旧的快照，汇总与还原
    自相矛盾。修复后 md 失败即回滚 json 指针，两个文件重新一致。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    baseline_best = guard.best["id"]
    baseline_md = (guard.dir / rounds.BEST_MD_NAME).read_text(encoding="utf-8")
    write_idea(state_path, "md 写盘失败也要保住的候选")

    real_write = rounds._atomic_write

    def boom(path, text):
        if Path(path).name == rounds.BEST_MD_NAME:
            raise OSError("磁盘满（模拟）")
        return real_write(path, text)

    monkeypatch.setattr(rounds, "_atomic_write", boom)
    with pytest.raises(OSError):
        guard.on_round_end(1)
    # 内容源没有被候选污染；元数据回滚为旧指针，两个文件仍相互一致
    assert (guard.dir / rounds.BEST_MD_NAME).read_text(
        encoding="utf-8") == baseline_md
    assert json.loads((guard.dir / rounds.BEST_JSON_NAME).read_text(
        encoding="utf-8"))["id"] == baseline_best
    assert guard.best["id"] == baseline_best
    assert guard.stats.adopted == 0


def test_late_adoption_partial_best_failure_keeps_content(ws, monkeypatch):
    """补分采纳的 best 写盘中途失败：未采纳的候选内容不得流进还原源。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    baseline_md = (guard.dir / rounds.BEST_MD_NAME).read_text(encoding="utf-8")
    write_idea(state_path, "待评分的候选")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9\n", encoding="utf-8")

    real_write = rounds._atomic_write

    def boom(path, text):
        if Path(path).name == rounds.BEST_MD_NAME:
            raise OSError("磁盘满（模拟）")
        return real_write(path, text)

    monkeypatch.setattr(rounds, "_atomic_write", boom)
    guard.finish()
    assert guard.best["round"] == 0
    assert guard.stats.adopted == 0
    assert guard.stats.pending == 1
    assert read_idea(state_path) == "（暂无）"
    assert (guard.dir / rounds.BEST_MD_NAME).read_text(
        encoding="utf-8") == baseline_md
    assert not [e for e in events(guard)
                if e["event"] == "verdict" and e.get("result") == "adopted"]

    # 写盘恢复后同一评分再次兑现：内容源与元数据一起切换
    monkeypatch.setattr(rounds, "_atomic_write", real_write)
    guard.finish()
    assert guard.best["id"] == cid
    assert guard.stats.adopted == 1
    assert read_idea(state_path) == "待评分的候选"


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
def test_candidate_snapshot_collision_gets_suffix(ws):
    """同 id 快照已存在时原子创建必须换名，绝不覆盖旧快照。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.dir.mkdir(parents=True, exist_ok=True)
    id1 = guard._snapshot_candidate(1, "第一份")
    id2 = guard._snapshot_candidate(1, "第二份")
    assert id1 != id2
    assert (guard.dir / f"cand-{id1}.md").read_text(
        encoding="utf-8") == "第一份"
    assert (guard.dir / f"cand-{id2}.md").read_text(
        encoding="utf-8") == "第二份"


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
