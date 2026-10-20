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


def test_ai_snapshot_deleted_during_judge_stays_pending(ws):
    """验证期间快照被删除：绝不能拿未验证的实时状态顶替晋升。

    回归：_read_candidate_text 在快照不可读时退回 research.md，导致
    AI 评审期间被删掉的候选仍可能把外部改过的实时内容写成最佳，破坏
    候选/最佳分离；原始候选恢复后也无从翻案（已被记成 adopted）。
    """
    workspace, state_path = ws
    saved = {}

    def judge(prompt):
        snap = next(guard.dir.glob(f"{rounds.CAND_PREFIX}*.md"))
        saved["path"] = snap
        saved["text"] = snap.read_text(encoding="utf-8")
        snap.unlink()
        write_idea(state_path, "评审期间混进来的未验证内容")
        return True, "评分: 9"

    guard = make_guard(workspace, state_path, verify="ai", judge=judge)
    guard.start()
    write_idea(state_path, "被验证通过的候选")
    # 与现有 _adopt 失败口径一致：挂起记账后异常上抛，由 runner 降级处理
    with pytest.raises(OSError):
        guard.on_round_end(1)
    # 最佳没有被未验证内容污染，候选也没有被记成已决
    assert guard.best["round"] == 0
    assert read_idea(guard.best_md) == "（暂无）"
    assert not [e for e in events(guard)
                if e["event"] == "verdict" and e.get("result") == "adopted"]
    assert guard.stats.pending == 1
    assert guard.stats.candidates == 1
    # 快照恢复后补分仍能翻案：严格读取让原候选可继续兑现
    saved["path"].write_text(saved["text"], encoding="utf-8")
    cid = saved["path"].stem[len(rounds.CAND_PREFIX):]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 恢复后采纳\n",
                                            encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    assert read_idea(state_path) == "被验证通过的候选"


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


def test_late_adoption_tolerates_non_int_round_in_history(ws):
    """history 里合法 JSON 但 round 类型损坏（字符串/布尔）时，补评采纳
    仍要兑现，且写出的 best 元数据不能带坏字段。

    回归：_recover_best / _valid_best 对 round 有真整数校验（专门防的正是
    finish() 的 `best["round"] > 0` TypeError），但 _apply_user_verdicts
    直接采信历史行的 round——字符串会被写进 best.json：finish() 抛
    TypeError、汇总整段丢失，下次启动还会因 _valid_best 拒绝而跳过该采纳
    事件、把最佳回退到更早的记录。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "等待补评的想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]

    # 模拟审计日志被外部编辑/旧版本写入：合法 JSON、round 却是字符串
    lines = guard.history_path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        ev = json.loads(ln)
        if ev.get("event") == "candidate" and ev.get("id") == cid:
            ev["round"] = "1"
            lines[i] = json.dumps(ev, ensure_ascii=False)
    guard.history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 采纳\n", encoding="utf-8")
    guard.finish()  # 修复前：'str' 与 'int' 比较抛 TypeError
    assert guard.best["id"] == cid
    assert guard.best["round"] == 0
    # best.json 必须能被 _valid_best 接受：重启后最佳元数据不丢失
    assert rounds._valid_best(json.loads(
        guard.best_json.read_text(encoding="utf-8")))
    summary = [m for lvl, m in guard.sink.messages if "汇总" in m]
    assert summary and cid in summary[-1]


def test_history_non_string_id_does_not_break_verdict_cashin(ws):
    """history 事件的 id 类型损坏（合法 JSON 的列表/对象）时，补分兑现
    与汇总不能整体崩溃。

    回归：_apply_user_verdicts 直接把历史行的 id 当 dict/set 的键，非
    字符串（unhashable）会抛 TypeError，让 start()/finish() 的补分兑现
    失败（守卫降级、汇总丢失）。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "等待补评的想法")
    assert guard.on_round_end(1) == "pending"
    cid = [e for e in events(guard)
           if e.get("event") == "candidate"][-1]["id"]

    lines = guard.history_path.read_text(encoding="utf-8").splitlines()
    lines.insert(1, json.dumps({"event": "candidate", "id": ["idea"],
                                "round": 1}, ensure_ascii=False))
    guard.history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 采纳\n", encoding="utf-8")

    guard.finish()  # 修复前：TypeError: unhashable type: 'list'
    assert guard.best["id"] == cid
    summary = [m for lvl, m in guard.sink.messages if "汇总" in m]
    assert summary and cid in summary[-1]


def test_history_verdict_with_missing_result_does_not_lock_candidate(ws):
    """history 里合法 JSON 但缺 result / result 未知的 verdict 事件不能把
    候选当成已决。

    回归：_apply_user_verdicts 以 `result != "pending"` 判定已决——缺字段
    （None）或外部写入的未知值都会把候选永久锁死，之后用户评多少分都
    被 resolved 集合跳过。只有 adopted / rejected 才是真正下了结论。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "坏事件不能锁死的候选")
    assert guard.on_round_end(1) == "pending"
    cid = [e for e in events(guard)
           if e.get("event") == "candidate"][-1]["id"]

    with open(guard.history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "verdict", "id": cid}) + "\n")
        f.write(json.dumps({"event": "verdict", "id": cid,
                            "result": "unknown"}) + "\n")
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 采纳\n", encoding="utf-8")

    guard.finish()
    assert guard.best["id"] == cid
    assert guard.stats.adopted == 1
    results = [e.get("result") for e in events(guard)
               if e.get("event") == "verdict" and e.get("id") == cid]
    assert results[-1] == "adopted"
    assert results.count("adopted") == 1


# ---------------------------------------------------------------- 测试级联
def test_detect_test_suite_pytest(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    suite = detect_test_suite(tmp_path)
    assert suite is not None and "pytest" in suite


@pytest.mark.parametrize("relpath", [
    "src/pkg/tests/test_deep.py",
    "src/pkg/tests/deep_test.py",
    "tests/unit/test_nested.py",
])
def test_detect_test_suite_pytest_nested(tmp_path, relpath):
    """pytest 文件在任意子目录（src/pkg/tests/ 等标准布局）也要探测到。

    回归：只查仓库根和 tests/ 会把 `src/pkg/tests/test_x.py` 这类嵌套
    套件当成没有测试，候选永远无法通过测试验证。"""
    path = tmp_path / relpath
    path.parent.mkdir(parents=True)
    path.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    suite = detect_test_suite(tmp_path)
    assert suite is not None and "pytest" in suite


def test_detect_test_suite_pytest_directory_named_like_test_file(tmp_path):
    """目录名恰好是 test_x.py / x_test.py 不是测试文件。

    回归：glob 同时返回目录，旧探测会把空目录当成 pytest 套件，随后
    `pytest -q` 没有可收集文件、以退出码 5 失败，候选被误判为测试失败。"""
    (tmp_path / "test_not_a_file.py").mkdir()
    nested = tmp_path / "tests" / "pkg_test.py"
    nested.mkdir(parents=True)
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_pytest_ignores_uncollected_dirs(tmp_path):
    """pytest 默认不收集的目录里的测试不能被当成本仓库的套件。

    虚拟环境、依赖目录、build/dist 与点目录里的第三方/生成测试都不会被
    `pytest -q` 收集；按它们探测会得到假阳性，随后 pytest 以退出码 5
    失败，候选被误判为测试失败。"""
    for relpath in ("node_modules/dep/test_dep.py", ".venv/lib/test_env.py",
                    ".hidden/test_hidden.py", "build/test_build.py",
                    "dist/test_dist.py"):
        path = tmp_path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


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


@pytest.mark.parametrize("line", [
    "test := x",
    "test::= x",
    "test:::= x",
    "test : = x",
    "test ?= x",
    "test += x",
    "test != echo x",
    "test = x",
])
def test_detect_test_suite_make_variable_assignment_is_not_a_suite(tmp_path,
                                                                   line):
    """变量赋值行不是 test 目标：`make test` 会以退出码 2 失败，探测命中
    会被误判为「测试失败」拒绝候选（应属「没有可运行套件」）。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(line + "\nall:\n\t@echo hi\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "test:",
    "test::",
    "test :",
    " test:",
    "test:; echo ok",
    "test: dep",
])
def test_detect_test_suite_make_target_forms_still_detected(tmp_path, line):
    """真正的 test 目标（含双冒号规则、前导空格、同行命令）仍要探测到。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(line + "\n\techo ok\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


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


def _fake_go(monkeypatch):
    real_which = shutil.which

    def which(name, *args, **kwargs):
        if name == "go":
            return "/usr/bin/go"
        return real_which(name, *args, **kwargs)

    monkeypatch.setattr("xuen.rounds.shutil.which", which)


def test_detect_test_suite_go_nested_module(tmp_path, monkeypatch):
    """go.mod 模块的包在子目录（cmd/、internal/ 等）时也要探测到：
    `go test ./...` 从仓库根可运行，只查根目录 *.go 会漏掉标准布局。"""
    _fake_go(monkeypatch)
    (tmp_path / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")
    pkg = tmp_path / "internal" / "store"
    pkg.mkdir(parents=True)
    (pkg / "store.go").write_text("package store\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["go", "test", "./..."]


def test_detect_test_suite_go_mod_without_packages_not_a_suite(
        tmp_path, monkeypatch):
    """只有 go.mod、没有任何 .go 文件时 `go test ./...` 会报无包可用，
    不能探测成套件并让探测失败被记成测试失败。"""
    _fake_go(monkeypatch)
    (tmp_path / "go.mod").write_text("module example.com/empty\n",
                                     encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_go_directories_named_like_source(tmp_path,
                                                           monkeypatch):
    """目录名以 .go 结尾不是 Go 源文件，不能探测成套件。"""
    _fake_go(monkeypatch)
    (tmp_path / "not_a_file.go").mkdir()
    (tmp_path / "go.mod").write_text("module example.com/demo\n",
                                     encoding="utf-8")
    nested = tmp_path / "internal" / "also_not_a_file.go"
    nested.mkdir(parents=True)
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


def test_run_suite_does_not_inherit_stdin(tmp_path):
    """套件不得继承 xuen 的 stdin（外部 agent 早已用 DEVNULL 隔离）。

    回归：TUI 模式下 textual 从 stdin 读键盘，测试套件若继承同一 stdin，
    测试里的 input()/read() 会抢走按键（或一直等不到输入，守卫挂到
    verify_timeout）。"""
    if os.name != "posix":
        pytest.skip("只在 POSIX 上构造带数据的父进程 stdin")
    # 把带数据的管道 dup 到 fd 0：子进程若继承 stdin，read() 会拿到
    # b"keystrokes" 并以 5 退出；DEVNULL 下 read() 得空串、以 0 退出
    r, w = os.pipe()
    os.write(w, b"keystrokes")
    os.close(w)
    saved = os.dup(0)
    try:
        os.dup2(r, 0)
        os.close(r)
        res = rounds.run_suite(
            [sys.executable, "-c",
             "import sys; sys.exit(5 if sys.stdin.read() else 0)"],
            tmp_path, 30.0)
    finally:
        os.dup2(saved, 0)
        os.close(saved)
    assert (res.available, res.ok) == (True, True)


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


class StopSink(RecordingSink):
    def should_stop(self):
        return True


def test_stop_before_verification_spawns_no_suite_or_judge(ws, monkeypatch):
    """用户停止后不得再拉起测试套件/AI 评审：候选直接挂起。

    回归：套件运行期间的停止已有回调，但停止标志在进入验证时若已为真，
    verify=ai（或 auto 无套件 + fallback=ai）仍会启动评审进程，跑满
    judge_timeout；run_tui 只等 20s，主动退出会被误报成退出码 1，评审
    进程还会成为孤儿。"""
    called = {"suite": 0, "judge": 0, "detect": 0}

    def fake_suite(*args, **kwargs):
        called["suite"] += 1
        return SuiteResult(available=True, ok=True, reason="exit 0")

    def fake_judge(prompt):
        called["judge"] += 1
        return True, "评分: 9"

    def fake_detect(repo_path):
        called["detect"] += 1
        return [sys.executable, "-c", "pass"]

    monkeypatch.setattr(rounds, "detect_test_suite", fake_detect)
    workspace, state_path = ws

    for index, (verify, fallback) in enumerate(
            (("ai", "ai"), ("tests", "ai"), ("auto", "ai")), start=1):
        guard = make_guard(workspace, state_path, StopSink(),
                           verify=verify, fallback=fallback,
                           judge=fake_judge, suite_runner=fake_suite)
        guard.start()
        write_idea(state_path, f"停止期间的候选 {index}")
        assert guard.on_round_end(index) == "pending"
        assert guard.stats.pending == 1
    assert called == {"suite": 0, "judge": 0, "detect": 0}


def test_stop_after_verify_check_before_judge_run_skips_process(ws, monkeypatch):
    """停止请求落在验证检查与评审启动之间时也不能拉起评审进程。

    回归：_verify 先检查 should_stop，随后 _run_judge 才把评审员挂到
    sink.agent；TUI 的 q 恰好落在这段窗口里时 stop_agent 杀的是已结束的
    主 agent，评审仍会启动并跑满 judge_timeout。"""
    workspace, state_path = ws

    class LateStopSink(RecordingSink):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def should_stop(self):
            self.calls += 1
            return self.calls >= 2

    created = {}

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            created["agent"] = self
            self.run_called = False

        def run(self, prompt):
            self.run_called = True
            return "评分: 9"

    monkeypatch.setattr(rounds, "ShellAgent", FakeAgent)
    sink = LateStopSink()
    guard = make_guard(workspace, state_path, sink, verify="ai")
    guard.start()
    write_idea(state_path, "竞态窗口候选")
    assert guard.on_round_end(1) == "pending"
    assert created["agent"].run_called is False
    assert sink.agent is None


def test_run_suite_stop_before_start_does_not_spawn(tmp_path):
    """停止标志在套件启动前已为真时，不应先拉起测试进程再等 0.2s 轮询。"""
    marker = tmp_path / "spawned"
    code = f"open({str(marker)!r}, 'w').write('x')"
    res = rounds.run_suite([sys.executable, "-c", code], tmp_path, 30.0,
                           stop=lambda: True)
    assert (res.available, res.stopped) == (False, True)
    assert not marker.exists()


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


def test_verdicts_unicode_line_separator_in_comment_not_split(ws):
    """评语里的 U+2028/U+2029/U+0085 不能把一行评分切成两行。

    回归：_read_verdicts 用 str.splitlines()，这些 Unicode 行分隔符也是
    行边界；评语后半段若恰以「cid 分数」开头，就会被解析成一条凭空出现
    的伪评分（把无关候选按用户没写过的分数采纳/拒绝），与 _read_events
    换成 ASCII 换行切分是同一类问题。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    for sep in ("\u2028", "\u2029", "\x85"):
        (guard.dir / "verdicts.txt").write_text(
            f"cand-a 9 很好{sep}cand-b 0 差\n", encoding="utf-8")
        v = guard._read_verdicts()
        assert v["cand-a"][0] == 9.0
        assert f"cand-b 0 差" in v["cand-a"][1]
        # 评语里的 cand-b 不能变成一条独立评分
        assert "cand-b" not in v


def test_parse_score_full_caps_score_keyword():
    """英文模式要像中英文那样容忍大小写：AI 评审员输出 "SCORE:" 时
    不能解析不出分数而把候选永久挂起（"Score:"/"score:" 一直可用）。"""
    assert parse_score("SCORE: 8.5") == 8.5
    assert parse_score("SCORE：7") == 7.0
    assert parse_score("评语\nTotal SCORE: 9") == 9.0
    assert parse_score("sCoRe: 10") == 10.0


def test_last_comment_excludes_full_caps_score_line():
    """_last_comment 同一套模式：全大写 SCORE 行也不该被当评语展示。"""
    text = "第一行评语\nSCORE: 8"
    assert rounds._last_comment(text) == "第一行评语"


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


def test_verdicts_encoding_corrupt_line_keeps_other_lines(ws):
    """verdicts.txt 里夹着非法 UTF-8 字节（非 UTF-8 编辑器保存 / 粘贴
    损坏）时，其余评分行必须照常生效。

    回归：_read_verdicts 整体 read_text 解码失败即返回 {}，cid 与分数
    这类纯 ASCII 列完好也会被一并静默忽略——用户以为评分已提交，候选
    永远等不到兑现。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "带坏字节的评分文件")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    guard.verdicts_path.write_bytes(
        f"{cid} 9 很好\n".encode("utf-8")
        + b"\xff\xfe broken line\n"
        + b"other-cid 3\n")
    v = guard._read_verdicts()
    assert v[cid][0] == 9.0
    assert v["other-cid"][0] == 3.0
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


def test_unparseable_verdict_warns_once_per_cid(ws):
    """评分解析不出的警告每个候选 id 只打一次（与未知 id 同口径）。

    回归：_apply_user_verdicts 在每轮开始/结束都会兑现，inf 循环里同一行
    坏评分会每轮重复刷警告，淹没真正的循环输出。
    """
    workspace, state_path = ws
    sink = RecordingSink()
    guard = make_guard(workspace, state_path, sink, verify="user")
    guard.start()
    write_idea(state_path, "想法")
    assert guard.on_round_end(1) == "pending"
    cid = [e for e in events(guard)
           if e.get("event") == "candidate"][-1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 八分 手滑\n",
                                            encoding="utf-8")
    for _ in range(3):
        guard.finish()
    badscore = [m for lvl, m in sink.messages
                if lvl == "warn" and "无法解析" in m]
    assert len(badscore) == 1
    # 仍是挂起：坏行不产生「已决」结论
    assert [e["result"] for e in events(guard) if e["event"] == "verdict"] \
        == ["pending"]


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


def test_adopt_failure_records_pending_stats_and_verdict(ws, monkeypatch):
    """晋升写盘失败：候选必须计入「待评分」，汇总不能自相矛盾。

    回归：_process_round_end 先记候选事件、后调 _adopt；_adopt 抛
    OSError（best 写盘失败 / 快照损坏）时该轮既无 pending 也无
    adopted/rejected 事件，stats 出现「候选 1、采纳/拒绝/待评分全 0」
    ——违反 adopted+rejected+pending==candidates，待评分候选数也失真。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "晋升写盘失败也要挂在待评分")
    real_write = rounds._atomic_write

    def boom(path, text):
        if Path(path).name == rounds.BEST_MD_NAME:
            raise OSError("磁盘满（模拟）")
        return real_write(path, text)

    monkeypatch.setattr(rounds, "_atomic_write", boom)
    with pytest.raises(OSError):
        guard.on_round_end(1)

    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending) == (1, 0, 0, 1)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert guard.best["round"] == 0
    assert read_idea(state_path) == "（暂无）"
    # 挂起结论也要落审计日志（候选有对应 verdict 事件），但不能是 adopted
    cid = [e["id"] for e in events(guard) if e["event"] == "candidate"][-1]
    verdicts = [e for e in events(guard) if e["event"] == "verdict"]
    assert [v for v in verdicts if v.get("result") == "adopted"] == []
    pending = [v for v in verdicts if v.get("result") == "pending"]
    assert pending and pending[-1]["id"] == cid

    # 写盘恢复后补分仍能兑现：pending 迁移到 adopted，不变式仍成立
    monkeypatch.setattr(rounds, "_atomic_write", real_write)
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9\n", encoding="utf-8")
    guard.finish()
    s = guard.stats
    assert (s.adopted, s.pending) == (1, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert read_idea(state_path) == "晋升写盘失败也要挂在待评分"


def test_snapshot_write_failure_not_counted_as_candidate(ws, monkeypatch):
    """候选快照写盘失败时不能先计入候选：该轮没有可评分的产物。

    回归：_process_round_end 先 `stats.candidates += 1` 再调用
    _snapshot_candidate；磁盘满/目录只读导致快照失败时异常虽由
    runner 降级，但统计里留下一个没有 adopted/rejected/pending 的
    候选，汇总违反 adopted+rejected+pending==candidates。候选快照
    失败应按跳过记账并还原最佳，不能留下半截候选。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "快照写盘失败的想法")

    def boom(*args, **kwargs):
        raise OSError("磁盘满（模拟）")

    monkeypatch.setattr(guard, "_snapshot_candidate", boom)
    with pytest.raises(OSError):
        guard.on_round_end(1)

    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending, s.skipped) \
        == (0, 0, 0, 0, 1)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert guard.best["round"] == 0
    assert read_idea(state_path) == "（暂无）"
    evs = events(guard)
    assert not [e for e in evs if e["event"] == "candidate"]
    assert [e for e in evs if e["event"] == "skipped"][-1]["round"] == 1


def test_interrupt_during_candidate_event_keeps_candidate_pending(ws, monkeypatch):
    """中断落在候选事件写盘时，快照已落盘就必须按待评分记账。

    回归：快照成功后写事件时收到 KeyboardInterrupt，except Exception
    捕不到；统计里留下一个没有 adopted/rejected/pending 的候选，汇总
    违反 adopted+rejected+pending==candidates，快照也因缺少 candidate
    事件无法被 verdicts.txt 补分。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    write_idea(state_path, "中断时的候选")
    real_append = guard._append_event
    raised = {"done": False}

    def flaky(ev):
        if ev.get("event") == "candidate" and not raised["done"]:
            raised["done"] = True
            raise KeyboardInterrupt
        return real_append(ev)

    monkeypatch.setattr(guard, "_append_event", flaky)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)

    s = guard.stats
    assert (s.candidates, s.pending, s.adopted, s.rejected) == (1, 1, 0, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    cids = [e["id"] for e in events(guard) if e["event"] == "candidate"]
    assert len(cids) == 1
    assert cids[0] in guard._pending_ids
    assert read_idea(state_path) == "（暂无）"


def test_interrupt_during_corrupt_candidate_event_keeps_stats_consistent(
        ws, monkeypatch):
    """结构损坏分支同样不能在中断时留下没有结论的候选。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    state_path.write_text("# 区块标记全丢了\n", encoding="utf-8")
    real_append = guard._append_event
    raised = {"done": False}

    def flaky(ev):
        if ev.get("event") == "candidate" and not raised["done"]:
            raised["done"] = True
            raise KeyboardInterrupt
        return real_append(ev)

    monkeypatch.setattr(guard, "_append_event", flaky)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)

    s = guard.stats
    assert (s.candidates, s.pending, s.adopted, s.rejected) == (1, 1, 0, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert guard.best["round"] == 0
    assert state.get_section(state_path.read_text(encoding="utf-8"),
                             state.SECTION_IDEA) == "（暂无）"


def test_interrupt_during_snapshot_rolls_back_candidate(ws, monkeypatch):
    """快照本身被中断（没有留下任何文件）时要回滚候选计数。

    回归：候选计数在调用 _snapshot_candidate 之前 +1，中断落在快照
    写盘时没有 cid 可挂起；回滚 candidates 并按跳过记账后，摘要才
    不会出现「候选 1、采纳/拒绝/待评分全 0」。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "快照被中断的想法")

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(guard, "_snapshot_candidate", interrupted)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)
    # runner 的中断路径：已处理轮次只补做还原，不再重复记账
    guard.on_round_failed(1, "被中断，轮次未完成")

    s = guard.stats
    assert (s.rounds, s.candidates, s.skipped, s.pending) == (1, 0, 1, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert not [e for e in events(guard) if e["event"] == "candidate"]
    assert guard.best["round"] == 0
    assert read_idea(state_path) == "（暂无）"


def test_interrupt_during_corrupt_snapshot_rolls_back_candidate(ws, monkeypatch):
    """结构损坏分支的快照被中断时同样回滚候选计数。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    state_path.write_text("# 区块标记全丢了\n", encoding="utf-8")

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(guard, "_snapshot_candidate", interrupted)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)
    guard.on_round_failed(1, "被中断，轮次未完成")

    s = guard.stats
    assert (s.rounds, s.candidates, s.skipped, s.pending) == (1, 0, 1, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert not [e for e in events(guard) if e["event"] == "candidate"]
    assert guard.best["round"] == 0


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


def test_restore_recovers_best_from_snapshot_when_best_md_deleted(ws):
    """best.md 被外部删除后还原不能把脚手架写回 research.md。

    回归：_read_best_md 读不到 best.md 时退回基线脚手架，候选被拒绝 /
    挂起触发的还原会把「（暂无）」覆盖到 research.md——当前最佳的完整
    内容明明还躺在 cand-<最佳id>.md 快照里（best.json 也指向它）。
    修复：按最佳 id 从候选快照找回内容并回写 best.md（自愈）。
    """
    workspace, state_path = ws
    sink = RecordingSink()
    guard = make_guard(workspace, state_path, sink, verify="off")
    guard.start()
    write_idea(state_path, "第一轮晋升的最佳")
    write_artifact(state_path, "第一轮晋升的产物")
    assert guard.on_round_end(1) == "adopted"
    cid = guard.best["id"]

    (guard.dir / rounds.BEST_MD_NAME).unlink()
    write_idea(state_path, "尚未验证的第二轮候选")
    guard.cfg.rounds.verify = "user"
    assert guard.on_round_end(2) == "pending"

    # 还原到第一轮的最佳内容，而不是脚手架的「（暂无）」
    assert read_idea(state_path) == "第一轮晋升的最佳"
    assert state.get_section(state_path.read_text(encoding="utf-8"),
                             state.SECTION_ARTIFACT) == "第一轮晋升的产物"
    # best.md 自愈回写，内容与快照一致；元数据仍指向同一候选
    assert read_idea(guard.best_md) == "第一轮晋升的最佳"
    assert guard.best["id"] == cid
    assert any("从候选快照恢复" in m
               for lvl, m in sink.messages if lvl == "warn")


def test_restore_recovers_best_from_snapshot_when_best_md_corrupt(ws):
    """best.md 结构损坏（被截断 / 篡改）时同样从候选快照找回内容。"""
    workspace, state_path = ws
    sink = RecordingSink()
    guard = make_guard(workspace, state_path, sink, verify="off")
    guard.start()
    write_idea(state_path, "第一轮晋升的最佳")
    assert guard.on_round_end(1) == "adopted"
    cid = guard.best["id"]

    guard.best_md.write_text("被外部截断的垃圾内容，没有区块标记",
                             encoding="utf-8")
    write_idea(state_path, "尚未验证的第二轮候选")
    guard.cfg.rounds.verify = "user"
    assert guard.on_round_end(2) == "pending"

    assert read_idea(state_path) == "第一轮晋升的最佳"
    assert read_idea(guard.best_md) == "第一轮晋升的最佳"
    assert guard.best["id"] == cid


def test_missing_best_md_without_snapshot_falls_back_to_scaffold(ws):
    """快照也丢失时退回原口径：按脚手架处理，而不是抛异常。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "晋升过的最佳")
    assert guard.on_round_end(1) == "adopted"
    cid = guard.best["id"]
    (guard.dir / rounds.BEST_MD_NAME).unlink()
    (guard.dir / f"{rounds.CAND_PREFIX}{cid}.md").unlink()

    text = guard._read_best_md()
    assert state.get_section(text, state.SECTION_IDEA) == "（暂无）"


def test_corrupt_best_md_without_snapshot_falls_back_to_scaffold(ws):
    """best.md 损坏且无候选快照（基线）时按脚手架处理，不返回损坏文本。

    缺失分支早已如此；损坏分支若直接返回原文，_restore_best 会把损坏
    区块当成空内容写回 research.md（而不是脚手架的「暂无」），且损坏
    内容会被当作最佳继续比较。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    assert guard.best["round"] == 0
    guard.best_md.write_text("被外部篡改的垃圾内容，没有区块标记",
                             encoding="utf-8")

    text = guard._read_best_md()
    assert state.get_section(text, state.SECTION_IDEA) == "（暂无）"
    assert state.get_section(text, state.SECTION_ARTIFACT) == "（暂无）"


def test_start_recovers_best_from_snapshot_when_best_md_deleted(ws):
    """重启时 best.md 缺失：从 best.json 指向的候选快照恢复，而不是以
    当前 research.md 重建基线（那会把旧最佳悄悄降级为新基线）。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    baseline_events = [e for e in events(guard) if e["event"] == "baseline"]
    write_idea(state_path, "晋升过的最佳")
    assert guard.on_round_end(1) == "adopted"
    cid = guard.best["id"]
    (guard.dir / rounds.BEST_MD_NAME).unlink()

    sink = RecordingSink()
    restarted = make_guard(workspace, state_path, sink, verify="off")
    restarted.start()
    assert restarted.best["id"] == cid
    assert read_idea(restarted.best_md) == "晋升过的最佳"
    assert read_idea(state_path) == "晋升过的最佳"
    # 没有因为 best.md 缺失而补记新的基线事件
    assert [e for e in events(restarted)
            if e["event"] == "baseline"] == baseline_events
    assert any("从候选快照恢复" in m
               for lvl, m in sink.messages if lvl == "warn")


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


def test_snapshot_interrupted_write_leaves_no_partial_file(ws, monkeypatch):
    """快照写到一半被 KeyboardInterrupt 打断时不能留下半截文件。

    回归：_snapshot_candidate 只在 OSError 时清理，except Exception
    捕不到中断/SystemExit；半截快照会永久占住 id，后续同轮快照被迫
    加序号，而且「快照可读」检查会把坏内容当成合法候选。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    real_open = open
    prefix = str(guard.dir / "cand-")

    class InterruptedFile:
        def __init__(self, path, mode, *args, **kwargs):
            self.inner = real_open(path, mode, *args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.inner.close()

        def write(self, text):
            raise KeyboardInterrupt

    def flaky_open(path, mode="r", *args, **kwargs):
        if str(path).startswith(prefix) and "x" in mode:
            return InterruptedFile(path, mode, *args, **kwargs)
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", flaky_open)
    with pytest.raises(KeyboardInterrupt):
        guard._snapshot_candidate(1, "只写了一半")
    assert not list(guard.dir.glob("cand-*.md"))

    monkeypatch.setattr("builtins.open", real_open)
    cid = guard._snapshot_candidate(1, "完整快照")
    assert [p.name for p in guard.dir.glob("cand-*.md")] == [f"cand-{cid}.md"]


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


# ------------------------------------------- best.json 外部丢失/损坏的恢复
def test_best_json_lost_recovers_metadata_from_history(ws):
    """best.json 被外部删除/损坏时，从 history 的最后一条基线/采纳事件
    恢复最佳元数据并回写。

    回归：修复前 _load_best 返回 {'id': 'unknown', 'round': -1} 且不补
    baseline 事件；拒绝与挂起轮次不会更新 best，汇总与评审提示词会永久
    停在「当前最佳：unknown」——只能等一次采纳才能自愈。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "被补评采纳的想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 采纳\n",
                                            encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    # 损坏成合法 JSON、字段却不可用：与文件缺失同口径处理
    (guard.dir / rounds.BEST_JSON_NAME).write_text('{"foo": 1}',
                                                   encoding="utf-8")

    sink = RecordingSink()
    guard2 = make_guard(workspace, state_path, sink, verify="user")
    guard2.start()
    assert guard2.best["id"] == cid
    assert guard2.best["round"] == 1
    assert guard2.best["verifier"] == "user"
    assert guard2.best["score"] == 9.0
    # 恢复结果已回写：下一次启动直接命中，不再走恢复分支
    assert json.loads((guard.dir / rounds.BEST_JSON_NAME).read_text(
        encoding="utf-8"))["id"] == cid
    assert any(lvl == "warn" and "恢复" in m for lvl, m in sink.messages)
    guard2.finish()
    summary = [m for lvl, m in sink.messages if "汇总" in m][-1]
    assert "unknown" not in summary
    assert cid in summary


def test_best_json_recovery_skips_corrupt_history_fields(ws):
    """从 history 恢复 best 元数据时，字段类型损坏的事件必须跳过（与
    _valid_best 同一口径）：列表 id / 文本 score 不能进入恢复结果。

    回归：_recover_best 原先只查 id 的真值，非字符串 id（合法 JSON 的
    列表）会被原样写进 best.json——下次启动仍被 _valid_best 拒绝，每次
    都走恢复分支；score 等字段不校验也会写出不可加载的元数据。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "第 1 轮产物")
    assert guard.on_round_end(1) == "adopted"
    good_id = guard.best["id"]

    # best.json 丢失，history 的最后一条采纳事件字段类型损坏
    (guard.dir / rounds.BEST_JSON_NAME).unlink()
    lines = guard.history_path.read_text(encoding="utf-8").splitlines()
    lines.append(json.dumps({"event": "verdict", "id": ["x"], "round": 1,
                             "result": "adopted", "score": "好",
                             "verifier": "user"}, ensure_ascii=False))
    guard.history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sink = RecordingSink()
    guard2 = make_guard(workspace, state_path, sink, verify="off")
    guard2.start()
    # 损坏事件被跳过，恢复到上一条真实采纳记录，回写的元数据可加载
    assert guard2.best["id"] == good_id
    assert rounds._valid_best(json.loads(
        guard2.best_json.read_text(encoding="utf-8")))
    guard2.finish()


def test_best_json_non_finite_or_huge_score_treated_as_corrupt(ws):
    """best.json 的 score 必须是有限数值：NaN/inf 参与阈值比较会让判定
    失效，超出 float 范围的巨大整数会在 `:g` 格式化（评审提示词/评分
    理由）时抛 OverflowError。二者与文本 score 同口径，按损坏元数据
    处理并从 history 恢复。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "第 1 轮产物")
    assert guard.on_round_end(1) == "adopted"
    cid = guard.best["id"]

    for bad in (float("nan"), float("inf"), float("-inf"), 10 ** 400):
        assert not rounds._valid_best(
            {"id": cid, "round": 1, "score": bad}), bad
    for good in (0, 9, 9.5):
        assert rounds._valid_best({"id": cid, "round": 1, "score": good})

    # 损坏元数据不能把 NaN/inf/巨大分数带进 self.best；从 history 的最后
    # 一条有效采纳事件恢复（本轮 verify=off，历史 score 为 None）
    for bad in (float("nan"), float("inf"), 10 ** 400):
        guard.best_json.write_text(
            json.dumps({"id": cid, "round": 1, "verifier": "off",
                        "score": bad}), encoding="utf-8")
        restarted = make_guard(workspace, state_path, verify="off")
        restarted.start()
        assert restarted.best["id"] == cid
        assert restarted.best["score"] is None
        assert rounds._valid_best(json.loads(
            restarted.best_json.read_text(encoding="utf-8")))
        restarted.finish()


def test_best_json_nul_cid_treated_as_corrupt(ws):
    """best.json 的 id 含 NUL 时按损坏元数据处理，不得让守卫启动崩溃。

    回归：_valid_best 只要求 id 是非空字符串，NUL 通过校验后
    _recover_best_text 拼出 cand-<id>.md，Path.read_text 抛
    ValueError("embedded null byte")。start()/finish() 只捕获 OSError，
    异常冒泡到 runner 的降级分支——整轮快照/验证/还原被静默禁用。
    生成侧只会产出 [0-9A-Za-z_-]，因此不安全 id 与类型损坏同口径：
    best.json 交给 _recover_best / 首次运行路径修复。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "第一轮产物")
    assert guard.on_round_end(1) == "adopted"
    cid = guard.best["id"]

    (guard.dir / rounds.BEST_JSON_NAME).write_text(
        json.dumps({"id": f"{cid}\u0000x", "round": 1,
                    "verifier": "user", "score": 9}),
        encoding="utf-8")
    (guard.dir / rounds.BEST_MD_NAME).unlink()

    sink = RecordingSink()
    restarted = make_guard(workspace, state_path, sink, verify="off")
    restarted.start()  # 修复前：ValueError: embedded null byte
    assert rounds._valid_best(restarted.best)
    assert "\u0000" not in restarted.best["id"]
    # 内容源没丢：按当前状态重建基线（research.md 仍是第 1 轮采纳内容）
    assert read_idea(restarted.best_md) == "第一轮产物"

    write_idea(state_path, "第二轮产物")
    assert restarted.on_round_end(2) == "adopted"
    assert rounds._valid_best(json.loads(
        restarted.best_json.read_text(encoding="utf-8")))
    restarted.finish()


def test_verdicts_nul_cid_does_not_crash(ws):
    """history/verdicts 里的候选 id 含 NUL 时按未知 id 忽略，不能抛异常。

    回归：_apply_user_verdicts 只校验 id 是非空字符串，含 NUL 的
    candidate 事件被当作有效候选；采纳分支拼出 cand-<id>.md 后
    read_text 抛 ValueError，start()/finish() 的 except OSError 接不住，
    守卫在补分兑现时崩溃（runner 随后禁用守卫）。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    with open(guard.history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "candidate", "id": "bad\u0000id",
                            "round": 1}, ensure_ascii=False) + "\n")
    (guard.dir / rounds.VERDICTS_NAME).write_text(
        "bad\u0000id 9 采纳\n", encoding="utf-8")

    guard.finish()  # 修复前：ValueError: embedded null byte
    assert guard.best["round"] == 0
    assert not [e for e in events(guard) if e.get("event") == "verdict"]
    assert any(lvl == "warn" and "不存在" in m
               for lvl, m in guard.sink.messages)


def test_best_json_and_history_lost_rebuilds_baseline(ws):
    """best.json 与 history.jsonl 都不可用：按 best.md 合成基线并补记
    baseline 事件，best.json 回写后重启自洽，内容源（best.md）原样保留。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    baseline_md = (guard.dir / rounds.BEST_MD_NAME).read_text(encoding="utf-8")
    (guard.dir / rounds.BEST_JSON_NAME).unlink()
    guard.history_path.unlink()

    sink = RecordingSink()
    guard2 = make_guard(workspace, state_path, sink)
    guard2.start()
    assert guard2.best["verifier"] == "baseline"
    assert guard2.best["round"] == 0
    assert [e["event"] for e in events(guard2)].count("baseline") == 1
    assert (guard.dir / rounds.BEST_JSON_NAME).exists()
    assert (guard.dir / rounds.BEST_MD_NAME).read_text(
        encoding="utf-8") == baseline_md
    assert read_idea(state_path) == "（暂无）"


def test_append_event_after_partial_line_not_swallowed(ws):
    """history.jsonl 末尾留下无换行的残行（写盘中途被杀 / ENOSPC）时，
    后续事件不能与残行拼成一行被静默丢弃。

    回归：_append_event 直接以 "a" 追加，新事件会被粘进残行；
    _read_events 逐行解析坏行跳过——审计记录、_recover_best 的恢复源、
    _apply_user_verdicts 的已决/未决判定（如一条被采纳的 verdict）会
    一起丢失。修复：追加前保证文件以换行结尾。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    with open(guard.history_path, "a", encoding="utf-8") as f:
        f.write('{"event": "candidate", "id": "被截')  # 无结尾换行的残行
    write_idea(state_path, "半截轮次留下的内容")
    guard.on_round_failed(1, "被中断")

    kinds = [e["event"] for e in events(guard)]
    assert kinds[-2:] == ["skipped", "restored"]
    raw = guard.history_path.read_text(encoding="utf-8")
    # 残行独立成行（保留可人工检查），新事件没有被拼接进残行
    assert '{"event": "candidate", "id": "被截\n{"event": "skipped"' in raw
    assert raw.endswith("\n")
    assert "" not in raw.splitlines()  # 不以换行结尾时不额外插入空行


def test_restore_heals_invalid_utf8_state_file(ws):
    """research.md 运行中混入非法 UTF-8 字节（外部编辑器按本地编码保存 /
    agent 写盘事故）时，守卫还原必须仍能执行并把文件修复回来。

    回归：update_section_file 严格解码，一字节损坏即抛 UnicodeDecodeError，
    每轮还原都失败告警、研究循环永久卡死；外部写入助手读同一文件同样抛
    异常，agent 再也写不进任何区块——只能人工删文件重启。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "好想法")
    write_artifact(state_path, "好产物")
    assert guard.on_round_end(1) == "adopted"
    state_path.write_bytes(
        state_path.read_bytes().replace("好想法".encode("utf-8"), b"\xff\xfe"))
    guard.on_round_failed(2, "测试损坏恢复")
    text = state_path.read_text(encoding="utf-8")  # 修复后不应再抛
    assert state.get_section(text, state.SECTION_IDEA) == "好想法"
    assert state.get_section(text, state.SECTION_ARTIFACT) == "好产物"


def test_invalid_utf8_round_snapshotted_and_healed(ws):
    """运行中 agent 写出的内容夹着非法 UTF-8 字节时不能整轮丢弃。

    回归：_read_state_text 严格解码，一个坏字节让 _process_round_end 把
    本轮当「状态文件缺失或不可读」记 skipped——候选快照不留、产物丢失；
    而 state 模块其它路径（ensure_state_file / update_section_file / 写入
    助手）都是「按替换符降级读取并回写修复」的自愈口径，守卫也必须
    一致：坏字节降级为 U+FFFD、文件就地修复，本轮内容照常快照并参与
    验证。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "好想法")
    state_path.write_bytes(
        state_path.read_bytes().replace("好想法".encode("utf-8"), b"\xff\xfe"))
    assert guard.on_round_end(1) == "adopted"
    text = state_path.read_text(encoding="utf-8")  # 修复后严格解码不应抛
    assert state.get_section(text, state.SECTION_IDEA) == "\ufffd\ufffd"
    assert cand_files(guard), "本轮候选必须留快照，不能整轮丢弃"
    assert not any(e["event"] == "skipped" for e in events(guard))
    assert guard.best["verifier"] == "none"


def test_ensure_state_file_heals_invalid_utf8_at_startup(tmp_path):
    """启动预检遇到非法 UTF-8 时必须就地修复，而不是让整次运行中止。

    回归：运行期所有写入路径（update_section_file / 写入助手 / 守卫还原）
    遇到非法 UTF-8 都会按替换符降级并回写修复，但 ensure_state_file 仍严格
    解码，runner 把它转成 SystemExit「状态文件读取失败…可备份后删除
    research.md 重建」——按提示删文件等于丢掉全部研究区块。"""
    state_path = tmp_path / "research.md"
    state.ensure_state_file(state_path, "测试任务")
    state_path.write_bytes(state_path.read_bytes().replace(
        "（暂无）".encode("utf-8"), b"\xff"))
    text = state.ensure_state_file(state_path, "测试任务")  # 不应抛
    assert state.get_section(text, state.SECTION_IDEA) == "\ufffd"
    assert state.get_section(text, state.SECTION_ARTIFACT) == "\ufffd"
    # 修复必须已落盘：严格解码不再抛，磁盘内容与返回值一致
    assert state_path.read_text(encoding="utf-8") == text


def test_helper_show_tolerates_invalid_utf8(tmp_path):
    """write_section.py show 遇到非法 UTF-8 必须降级输出而不是 traceback。

    回归：写入子命令（idea/artifact）早已按替换符降级并回写修复，show 仍
    严格解码——状态文件正因写盘事故损坏时，show 正是查看现状的通道，
    却直接 UnicodeDecodeError 冒泡成 traceback（退出码 1）。"""
    import subprocess

    state_path = tmp_path / "research.md"
    state.ensure_state_file(state_path, "测试任务")
    state_path.write_bytes(state_path.read_bytes().replace(
        "（暂无）".encode("utf-8"), b"\xff"))
    helper = state.write_helper_script(tmp_path, state_path)
    r = subprocess.run([sys.executable, str(helper), "show"],
                       cwd=str(tmp_path), capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    assert "Traceback" not in err, err
    out = r.stdout.decode("utf-8")
    assert "\ufffd" in out
    # 标记行与结构照常可读，供外边看现状
    assert state.SECTION_IDEA in out and state.SECTION_ARTIFACT in out


def test_state_supports_cr_only_line_endings(tmp_path):
    """状态文件为裸 CR 行尾（老式 Mac 编辑器 / 手工转换）时区块必须可读可写。

    回归：_SECTION_MARKER 的 (?m)^...$ 只认 \\n，CR-only 文件里所有标记都
    识别不到：get_section 两个区块都返回空串，update_section_file 还会在
    文件末尾另建一对标记，原有内容沦为死数据。"""
    state_path = tmp_path / "research.md"
    state_path.write_bytes(
        state.scaffold("测试任务").replace("\n", "\r").encode("utf-8"))
    text = state_path.read_text(encoding="utf-8")
    assert state.get_section(text, state.SECTION_IDEA) == "（暂无）"
    assert state.get_section(text, state.SECTION_ARTIFACT) == "（暂无）"
    assert state.update_section_file(state_path, state.SECTION_IDEA, "CR 想法") \
        == ("（暂无）", "CR 想法")
    text = state_path.read_text(encoding="utf-8")
    assert state.get_section(text, state.SECTION_IDEA) == "CR 想法"
    assert state.get_section(text, state.SECTION_ARTIFACT) == "（暂无）"


def test_strip_stray_markers_handles_cr_only_lines():
    """_strip_stray_markers 必须能清除裸 CR 行尾的独占整行标记。"""
    s, e = state.start_marker(state.SECTION_IDEA), \
        state.end_marker(state.SECTION_IDEA)
    text = f"前言\r{s}\r正文\r{e}"
    assert state._strip_stray_markers(text, [], 0, s, e) == "前言\r正文"
    # 行内提及的标记文本是普通内容，必须保留
    inline = f"前言\r说明：{s} 是标记\r正文"
    assert state._strip_stray_markers(inline, [], 0, s, e) == inline


def test_section_content_keeps_unicode_line_separators(tmp_path):
    """区块内容里的 U+2028/U+2029/U+0085 不是标记行边界。

    回归：sanitize_section_content 用 str.splitlines() 切行（helper 副本
    相同），会把这类 Unicode 行分隔符后面的标记样文本当成独占整行标记
    删除，并把分隔符改写成换行，导致写入内容丢字/变形；而区块标记解析
    （_SECTION_MARKER）只认 CR/LF，这些文本本来就不会参与配对。"""
    import subprocess

    for sep in ("\u2028", "\u2029", "\x85"):
        # 行分隔符既在内容中间，也在首尾：两端不能被当成可剥空白后
        # 把后面的标记样文本暴露成“独占整行”的标记
        contents = (
            f"甲{sep}{state.start_marker(state.SECTION_IDEA)}{sep}乙",
            f"{sep}{state.start_marker(state.SECTION_IDEA)}{sep}",
        )
        for content in contents:
            assert state.sanitize_section_content(content) == content

            state_path = tmp_path / "research.md"
            state.ensure_state_file(state_path, "测试任务")
            state.update_section_file(state_path, state.SECTION_IDEA, content)
            text = state_path.read_text(encoding="utf-8")
            assert state.get_section(text, state.SECTION_IDEA) == content

            helper = state.write_helper_script(tmp_path, state_path)
            r = subprocess.run([sys.executable, str(helper), "idea"],
                               input=content.encode("utf-8"),
                               capture_output=True)
            assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
            text = state_path.read_text(encoding="utf-8")
            assert state.get_section(text, state.SECTION_IDEA) == content


def test_helper_writes_sections_in_cr_only_state(tmp_path):
    """写入助手脚本必须与 xuen.state 同口径支持裸 CR 行尾。

    回归：helper 内嵌的是 _SECTION_MARKER 的副本，只认 \\n；CR-only
    状态文件里已有标记全被当正文，写入新区块后另一区块读出内容被清空。"""
    import subprocess

    state_path = tmp_path / "research.md"
    state_path.write_bytes(
        state.scaffold("测试任务").replace("\n", "\r").encode("utf-8"))
    helper = state.write_helper_script(tmp_path, state_path)
    r = subprocess.run([sys.executable, str(helper), "idea"],
                       input="CR 想法".encode("utf-8"), capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    text = state_path.read_text(encoding="utf-8")
    assert state.get_section(text, state.SECTION_IDEA) == "CR 想法"
    assert state.get_section(text, state.SECTION_ARTIFACT) == "（暂无）"


def test_helper_and_module_keep_same_state_entry_when_symlink_replaced(tmp_path):
    """状态文件是符号链接时，helper 不得写解析后的目标而模块写链接路径。"""
    import subprocess

    if not hasattr(os, "symlink"):
        pytest.skip("平台不支持符号链接")
    real_path = tmp_path / "real.md"
    state.ensure_state_file(real_path, "测试任务")
    state_path = tmp_path / "research.md"
    try:
        state_path.symlink_to(real_path)
    except OSError:
        pytest.skip("平台不允许创建符号链接")
    helper = state.write_helper_script(tmp_path, state_path)

    r = subprocess.run([sys.executable, str(helper), "idea"],
                       input="helper 一".encode("utf-8"), capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert state.get_section(state_path.read_text(encoding="utf-8"),
                             state.SECTION_IDEA) == "helper 一"

    state.update_section_file(state_path, state.SECTION_ARTIFACT, "module")
    assert not state_path.is_symlink()
    r = subprocess.run([sys.executable, str(helper), "idea"],
                       input="helper 二".encode("utf-8"), capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")

    text = state_path.read_text(encoding="utf-8")
    assert state.get_section(text, state.SECTION_IDEA) == "helper 二"
    assert state.get_section(text, state.SECTION_ARTIFACT) == "module"


def test_update_section_preserves_other_section_with_mixed_line_endings(tmp_path):
    """混合 CR/LF 行尾时更新一个区块不得改变另一区块读出内容。

    回归：ARTIFACT 的 START 用 LF、紧接着的 END 用 CR、后面还有一个 LF
    END 时，旧解析把 CR 行尾的 END 当正文、与后面的 LF END 配对；更新
    IDEA 清除游离标记后，ARTIFACT 读出内容从「文本 + END 字面量」变成
    「文本」。"""
    state_path = tmp_path / "research.md"
    text = (
        f"{state.start_marker(state.SECTION_ARTIFACT)}\n"
        f"文本\r{state.end_marker(state.SECTION_ARTIFACT)}\n"
        f"{state.end_marker(state.SECTION_ARTIFACT)}\r"
    )
    state_path.write_bytes(text.encode("utf-8"))
    before = state._first_section(text, state.SECTION_ARTIFACT)
    assert before == "文本"
    state.update_section_file(state_path, state.SECTION_IDEA, "新想法")
    text = state_path.read_text(encoding="utf-8")
    assert state._first_section(text, state.SECTION_ARTIFACT) == before
    assert state.get_section(text, state.SECTION_IDEA) == "新想法"


def test_read_events_tolerates_encoding_corrupt_line(ws):
    """history.jsonl 中间的行含非法 UTF-8 字节（写盘中途被杀留下的半截
    多字节字符 / 手工编辑事故）时，其余事件必须照常可读。

    回归：_read_events 整体 read_text 解码，一字节损坏即抛
    UnicodeDecodeError 并把【整份】历史当作空——审计记录、_recover_best
    的恢复源、_apply_user_verdicts 的已决/未决判定一起丢失，最佳元数据
    会被错误地重建为基线、已决的拒绝还能被 verdicts.txt 翻案。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.dir.mkdir(parents=True, exist_ok=True)
    good1 = json.dumps({"event": "heartbeat", "round": 1})
    good2 = json.dumps({"event": "skipped", "round": 2, "reason": "x"})
    guard.history_path.write_bytes(
        good1.encode("utf-8") + b"\n"
        + b'{"event": "heartbeat", "round": \xff\xfe}\n'  # 坏字节 + 非法 JSON
        + good2.encode("utf-8") + b"\n")
    evs = guard._read_events()
    assert [(e["event"], e.get("round")) for e in evs] == [
        ("heartbeat", 1), ("skipped", 2)]


def test_read_events_preserves_unicode_line_separators(ws):
    """history.jsonl 的逐行解析只能按 \\n 切分。

    json.dumps(ensure_ascii=False) 不转义 U+2028/U+2029/U+0085，而
    str.splitlines 会把它们当成换行——任务名 / 评语含这些字符时，一条
    合法 JSON 事件会被拆成两半并被整体跳过，审计日志与 best 恢复源
    静默丢记录。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.dir.mkdir(parents=True, exist_ok=True)
    reason = "a\u2028b\u2029c\x85d"
    sep_event = json.dumps({"event": "skipped", "round": 2,
                            "reason": reason}, ensure_ascii=False)
    tail = json.dumps({"event": "heartbeat", "round": 3})
    guard.history_path.write_text(sep_event + "\n" + tail + "\n",
                                  encoding="utf-8")
    evs = guard._read_events()
    assert [e["event"] for e in evs] == ["skipped", "heartbeat"]
    assert evs[0]["reason"] == reason
    # 外部编辑器转成 CR / CRLF 也不能把整份历史并成一行
    guard.history_path.write_text(sep_event + "\r" + tail + "\r\n",
                                  encoding="utf-8")
    evs = guard._read_events()
    assert [e["event"] for e in evs] == ["skipped", "heartbeat"]
    assert evs[0]["reason"] == reason


def test_read_events_tolerates_bom(ws):
    """history.jsonl 带 UTF-8 BOM 时首条事件不能被静默丢弃。

    Windows 记事本等编辑器保存会在文件首加 BOM；json.loads 把 U+FEFF
    当非法 JSON 前缀，首行事件（常见为 baseline，或外部拼接后的 candidate）
    连同后续的恢复/已决依据一起丢失。拼接文件里靠后的 BOM 同样要剥。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.dir.mkdir(parents=True, exist_ok=True)
    first = json.dumps({"event": "baseline", "id": "baseline-x", "round": 0})
    second = json.dumps({"event": "candidate", "id": "cand-x", "round": 1})
    guard.history_path.write_bytes(
        b"\xef\xbb\xbf" + first.encode("utf-8") + b"\n"
        + b"\xef\xbb\xbf" + second.encode("utf-8") + b"\n")
    evs = guard._read_events()
    assert [e["event"] for e in evs] == ["baseline", "candidate"]
    assert evs[0]["id"] == "baseline-x"
    assert evs[1]["id"] == "cand-x"


def test_load_best_tolerates_bom(ws):
    """best.json 带 UTF-8 BOM 时不能按损坏元数据丢弃。

    丢弃会触发 _recover_best：历史也不可用时把最佳重建为 baseline，
    round/score/verifier 全部失真，汇总与评审提示词长期显示错误信息。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    guard.dir.mkdir(parents=True, exist_ok=True)
    data = {"id": "cand-bom", "round": 3, "verifier": "user", "score": 9.0}
    guard.best_json.write_bytes(
        b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))
    assert guard._load_best() == data


def test_late_adoption_state_already_matching_no_restore_noise(ws):
    """补分采纳时 research.md 已与快照一致（无区块需写回）：不产生多余
    restored 事件、不虚增还原统计（与 _restore_best 的无变化口径一致），
    日志也不得虚称「写回状态文件」。"""
    workspace, state_path = ws
    sink = RecordingSink()
    guard = make_guard(workspace, state_path, sink, verify="user")
    guard.start()
    write_idea(state_path, "外部已写回的想法")
    assert guard.on_round_end(1) == "pending"
    cid = events(guard)[1]["id"]
    # 外部（或用户）已把快照内容完整写回 research.md
    state_path.write_text((guard.dir / f"cand-{cid}.md").read_text(
        encoding="utf-8"), encoding="utf-8")
    before = guard.stats.restored
    n0 = len([e for e in events(guard) if e["event"] == "restored"])
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9\n", encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    assert guard.stats.adopted == 1
    assert guard.stats.restored == before
    assert len([e for e in events(guard)
                if e["event"] == "restored"]) == n0
    oks = [m for lvl, m in sink.messages if lvl == "ok" and "晋升为最佳" in m]
    assert oks and "无需写回" in oks[-1]


def test_adopt_corrupt_snapshot_not_committed(ws, monkeypatch):
    """晋升前必须重新校验快照结构：快照落盘后被外部截断/篡改时，
    损坏内容绝不能进 best.md（否则下次还原会把空区块写回 research.md，
    静默丢掉当前最佳）。异常按写盘失败口径上抛，候选保持未决。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    baseline_id = guard.best["id"]
    baseline_md = (guard.dir / rounds.BEST_MD_NAME).read_text(encoding="utf-8")
    write_idea(state_path, "结构损坏的快照不能进最佳")
    real_verify = guard._verify

    def corrupt_snapshot(round_no, cid):
        (guard.dir / f"{rounds.CAND_PREFIX}{cid}.md").write_text(
            "坏掉的内容（缺少区块标记）", encoding="utf-8")
        return real_verify(round_no, cid)

    monkeypatch.setattr(guard, "_verify", corrupt_snapshot)
    with pytest.raises(OSError):
        guard.on_round_end(1)
    assert guard.best["id"] == baseline_id
    assert guard.stats.adopted == 0
    assert (guard.dir / rounds.BEST_MD_NAME).read_text(
        encoding="utf-8") == baseline_md
    assert not [e for e in events(guard)
                if e["event"] == "verdict" and e.get("result") == "adopted"]


def test_late_adoption_corrupt_snapshot_stays_pending(ws):
    """用户补分采纳旧候选前同样要校验快照结构：损坏快照保持挂起，
    不写 best.md、不写回 research.md，也不留不可翻案的 adopted 事件。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    baseline_md = (guard.dir / rounds.BEST_MD_NAME).read_text(encoding="utf-8")
    write_idea(state_path, "等待补分的想法")
    assert guard.on_round_end(1) == "pending"
    cid = [e for e in events(guard) if e["event"] == "candidate"][-1]["id"]
    (guard.dir / f"{rounds.CAND_PREFIX}{cid}.md").write_text(
        "坏掉的内容（缺少区块标记）", encoding="utf-8")
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 采纳\n",
                                            encoding="utf-8")
    guard.finish()
    assert guard.best["round"] == 0
    assert guard.stats.adopted == 0
    assert guard.stats.pending == 1
    assert (guard.dir / rounds.BEST_MD_NAME).read_text(
        encoding="utf-8") == baseline_md
    assert read_idea(state_path) == "（暂无）"
    assert not [e for e in events(guard)
                if e["event"] == "verdict" and e.get("result") == "adopted"]


@pytest.mark.parametrize("mode, expected", [
    ("off", "adopted"),
    ("tests", "rejected"),
    ("user", "pending"),
])
def test_verdict_event_append_failure_keeps_result_accounting(
        ws, monkeypatch, mode, expected):
    """判定事件写盘失败不能把已生效的判定变成异常。

    回归：_process_round_end 在 _adopt/拒绝/挂起分派【之前】写 verdict
    事件且未捕获 OSError。磁盘满时采纳轮已计入 adopted（不变式尚可），
    拒绝/挂起轮却因异常直接跳出——stats 停在「候选 1、采纳/拒绝/待评
    分全 0」，拒绝/挂起路径的还原与补分登记也全部跳过，汇总自相矛盾。
    判定事件只是审计/恢复源，写盘失败应告警降级，判定本身照常完成。
    """
    workspace, state_path = ws
    kwargs = {"verify": mode}
    if mode == "tests":
        monkeypatch.setattr(rounds, "detect_test_suite", lambda repo: ["pytest"])
        kwargs["suite_runner"] = lambda *a, **k: SuiteResult(
            available=True, ok=False, reason="退出码 1")
    guard = make_guard(workspace, state_path, **kwargs)
    guard.start()
    write_idea(state_path, "判定事件写盘失败也要完成本轮")
    real_append = guard._append_event

    def fail_verdict_event(ev):
        if ev.get("event") == "verdict":
            raise OSError("磁盘满（模拟）")
        return real_append(ev)

    monkeypatch.setattr(guard, "_append_event", fail_verdict_event)
    assert guard.on_round_end(1) == expected

    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending) == {
        "adopted": (1, 1, 0, 0),
        "rejected": (1, 0, 1, 0),
        "pending": (1, 0, 0, 1),
    }[expected]
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert any("记录判定事件失败" in m for _, m in guard.sink.messages)
    # 判定已生效：拒绝/挂起必须还原最佳，采纳则保留候选内容为最佳
    assert read_idea(state_path) == (
        "判定事件写盘失败也要完成本轮" if expected == "adopted" else "（暂无）")


def test_corrupt_verdict_event_failure_keeps_rejection_accounting(
        ws, monkeypatch):
    """结构损坏分支的判定事件写盘失败同样只告警，拒绝记账与还原照常完成。

    回归：该分支的 verdict 事件写入不在任何 try 内；磁盘满时异常直接
    跳出，stats 停在「候选 1、拒绝 0」，还原也被跳过——与正常验证分支
    修复前的自相矛盾完全一致。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    state_path.write_text("区块标记被外部删除", encoding="utf-8")
    real_append = guard._append_event

    def fail_verdict_event(ev):
        if ev.get("event") == "verdict":
            raise OSError("磁盘满（模拟）")
        return real_append(ev)

    monkeypatch.setattr(guard, "_append_event", fail_verdict_event)
    assert guard.on_round_end(1) == "rejected"

    s = guard.stats
    assert (s.rounds, s.candidates, s.rejected) == (1, 1, 1)
    assert (s.adopted, s.pending, s.skipped) == (0, 0, 0)
    assert cand_files(guard)  # 本轮产物照常快照留档
    assert any("记录判定事件失败" in m for _, m in guard.sink.messages)
    assert read_idea(state_path) == "（暂无）"  # 已还原最佳


def test_user_verdict_event_failure_not_reapplied_by_round_tail(
        ws, monkeypatch):
    """用户评分在 _process_round_end 里已兑现、但判定事件写盘失败时，
    本轮收尾的 _apply_user_verdicts 不能把 verdicts.txt 里同一行再兑现
    一次（拒绝统计翻倍，adopted+rejected+pending==candidates 破裂）。

    回归：事件失败只告警后没有把候选记入 _applied_verdicts；本轮结束时
    resolved 里没有该 id（事件缺失）、当前最佳也不是它，于是同一行评分
    被再次应用。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "用户评分低于阈值")
    monkeypatch.setattr(guard, "_snapshot_candidate",
                        lambda round_no, text: "fixedcid")
    (guard.dir / "verdicts.txt").write_text("fixedcid 2\n", encoding="utf-8")
    real_append = guard._append_event

    def fail_verdict_event(ev):
        if ev.get("event") == "verdict":
            raise OSError("磁盘满（模拟）")
        return real_append(ev)

    monkeypatch.setattr(guard, "_append_event", fail_verdict_event)
    assert guard.on_round_end(1) == "rejected"

    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending) == (1, 0, 1, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert "fixedcid" in guard._applied_verdicts
    assert read_idea(state_path) == "（暂无）"  # 拒绝路径已还原最佳


def test_pending_verdict_event_failure_allows_same_session_late_scoring(
        ws, monkeypatch):
    """挂起轮的判定事件写盘失败不能让候选永久无法补分。

    回归：_process_round_end 的降级写把挂起也记入 _applied_verdicts。
    挂起不是终局判定；用户随后在 verdicts.txt 补分时，_apply_user_verdicts
    会直接跳过该 id，候选在本会话内永远无法采纳。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "等待补分的好想法")
    real_append = guard._append_event

    def fail_verdict_event(ev):
        if ev.get("event") == "verdict":
            raise OSError("磁盘满（模拟）")
        return real_append(ev)

    monkeypatch.setattr(guard, "_append_event", fail_verdict_event)
    assert guard.on_round_end(1) == "pending"
    cid = [e["id"] for e in events(guard)
           if e["event"] == "candidate"][-1]
    assert any("记录判定事件失败" in m for _, m in guard.sink.messages)
    assert cid not in guard._applied_verdicts

    monkeypatch.setattr(guard, "_append_event", real_append)
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9 采纳\n",
                                             encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    s = guard.stats
    assert (s.adopted, s.rejected, s.pending) == (1, 0, 0)
    assert read_idea(state_path) == "等待补分的好想法"


def test_skipped_and_heartbeat_event_failure_does_not_abort_round(
        ws, monkeypatch):
    """心跳/跳过事件的写盘失败只告警：轮次返回值与还原照常。

    回归：这三处 _append_event 未捕获，磁盘满时 heartbeat/skipped 轮次
    直接抛异常——runner 误判为「守卫处理异常」，失败轮次的半截产物还会
    因为跳过还原而留在 research.md 污染下一轮。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()

    def fail_append(kinds):
        real_append = guard._append_event

        def _append(ev):
            if ev.get("event") in kinds:
                raise OSError("磁盘满（模拟）")
            return real_append(ev)
        return _append

    # 心跳：内容与基线一致
    monkeypatch.setattr(guard, "_append_event", fail_append({"heartbeat"}))
    assert guard.on_round_end(1) == "heartbeat"
    assert guard.stats.heartbeat == 1
    assert any("记录心跳事件失败" in m for _, m in guard.sink.messages)

    # 跳过：状态文件缺失
    monkeypatch.setattr(guard, "_append_event", fail_append({"skipped"}))
    state_path.unlink()
    assert guard.on_round_end(2) == "skipped"
    assert read_idea(state_path) == "（暂无）"  # 还原重建了状态文件
    assert any("记录跳过事件失败" in m for _, m in guard.sink.messages)

    # on_round_failed 的跳过记账同理：还原不能被事件失败挡住
    write_idea(state_path, "半截产物")
    guard.on_round_failed(3, "agent 超时")
    assert (guard.stats.rounds, guard.stats.skipped) == (3, 2)
    assert read_idea(state_path) == "（暂无）"


def test_late_verdict_event_write_failure_still_applies_and_dedupes(ws, monkeypatch):
    """补分判定事件写盘失败时，已落盘的晋升仍要完成记账且不能重复兑现。

    回归：_apply_user_verdicts 在 _commit_best 成功后才写 verdict 事件，
    写盘失败（磁盘满）会直接抛出——self.best/stats 停在旧值，调用方只看到
    「补分失败稍后重试」，而 best.md/best.json 已经指向新候选；下一次
    start/finish/每轮兑现会再次采纳同一候选。判定已生效，事件失败应告警
    降级，并用内存集合阻止同一行评分重复兑现。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "补分事件写盘失败也要晋升")
    assert guard.on_round_end(1) == "pending"
    cid = [e["id"] for e in events(guard) if e["event"] == "candidate"][-1]
    (guard.dir / "verdicts.txt").write_text(f"{cid} 9\n", encoding="utf-8")

    real_append = guard._append_event

    def fail_verdict_event(ev):
        if ev.get("event") == "verdict":
            raise OSError("磁盘满（模拟）")
        return real_append(ev)

    monkeypatch.setattr(guard, "_append_event", fail_verdict_event)
    guard.finish()
    assert guard.best["id"] == cid
    s = guard.stats
    assert (s.adopted, s.pending) == (1, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert read_idea(state_path) == "补分事件写盘失败也要晋升"
    assert any("记录补分判定事件失败" in m for _, m in guard.sink.messages)

    # 历史里没有已决事件也不能重复兑现（同一会话再次 finish）
    monkeypatch.setattr(guard, "_append_event", real_append)
    guard.finish()
    assert guard.stats.adopted == 1
    assert guard.stats.adopted + guard.stats.rejected + guard.stats.pending \
        == guard.stats.candidates


def test_current_best_score_does_not_create_rejection_verdict(ws):
    """当前最佳已经是「已决」，历史 verdict 丢失后补分也不能再判它。

    回归：_apply_user_verdicts 只按 history 的 verdict 事件去重。采纳事件
    若因写盘失败/外部截断缺失，用户再给当前最佳写一行低分，会记一条
    「拒绝当前最佳」的 late 判定并增加拒绝统计，但最佳内容不会也不该
    回退——审计与汇总自相矛盾。当前最佳 id 应天然视为已决。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "已采纳的最佳")
    assert guard.on_round_end(1) == "adopted"
    cid = guard.best["id"]
    # 模拟采纳 verdict 事件丢失（只保留 candidate 事件）
    kept = [e for e in events(guard)
            if not (e.get("event") == "verdict" and e.get("id") == cid)]
    guard.history_path.write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in kept),
        encoding="utf-8")

    (guard.dir / "verdicts.txt").write_text(f"{cid} 2\n", encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    assert guard.stats.rejected == 0
    assert guard.stats.adopted == 1
    late = [e for e in events(guard) if e["event"] == "verdict"
            and e.get("id") == cid and e.get("late")]
    assert late == []


def test_restore_event_write_failure_does_not_abort_round(ws, monkeypatch):
    """还原事件写盘失败不能把已完成的还原变成异常。

    回归：_restore_best 先写回 research.md、增加 restored 统计，再追加
    restored 事件；事件写入失败（磁盘满）时异常一路冒出 on_round_end，
    调用方误以为整轮守卫失败。挂起候选的 pending 记账虽已完成，但
    「如何评分」提示会丢失，runner 还会再做一次无意义的补还原。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "还原事件写盘失败也要完成挂起")
    real_append = guard._append_event

    def fail_restored_event(ev):
        if ev.get("event") == "restored":
            raise OSError("磁盘满（模拟）")
        return real_append(ev)

    monkeypatch.setattr(guard, "_append_event", fail_restored_event)
    assert guard.on_round_end(1) == "pending"
    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending, s.restored) \
        == (1, 0, 0, 1, 1)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert read_idea(state_path) == "（暂无）"
    assert any("记录还原事件失败" in m for _, m in guard.sink.messages)


def test_later_malformed_verdict_line_does_not_erase_valid_score(ws):
    """同一候选的坏评分行不能覆盖前面的有效评分。

    回归：_read_verdicts 按行覆盖 out[cid]，用户先写「cid 9」、随后
    补了一行打错的「cid abc」时，坏行把有效评分替换成 None，候选永远
    挂起——与「坏行跳过、好行照常生效」的容错口径相反。坏行应跳过，
    但后一条有效评分仍按最后一条覆盖（用户纠正分数的主要写法）。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "坏行不能覆盖有效补分")
    assert guard.on_round_end(1) == "pending"
    cid = [e["id"] for e in events(guard) if e["event"] == "candidate"][-1]
    (guard.dir / "verdicts.txt").write_text(
        f"{cid} 9\n{cid} 3x\n", encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    assert guard.stats.adopted == 1
    assert guard.stats.pending == 0
    assert guard.stats.adopted + guard.stats.rejected + guard.stats.pending \
        == guard.stats.candidates
