"""轮次守卫单元测试：快照、候选/最佳分离、验证级联、用户/AI 评分、还原语义。"""
import json
import os
import shutil
import subprocess
import sys
import threading
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

    虚拟环境、依赖目录、build/dist、点目录以及 pytest 默认忽略的
    *.egg（安装产物）/{arch} 目录里的第三方/生成测试都不会被
    `pytest -q` 收集；按它们探测会得到假阳性，随后 pytest 以退出码 5
    失败，候选被误判为测试失败。"""
    for relpath in ("node_modules/dep/test_dep.py", ".venv/lib/test_env.py",
                    ".hidden/test_hidden.py", "build/test_build.py",
                    "dist/test_dist.py", "pkg.egg/test_egg.py",
                    "{arch}/test_arch.py"):
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


def test_detect_test_suite_make_with_bom(tmp_path):
    """Windows 编辑器保存的 Makefile 常带 UTF-8 BOM。

    GNU make 会忽略文件首的 BOM、照常执行 test 目标；探测按 utf-8 读取
    时 BOM 会粘在 "test" 前导致正则不匹配，把可运行的套件误判成「没有
    测试」，候选转而进入评分兜底。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text("\ufefftest:\n\techo ok\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("name", ["GNUmakefile", "makefile"])
def test_detect_test_suite_make_default_file_names(tmp_path, name):
    """GNU make 也搜索 GNUmakefile / makefile；只查 Makefile 会漏掉套件，
    auto 模式于是白白跳过测试、转去 AI 评分。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / name).write_text("test:\n\techo ok\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_respects_gnu_make_search_order(tmp_path):
    """GNUmakefile 存在时 make 不会再看 Makefile：后者里的 test 目标
    不可运行，探测命中会让 make test 以退出码 2 拒绝候选。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "GNUmakefile").write_text("all:\n\techo all\n",
                                          encoding="utf-8")
    (tmp_path / "Makefile").write_text("test:\n\techo ok\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_unusable_first_default_file_shadows_makefile(
        tmp_path):
    """GNUmakefile 是目录时 make 直接失败，不能跳过它去探测 Makefile。

    回归：探测用 is_file() 选默认文件，目录/悬空链接类型的 GNUmakefile
    被当作不存在，转而命中 Makefile 的 test 目标并执行 `make test`；
    但 GNU make 会先选中目录并以退出码 2 报「Is a directory」，候选被
    误判为测试失败。首个存在的默认文件不可用时应按「没有可运行套件」
    处理。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "GNUmakefile").mkdir()
    (tmp_path / "Makefile").write_text("test:\n\techo ok\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_broken_symlink_shadows_makefile(tmp_path):
    """悬空符号链接的 GNUmakefile 同样会让 make 失败，不能回退到 Makefile。"""
    if not shutil.which("make") or not hasattr(os, "symlink"):
        pytest.skip("make 或符号链接不可用")
    try:
        (tmp_path / "GNUmakefile").symlink_to(tmp_path / "missing")
    except OSError:
        pytest.skip("当前环境不允许创建符号链接")
    (tmp_path / "Makefile").write_text("test:\n\techo ok\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_suffixed_target_only_is_not_a_suite(tmp_path):
    """只有 test-unit / test-ci 之类后缀目标不算 make 套件：探测命中会执行
    `make test`，而 Makefile 并没有 test 目标、make 以退出码 2 失败，
    会被误判为「测试失败」拒绝候选（该场景应属「没有可运行套件」）。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text("test-unit:\n\techo unit\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("directive", [
    "include tests.mk",
    "-include tests.mk",
    "sinclude tests.mk",
    " include tests.mk # comment",
    "include tests.mk other.mk",
    "include tests.mk \\\n",
])
def test_detect_test_suite_make_included_file(tmp_path, directive):
    """test 目标写在 include 进来的 Makefile 里时也要探测到。

    GNU make 会读取 include/-include/sinclude 的文件；只扫描主 Makefile
    会把这类可运行的 `make test` 误判成没有套件，tests 模式永远挂起。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(directive + "\n",
                                       encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@true\n",
                                       encoding="utf-8")
    (tmp_path / "other.mk").write_text("all:\n\t@true\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "T = tests.mk\ninclude $(T)\n",
    "T := tests.mk\ninclude ${T}\n",
    "T ?= tests.mk\ninclude $(T)\n",
    "T = other.mk\nT += tests.mk\ninclude $(T)\n",
    "D = mk\ninclude $(D)/tests.mk\n",
    "M = other.mk tests.mk\ninclude $(M)\n",
    "include vars.mk\ninclude $(T)\n",
    "T = tests.mk\ninclude $T\n",
    "include $(CURDIR)/tests.mk\n",
    "D = mk\ninclude $(addprefix $(D)/, tests.mk)\n",
    "include $(addsuffix .mk, tests)\n",
    "include $(strip tests.mk)\n",
    "include $(notdir mk/tests.mk)\n",
    "include $(dir mk/tests.mk)tests.mk\n",
    "include $(basename tests.mk).mk\n",
    "D = mk\ninclude $(wildcard $(addprefix $(D)/, *.mk))\n",
    "include $(addprefix mk/, $(notdir mk/tests.mk))\n",
    "include $(dir $(wildcard mk/tests.mk))tests.mk\n",
    "include $(strip $(wildcard tests.mk))\n",
    "include $(dir $(lastword $(MAKEFILE_LIST)))tests.mk\n",
    "include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))tests.mk\n",
    "include $(lastword Makefile tests.mk)\n",
    "include $(realpath tests.mk)\n",
])
def test_detect_test_suite_make_variable_include(tmp_path, makefile):
    """include 的文件名由简单变量展开时也要按 make 语义读取。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@true\n",
                                       encoding="utf-8")
    (tmp_path / "other.mk").write_text("all:\n\t@true\n",
                                       encoding="utf-8")
    (tmp_path / "vars.mk").write_text("T = tests.mk\n", encoding="utf-8")
    (tmp_path / "mk").mkdir()
    (tmp_path / "mk" / "tests.mk").write_text("test:\n\t@true\n",
                                              encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "F = tests.mk\ninclude $(foreach f,$(F),$(f))\n",
    "F = tests.mk\ninclude $(value F)\n",
    "F = tests.mk\nfiles = $(F)\ninclude $(call files)\n",
    "include $(if x,tests.mk,missing.mk)\n",
    "include $(info )tests.mk\n",
    "include $(warning )tests.mk\n",
    "X = tests.mk\ninclude $(if $(origin X),tests.mk)\n",
    "X := tests.mk\ninclude $(if $(flavor X),tests.mk)\n",
])
def test_detect_test_suite_make_include_argument_functions(tmp_path,
                                                           makefile):
    """include 参数里的 value/foreach/call/条件/元数据函数要按 make 展开。

    回归：include 只展开普通引用与静态函数，`include $(value F)` /
    `$(foreach f,...)` 被当成字面文件名，真正的 tests.mk 没有读入，
    可运行的 test 目标被误判成没有套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@true\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "include =",
    "include := x",
    "include ?= x",
    "include += x",
    "include ::= x",
    "-include =",
    "sinclude = x",
    " include = x",
])
def test_detect_test_suite_make_include_assignment_is_not_directive(
        tmp_path, line):
    """`include =` 等是名为 include 的普通变量赋值，不是 include 指令。

    回归：include 正则把赋值运算符当必需文件名，`include =` 被误报成
    缺失文件，后面可运行的 test 目标被漏检。-include/sinclude 同理。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_unsupported_include_assignment_op_missing_file(
        tmp_path):
    """`:::=` 在 make 4.3 不是赋值运算符，`include :::=` 仍是 include。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include :::=\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_empty_info_include_is_noop(tmp_path):
    """`include $(info x)` 展开成空文件名，make 不读任何文件也不会失败。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(info x)\ntest:\n\t@true\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_basename_dotfile(tmp_path):
    """make 的 basename 对 `.tests` 返回空串，不能按 splitext 保留原词。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(basename .tests).mk\n", encoding="utf-8")
    (tmp_path / ".tests.mk").write_text("test:\n\t@true\n",
                                        encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_suffix_dotfile(tmp_path):
    """make 的 suffix 对 `.tests` 返回 `.tests`，缺失的必需 include 要报错。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(suffix .tests)\ntest:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_recursive_variable(tmp_path):
    """递归变量自引用/互引用会让 make 展开时报错，不能探测出套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    cases = [
        "T = $(T)\ninclude $(T)\ntest:\n\t@true\n",
        "T = $(T)\n$(T):\n\t@true\n",
        "A = $(B)\nB = $(A)\ninclude $(A)\ntest:\n\t@true\n",
    ]
    for makefile in cases:
        (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
        assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_undefined_include_path(tmp_path):
    """未定义变量展开为空：`include $(T)/tests.mk` 会变成 /tests.mk，
    make 因必需 include 缺失而失败，不能当空文件名跳过。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(UNDEFINED)/tests.mk\ntest:\n\t@true\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_escaped_dollar_function(tmp_path):
    """`$$(wildcard ...)` 里的 $$ 是字面 $，不能按函数展开。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $$(wildcard tests.mk)\ntest:\n\t@true\n",
        encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@true\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_unterminated_function(tmp_path):
    """未闭合的 include 函数引用会让 make 直接报错，不能继续探测。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    for expr in ("$(wildcard tests.mk", "$(T"):
        (tmp_path / "Makefile").write_text(
            f"include {expr}\ntest:\n\t@true\n", encoding="utf-8")
        assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_bad_addprefix_args(tmp_path):
    """addprefix/addsuffix 缺少逗号时 make 直接报错，不能当空展开。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    for expr in ("$(addprefix a)", "$(addsuffix a)", "$(addprefix )"):
        (tmp_path / "Makefile").write_text(
            f"include {expr}\ntest:\n\t@true\n", encoding="utf-8")
        assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_variable_include_missing(tmp_path):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "T = missing.mk\ninclude $(T)\ntest:\n\t@true\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) is None

    (tmp_path / "Makefile").write_text(
        "T = missing.mk\n-include $(T)\ntest:\n\t@true\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("directive", [
    "include $(wildcard *.mk)",
    "include ${wildcard *.mk}",
    "include $(wildcard vars.mk tests.mk)",
    "include $(wildcard missing-*.mk) tests.mk",
])
def test_detect_test_suite_make_wildcard_function_include(tmp_path,
                                                          directive):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(directive + "\n", encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@true\n",
                                       encoding="utf-8")
    (tmp_path / "vars.mk").write_text("X = 1\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_wildcard_preserves_dot_slash(tmp_path):
    """wildcard 要保留 `./` 前缀，便于 ifeq 与拼出的路径比较。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "tests.mk").write_text("test:\n\t@true\n",
                                       encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "ifeq ($(wildcard ./tests.mk),./tests.mk)\n"
        "include tests.mk\n"
        "endif\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_wildcard_absolute_path(tmp_path):
    """绝对路径通配不能因为落在仓库内就被改成相对路径。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    target = tmp_path / "tests.mk"
    target.write_text("test:\n\t@true\n", encoding="utf-8")
    absolute = target.as_posix()
    (tmp_path / "Makefile").write_text(
        f"ifeq ($(wildcard {absolute}),{absolute})\n"
        "include tests.mk\n"
        "endif\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_wildcard_include(tmp_path):
    """include *.mk 要按 make 的 wildcard 语义读取所有匹配文件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text("include *.mk\n", encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@true\n",
                                       encoding="utf-8")
    (tmp_path / "vars.mk").write_text("X = 1\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("directive", [
    "include $(filter %.mk,other.txt tests.mk)",
    "include $(filter-out %.txt,tests.mk other.txt)",
    "include $(subst x,tests,x.mk)",
    "include $(subst ,,tests.mk)",
    "include $(patsubst %.txt,%.mk,tests.txt)",
    "include $(word 2,other.mk tests.mk)",
    "include $(wordlist 2,2,other.mk tests.mk)",
    "include $(wordlist 1,0,other.mk) tests.mk",
    "include $(sort other.mk tests.mk other.mk)",
    "include $(filter %.mk,$(sort other.txt tests.mk))",
    "include $(wildcard $(patsubst %.txt,%.mk,tests.txt))",
])
def test_detect_test_suite_make_more_include_functions(tmp_path, directive):
    """include 文件名里的静态文本函数要按 make 语义展开。

    filter/filter-out/subst/patsubst/word/wordlist/sort 等函数常用于
    拼出 include 路径；不展开会漏掉可运行的 test 目标，把套件降级成
    评分兜底。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(directive + "\n", encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@true\n",
                                       encoding="utf-8")
    (tmp_path / "other.mk").write_text("all:\n\t@true\n",
                                       encoding="utf-8")
    (tmp_path / "other.txt").write_text("", encoding="utf-8")
    (tmp_path / "tests.txt").write_text("", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_join_function_include(tmp_path):
    """include 路径里的 $(join ...) 要按 make 语义拼出实际文件名。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(join a,tests.mk)\n", encoding="utf-8")
    (tmp_path / "atests.mk").write_text("test:\n\t@true\n",
                                        encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_include_function_bad_index_not_a_suite(
        tmp_path):
    """word/wordlist 的非法下标会让 make 在展开时报错，不能忽略。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    for directive in ("include $(word x,tests.mk)",
                      "include $(word 0,tests.mk)",
                      "include $(word +1,tests.mk)",
                      "include $(wordlist 2,x,tests.mk other.mk)",
                      "include $(wordlist 0,1,tests.mk)",
                      "include $(wordlist 1,-1,tests.mk)",
                      "include $(wordlist +1,2,tests.mk)",
                      "include $(wordlist 1,+2,tests.mk)"):
        (tmp_path / "Makefile").write_text(directive + "\n",
                                           encoding="utf-8")
        (tmp_path / "tests.mk").write_text("test:\n\t@true\n",
                                           encoding="utf-8")
        (tmp_path / "other.mk").write_text("all:\n\t@true\n",
                                           encoding="utf-8")
        assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$(wordlist x,x,$(shell true)) test:",
    "$(wordlist 1,x,$(shell true)) test:",
    "$(word x,$(shell true)) test:",
    "$(wordlist $(shell true), $(abspath x), a) test:",
])
def test_detect_test_suite_make_bad_index_with_unsupported_tail(
        tmp_path, line):
    """后续参数含无法静态求值的 shell 时，非法下标仍会让 make 报错。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(line + "\n\t@true\n",
                                       encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_empty_wordlist_arg_not_a_suite(tmp_path):
    """wordlist 第二个参数完全省略时 make 报错，不能静默展开成空串。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(wordlist 1,,tests.mk)\ntest:\n\t@true\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("directive", [
    "include $(filter %.mk)",
    "include $(filter-out %.mk)",
    "include $(subst a,b)",
    "include $(patsubst a,b)",
    "include $(word 1)",
    "include $(wordlist 1,2)",
    "include $(findstring a)",
    "include $(addprefix x)",
    "include $(addsuffix x)",
])
def test_detect_test_suite_make_function_missing_arg_not_a_suite(
        tmp_path, directive):
    """静态函数缺参会让 make 展开时报错，不能把后面的 test 当可运行套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        directive + "\ntest:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("assignment", [
    "X := $(wordlist foo,,x)",
    "X := $(word x,a b)",
    "X := $(word 0,a b)",
    "X := $(addprefix a)",
    "X := $(filter a)",
    "X := $(subst a,b)",
    "X := ok\nX += $(wordlist foo,,x)",
    "export X := $(wordlist foo,,x)",
    "override X := $(wordlist foo,,x)",
    "define X :=\n$(wordlist foo,,x)\nendef",
    "X != $(wordlist foo,,x)",
])
def test_detect_test_suite_make_invalid_immediate_assignment_blocks_suite(
        tmp_path, assignment):
    """`:=`/`+=`/`!=` 右值读取期展开出错时 make 不会执行后面的 test。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        assignment + "\ntest:\n\t@true\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "test:\n\t@true\n$(if $(wordlist $< , $* , foo) ,x ,y):\n\t@true\n",
    "test:\n\t@true\n$(and $(wordlist test foo,,x), y):\n\t@true\n",
    "test:\n\t@true\n$(or $(word 0,a b),y):\n\t@true\n",
])
def test_detect_test_suite_make_condition_function_error_blocks_suite(
        tmp_path, line):
    """if/or/and 求值时展开出的非法下标是读取期错误，不能被吞掉。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(line, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("assignment", [
    "X = $(wordlist foo,,x)",
    "X += $(wordlist foo,,x)",
    "X = ok\nX ?= $(wordlist foo,,x)",
])
def test_detect_test_suite_make_recursive_assignment_not_expanded(
        tmp_path, assignment):
    """递归赋值在使用前不会展开，右值里的错误函数不影响 test 目标。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        assignment + "\ntest:\n\t@true\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("directive,filename", [
    ("include foo\\*.mk\n", "foo*.mk"),
    ("include foo\\?.mk\n", "foo?.mk"),
    ("include foo\\[x\\].mk\n", "foo[x].mk"),
    ("include $(wildcard foo\\*.mk)\n", "foo*.mk"),
    ("include foo\\ bar.mk\n", "foo bar.mk"),
    ("include foo\\#bar.mk\n", "foo#bar.mk"),
])
def test_detect_test_suite_make_escaped_glob_is_literal(tmp_path, directive,
                                                        filename):
    """反斜杠转义的通配符/空格是文件名本身，不能当通配符展开。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(directive, encoding="utf-8")
    (tmp_path / filename).write_text("test:\n\t@true\n",
                                     encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("directive,decoy", [
    ("include foo\\*.mk\n", "foobar.mk"),
    ("include foo\\?.mk\n", "fooX.mk"),
    ("include foo\\[x\\].mk\n", "foox.mk"),
    ("include $(wildcard foo\\*.mk)\n", "foobar.mk"),
])
def test_detect_test_suite_make_escaped_glob_does_not_match_decoy(
        tmp_path, directive, decoy):
    """转义后的通配符只能匹配字面文件名，不能匹配其他文件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(directive, encoding="utf-8")
    (tmp_path / decoy).write_text("test:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_filter_escaped_percent_is_literal(tmp_path):
    """filter 模式里的 \\% 是字面 %，不是通配符。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(filter tests.m\\%,tests.m%)\n", encoding="utf-8")
    (tmp_path / "tests.m%").write_text("test:\n\t@echo ok\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_patsubst_escaped_percent_is_literal(tmp_path):
    """patsubst 的 pattern 里 \\% 是字面 %；替换结果要能命中真实文件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(patsubst tests.m\\%,tests.mk,tests.m%)\n",
        encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@echo ok\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_patsubst_only_first_percent_replaced(tmp_path):
    """patsubst 的 replacement 里只有第一个未转义 % 会被词干替换。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(patsubst tests%,tests.mk%%,tests)\n", encoding="utf-8")
    (tmp_path / "tests.mk%").write_text("test:\n\t@echo ok\n",
                                        encoding="utf-8")
    (tmp_path / "tests.mk").write_text("all:\n\t@true\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_make_pattern_backslash_matches_gnu_make():
    """pattern/replacement 的反斜杠只在紧邻 % 时参与转义。"""
    assert rounds._make_pattern_match("a\\X", "aX") == (False, None)
    assert rounds._make_pattern_match("a\\X", "a\\X") == (True, None)
    assert rounds._make_pattern_subst("a%", "\\%b", "ac") == "%b"
    assert rounds._make_pattern_subst("a%", "\\\\%b", "ac") == "\\cb"
    assert rounds._make_pattern_subst("a%", "X%Y%Z", "abc") == "XbcY%Z"


def test_make_strip_value_comment_matches_gnu_make():
    """变量赋值里的 # 注释按 make 的反斜杠奇偶规则处理。"""
    strip = rounds._make_strip_value_comment
    assert strip("a\\#b") == "a#b"
    assert strip("a\\\\#b") == "a\\"
    assert strip("a\\\\\\#b") == "a\\#b"
    assert strip("a\\\\\\\\#b") == "a\\\\"
    assert strip("a#b") == "a"


def test_make_expand_functions_match_gnu_make_whitespace(tmp_path):
    """patsubst/wordlist/suffix 的空白与空占位语义与 GNU make 一致。"""
    expand = rounds._make_expand_include_function
    assert expand("patsubst", "a,b, a  b ", tmp_path) == " b  b "
    assert expand("patsubst", "a%,x%, a  b ", tmp_path) == "x b"
    # 含 % 的模式分支按词替换，空结果不保留多余空格。
    assert expand("patsubst", "a%,,a b", tmp_path) == "b"
    assert expand("patsubst", "a%,,a x a", tmp_path) == "x"
    assert expand("patsubst", "%,,a b", tmp_path) == ""
    assert expand("patsubst", "a%, ,a b", tmp_path) == "  b"
    # 变量替换引用：转义的 % 是字面后缀，空替换结果同样不占词。
    assert rounds._make_substitute_ref("a b", "a%=") == "b"
    assert rounds._make_substitute_ref("xa%", "a\\%=test") == "xtest"
    assert rounds._make_substitute_ref("xa%", "\\%=test") == "xatest"
    assert expand("patsubst", ",R, ", tmp_path) == " R"
    assert expand("patsubst", ",R,x ", tmp_path) == "x R"
    assert expand("patsubst", ",R,x", tmp_path) == "x"
    assert expand("wordlist", "1,2,  a  b  c ", tmp_path) == "a  b"
    assert expand("wordlist", "2, ,a b", tmp_path) == ""
    # 函数名后的第一个参数会去掉起始空白；逗号后的参数保留空白。
    assert expand("subst", " x,Y,x x", tmp_path) == "Y Y"
    assert expand("subst", "x, foo,x", tmp_path) == " foo"
    assert expand("patsubst", " a%,b%,a a", tmp_path) == "b b"
    assert expand("addprefix", " x,a b", tmp_path) == "xa xb"
    assert expand("addsuffix", " x,a b", tmp_path) == "ax bx"
    assert expand("findstring", " a, a", tmp_path) == "a"
    # 第二个参数完全省略（不是写成空白）时 make 报错，不能当 0。
    with pytest.raises(rounds._MakeRequiredIncludeError):
        expand("wordlist", "1,,a b", tmp_path)
    assert expand("suffix", "foo.o a/b bar.c", tmp_path) == ".o .c"
    assert expand("join", "a,tests.mk", tmp_path) == "atests.mk"
    assert expand("join", "a b,c d", tmp_path) == "ac bd"
    assert expand("join", "a b,c", tmp_path) == "ac b"
    assert expand("join", ",a b", tmp_path) == "a b"
    assert expand("join", "a b,", tmp_path) == "a b"
    with pytest.raises(rounds._MakeRequiredIncludeError):
        expand("join", "a", tmp_path)



def test_make_expand_immediate_value_keeps_argument_space(tmp_path):
    """`:=` 右值的静态函数参数也要按原文定边界：变量展开为空后留下的
    空格属于参数值。`$(subst $x ,test: ,$+)` 是空操作，
    `$(addprefix $(E) , test)` 的前缀是单个空格。"""
    expand = rounds._make_expand_immediate_value
    assert expand("$(subst $x ,test: ,$+)", {}, {}, tmp_path) == ""
    assert expand("$(addprefix $(E) , test)",
                  {"E": ""}, {"E": True}, tmp_path) == " test"


def test_detect_test_suite_make_immediate_argument_space_affects_ifeq(
        tmp_path):
    """`:=` 值的前导空格参与 ifeq 比较，不能因为展开顺序被吞掉。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "E =\n"
        "Y := $(addprefix $(E) , test)\n"
        "ifeq ($(Y), test)\n"
        "test:\n\t@true\n"
        "endif\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None

def test_make_expand_functions_keep_expanded_leading_space(tmp_path):
    """静态函数参数展开后自带的前导空白不能被再次 lstrip 掉。"""
    (tmp_path / "a").write_text("", encoding="utf-8")
    assert rounds._make_expand_include_functions(
        "$(subst ..,\\%, )", tmp_path) == " "
    assert rounds._make_expand_include_functions(
        "$(subst $(subst ..,\\%, ),3,c)", tmp_path) == "c"


def test_make_realpath_trailing_slash_on_file_is_empty(tmp_path):
    """`realpath a/` 在 a 是普通文件时返回空，不能先 abspath 掉尾随斜杠。"""
    (tmp_path / "a").write_text("", encoding="utf-8")
    expand = rounds._make_expand_include_function
    assert expand("realpath", "a/", tmp_path) == ""
    assert expand("realpath", "a", tmp_path) == str(tmp_path / "a")


@pytest.mark.parametrize("makefile", [
    "%:\n\t@echo ok\n",
    "%::\n\t@echo ok\n",
    "t%st:\n\t@echo ok\n",
    "%: ; @echo ok\n",
    "%:\n# comment\n\t@echo ok\n",
    # 同一模式分别用 : 和 :: 定义是合法的，不算具体目标的冒号冲突。
    "%:\n\t@echo ok\n%::\n\t@echo ok\n",
    "%: |\n\t@echo ok\n",
])
def test_detect_test_suite_make_pattern_rule_target(tmp_path, makefile):
    """无依赖且能匹配 test 的模式规则让 make test 可执行。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile, prereqs", [
    ("%: %.c\n\t@echo ok\n", ["test.c"]),
    ("t%t: %.src\n\t@echo ok\n", ["es.src"]),
    ("%: %.c %.h | %.stamp\n\t@echo ok\n",
     ["test.c", "test.h", "test.stamp"]),
    ("%: %.c # comment\n\t@echo ok\n", ["test.c"]),
    # 模式依赖里的 % 不做反斜杠转义：反斜杠是文件名的一部分。
    ("%: pre\\%post\n\t@echo ok\n", ["pre\\testpost"]),
    # 自依赖会被 make 以 circular dependency dropped 忽略。
    ("%: %\n\t@echo ok\n", []),
    ("%: % %.c\n\t@echo ok\n", ["test.c"]),
])
def test_detect_test_suite_make_pattern_rule_existing_prereqs(
        tmp_path, makefile, prereqs):
    """模式规则的依赖都是已存在文件时 make test 也能执行。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    for name in prereqs:
        (tmp_path / name).write_text("", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_pattern_rule_missing_prereq(tmp_path):
    """模式依赖缺失且无其它规则可构建时 make test 失败。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "%: %.c %.h\n\t@echo ok\n", encoding="utf-8")
    (tmp_path / "test.c").write_text("", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    # stem 为空时 make 不会用 test% / %test 匹配 test。
    "test%:\n\t@echo ok\n",
    "%test:\n\t@echo ok\n",
    "%.o:\n\t@echo ok\n",
    # 带依赖、没有 recipe 的模式规则无法静态确认可执行。
    "%: dep\n\t@echo ok\n",
    "%:\n",
    "ifeq (0,1)\n%:\n\t@echo ok\nendif\n",
])
def test_detect_test_suite_make_pattern_rule_not_applicable(tmp_path,
                                                            makefile):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_target_specific_colon_style_not_conflict(
        tmp_path):
    """target-specific 赋值不定义目标，不参与 : / :: 冲突判断。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    for makefile in (
        "test: X=1\ntest::\n\t@echo ok\n",
        "test:: X=1\ntest:\n\t@echo ok\n",
    ):
        (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
        p = subprocess.run(["make", "test"], cwd=tmp_path,
                           capture_output=True, text=True)
        assert p.returncode == 0
        assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_target_words_ignore_variable_internals(
        tmp_path):
    """变量引用内部的 test 不是目标词，不能和真实的 test 规则冲突。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    makefiles = (
        "Z := $(firstword test:)\n"
        "W != $(strip test)\n"
        "test:\n\t@true\n"
        "$(flavor $(abspath test:) , $(flavor test foo, $<)):: a\n"
        "\t@true\n",
        "Z += $(info test/, foo)\n"
        "V = $(abspath test)\n"
        "test:\n\t@true\n"
        "$(origin ./test , $<):: a\n"
        "\t@true\n",
    )
    for makefile in makefiles:
        (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
        p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                           capture_output=True, text=True)
        assert p.returncode == 0
        assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "$(flavor $(abspath test:) , $(flavor test foo, $<)):: a",
    "$(origin ./test , $<):: a",
])
def test_detect_test_suite_make_variable_internal_test_not_a_target(
        tmp_path, line):
    """只有变量引用里出现 test 的目标列表不定义 test 目标。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(line + "\n\t@true\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_pattern_second_percent_is_literal(tmp_path):
    """模式里只有第一个 %% 是通配符，后续 %% 按字面匹配。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(filter %%.mk,tests.mk)\n", encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@echo ok\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_wildcard_function_no_match_is_empty(tmp_path):
    """`$(wildcard missing.mk)` 无匹配时展开为空，不能当字面文件名 include。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include $(wildcard missing.mk)\ntest:\n\t@true\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_wildcard_include_no_match(tmp_path):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include *.mk\ntest:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None

    (tmp_path / "Makefile").write_text(
        "-include *.mk\ntest:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_missing_include_is_not_a_suite(tmp_path):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text("include missing.mk\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_grouped_escaped_semicolon_recipe(tmp_path):
    """grouped 目标没有真 recipe 时，make 4.3 会把 `\;` 当 recipe 分隔符。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text("test &: foo\\;bar\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]
    (tmp_path / "Makefile").write_text("test &: foo\\:bar\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "test&:\n",
    "test&: dep\n",
    # 其他目标的 grouped target 缺 recipe 同样让整份 Makefile 读取失败。
    "foo&:\ntest:\n\t@true\n",
    "foo&: dep\ntest:\n\t@true\n",
    "foo &: dep\ntest:\n\t@true\n",
    "foo&: \\\n\t@true\ntest:\n\t@true\n",
    "test:\ntest::\n\t@true\n",
    "test::\ntest:\n\t@true\n",
    # 冲突目标不是 test 本身时整个 Makefile 也会读取失败。
    "test foo::\n\t@true\nfoo:\n",
    "test:\n\t@true\nother::\nother:\n",
    # 第一个目标规则之前的 recipe 行会让 make 直接停止读取，即使后面
    # 另有合法 test 目标也不会执行。
    "\t@true\ntest:\n\t@true\n",
    "X=1\n\t@true\ntest:\n\t@true\n",
    "test: X=1\n\t@true\ntest:\n\t@true\n",
    "# comment\n\n\t@true\ntest:\n\t@true\n",
    "export private test foo :\t\n\t@true\ntest:\n\t@true\n",
    "unexport test X:=1\n\t@true\ntest:\n\t@true\n",
    "vpath %.c src:x\n\t@true\ntest:\n\t@true\n",
    "override X=1\n\t@true\ntest:\n\t@true\n",
])
def test_detect_test_suite_make_invalid_target_structure(tmp_path, makefile):
    """grouped target 无 recipe / : 与 :: 混用会让 make 直接报错。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "ifeq ($(UNDEFINED),)\ntest:\n\t@true\nendif\n",
    'ifeq "$(UNDEFINED)" ""\ntest:\n\t@true\nendif\n',
    "test$(UNDEFINED):\n\t@true\n",
    "ifeq (1,1)\ntest:\n\t@true\nendif\n",
    "ifeq (0,1)\nall:\n\t@true\nelse\ntest:\n\t@true\nendif\n",
    "ifeq (0,1)\nall:\n\t@true\nelse ifeq (1,1)\ntest:\n\t@true\nendif\n",
    "ifndef X\ntest:\n\t@true\nendif\n",
    "X = 1\nifeq ($(X),1)\ntest:\n\t@true\nendif\n",
    "include vars.mk\nifeq ($(X),1)\ntest:\n\t@true\nendif\n",
    "ifeq (1,1)\nifeq (1,1)\ntest:\n\t@true\nendif\nendif\n",
    'ifeq "a" "a"\ntest:\n\t@true\nendif\n',
    'ifeq " a " " a "\ntest:\n\t@true\nendif\n',
])
def test_detect_test_suite_make_conditional_branch(tmp_path, makefile):
    """只有生效条件分支里的 test 目标才算套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    (tmp_path / "vars.mk").write_text("X = 1\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    # 括号写法的空白只在语法层去掉；变量值展开后自带的首尾空白仍必须
    # 参与比较，否则会把未生效分支里的 test 目标误当成可用套件。
    "X = foo \nifeq ($(X),foo)\ntest:\n\t@true\nendif\n",
    "X = $(subst x, foo,x)\nifeq (foo,$(X))\ntest:\n\t@true\nendif\n",
])
def test_detect_test_suite_make_conditional_expanded_whitespace(
        tmp_path, makefile):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile, expected", [
    # make 的 += 保留追加值自身的尾随空白：值确实是 "foo bar "，
    # 与 "foo bar" 比较不相等；空追加值也不会凭空加一个分隔空格。
    ("X = foo\nX += bar \n"
     'ifeq "$(X)" "foo bar "\ntest:\n\t@true\nendif\n', True),
    ("X = foo\nX += bar \n"
     "ifeq ($(X),foo bar)\ntest:\n\t@true\nendif\n", False),
    ("X = foo\nX +=\n"
     "ifeq ($(X),foo)\ntest:\n\t@true\nendif\n", True),
])
def test_detect_test_suite_make_append_whitespace(tmp_path, makefile,
                                                  expected):
    """+= 的拼接语义要与 make 一致，不能 strip 掉尾随空白。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    result = detect_test_suite(tmp_path)
    assert result == (["make", "test"] if expected else None)


@pytest.mark.parametrize("makefile, expected", [
    # 条件参数的注释转义与赋值一致：奇数反斜杠让 # 变成字面量。
    ("X = foo\\#bar\nifeq ($(X),foo\\#bar)\n"
     "test:\n\t@true\nendif\n", True),
    ("X = a\\\\\\#b\nifeq ($(X),a\\\\\\#b)\n"
     "test:\n\t@true\nendif\n", True),
    ("X = a\\\\\\#b\nifeq ($(X),a\\#b)\n"
     "test:\n\t@true\nendif\n", False),
    # 偶数反斜杠让 # 开始注释，条件缺少右括号/逗号是读取期错误。
    ("X = a\\\\#b\nifeq ($(X),a\\\\#b)\n"
     "test:\n\t@true\nendif\n", False),
])
def test_detect_test_suite_make_conditional_hash_escape(
        tmp_path, makefile, expected):
    """ifeq 参数里的 \\# 要按 make 注释语义去掉反斜杠。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    result = detect_test_suite(tmp_path)
    assert result == (["make", "test"] if expected else None)


def test_detect_test_suite_make_conditional_escaped_comma(tmp_path):
    """条件参数里的反斜杠不转义逗号，第一个逗号仍是参数分隔符。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "ifneq (a\\,b,a\\,b)\ntest:\n\t@true\nendif\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]

    (tmp_path / "Makefile").write_text(
        "ifeq (a\\,b,a\\,b)\ntest:\n\t@true\nendif\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_conditional_bare_paren_boundaries(tmp_path):
    """条件括号只按圆括号配对，反斜杠和裸花括号都不改变参数边界。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    # 反斜杠不转义右括号：两个值都是单个反斜杠，条件为真。
    (tmp_path / "Makefile").write_text(
        "ifeq (\\,\\)\ntest:\n\t@true\nendif\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]

    # 裸花括号不保护逗号：左右值是 `{a` 与 `b},{a,b}`，条件为假。
    (tmp_path / "Makefile").write_text(
        "ifeq ({a,b},{a,b})\ntest:\n\t@true\nendif\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    # 函数参数里的反斜杠同样不转义逗号；`a\,test` 是 `a\` 与
    # `test` 两个参数，if 选中第二参数 test。
    "$(if a\\,test,x):\n\t@true\n",
    "$(and a\\,test,test):\n\t@true\n",
    "$(and x,a\\,test):\n\t@true\n",
])
def test_detect_test_suite_make_function_escaped_comma(tmp_path, makefile):
    """反斜杠不参与函数参数分隔，转义逗号不能吞掉后续参数。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    # 四个参数时 if 选中 b 而不是 test；subst 的最后一个参数是
    # `test,test`，整体不是 test 目标。
    "$(if a\\,b,test,test):\n\t@true\n",
    "$(subst a\\,b,test,test):\n\t@true\n",
    "$(if test\\,x,test,x):\n\t@true\n",
])
def test_detect_test_suite_make_function_escaped_comma_negative(
        tmp_path, makefile):
    r"""把 `\,` 当转义会错切参数并凭空探测出 test 目标。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "ifeq (foo ,foo)\ntest:\n\t@true\nendif\n",
    "ifeq (foo, foo)\ntest:\n\t@true\nendif\n",
])
def test_detect_test_suite_make_conditional_literal_comma_whitespace(
        tmp_path, makefile):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_ifdef_expanded_leading_whitespace(
        tmp_path):
    """ifdef 展开后以空白开头是读取期错误；不能 strip 后误判成已定义。

    变量值尾随空白会被 make 忽略，但前导空白会让 make 报 invalid syntax
    in conditional；探测命中会把必然失败的 make test 当成测试失败。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "Y = 1\nX = $(subst x, Y,x)\nifdef $(X)\ntest:\n\t@true\nendif\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_ifdef_expanded_trailing_whitespace(tmp_path):
    """ifdef 展开后的尾随空白按 make 语义忽略，不能漏掉可运行套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "Y = 1\nX = $(subst x,Y ,x)\nifdef $(X)\ntest:\n\t@true\nendif\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_grouped_target_with_recipe(tmp_path):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    for makefile in ("test&: ;\n", "test&:\n\t@true\n",
                     "test&: dep\n\t@true\n",
                     "test&:\n\t# shell comment\n",
                     "test&:\n\t\n",
                     "foo&:\n\t@true\ntest:\n\t@true\n",
                     "foo &: ; @true\ntest:\n\t@true\n"):
        (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
        assert detect_test_suite(tmp_path) == ["make", "test"], makefile


@pytest.mark.parametrize("makefile", [
    "ifeq (0,1)\ntest:\n\t@true\nendif\n",
    "ifdef X\ntest:\n\t@true\nendif\n",
    "ifeq (1,1)\nall:\n\t@true\nelse\ntest:\n\t@true\nendif\n",
    "ifeq (0,1)\nall:\n\t@true\nelse ifeq (0,1)\ntest:\n\t@true\nendif\n",
    "ifeq (0,1)\nifeq (1,1)\ntest:\n\t@true\nendif\nendif\n",
    'ifeq "a " "a"\ntest:\n\t@true\nendif\n',
])
def test_detect_test_suite_make_inactive_conditional_branch(tmp_path,
                                                           makefile):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    # 未配对 / 重复的 else / 缺失 endif / 游离 endef 都会让 make 在读取
    # 阶段报错停止，即使文件里写了 test 目标也不会被执行。
    # 未生效分支里的 define/endef 仍做词法配对，但 endef 尾随文本不会
    # 结束 define，后面的 endif 被吞掉，同样在读取阶段失败。
    "ifeq (0,1)\ndefine X\nfoo\nendef foo\nendif\n"
    "test:\n\t@echo ok\n",
    "test:\n\t@echo ok\nendif\n",
    "test:\n\t@echo ok\nelse\n",
    "ifeq (1,1)\ntest:\n\t@echo ok\n",
    "ifeq (0,1)\nall:\n\t@true\nelse\ntest:\n\t@echo ok\nelse\n"
    "all2:\n\t@true\nendif\n",
    "ifeq (0,1)\nall:\n\t@true\nelse\ntest:\n\t@echo ok\n"
    "else ifeq (1,1)\nall2:\n\t@true\nendif\n",
    "test:\n\t@echo ok\ndefine X\nfoo\n",
    "test:\n\t@echo ok\nendef\n",
    "test:\n\t@echo ok\ndefine\nfoo\nendef\n",
    "test:\n\t@echo ok\ndefine # c\nfoo\nendef\n",
    "test:\n\t@echo ok\nprivate define\nfoo\nendef\n",
    "test:\n\t@echo ok\nprivate define # c\nfoo\nendef\n",
    "test:\n\t@echo ok\ndefine $(UNDEFINED)\nfoo\nendef\n",
    "test:\n\t@echo ok\n$(UNDEFINED) = x\n",
    "test:\n\t@echo ok\n$(UNDEFINED) := x\n",
    "test:\n\t@echo ok\n = x\n",
    # 单字符/动态变量名展开为空：make 在读取阶段报 empty variable name。
    "test:\n\t@echo ok\n$x = x\n",
    "test:\n\t@echo ok\n$x += x\n",
    "test:\n\t@echo ok\n$: = x\n",
    "test:\n\t@echo ok\n$# = x\n",
    "test:\n\t@echo ok\n$  = x\n",
    "test:\n\t@echo ok\n$(UNDEFINED) += x\n",
    "test:\n\t@echo ok\n$(UNDEFINED) ?= x\n",
    "test:\n\t@echo ok\nundefine\n",
    "test:\n\t@echo ok\nundefine # c\n",
    "test:\n\t@echo ok\nprivate undefine\n",
    "test:\n\t@echo ok\ndefine = x\nfoo\nendef\n",
    "test:\n\t@echo ok\nifeq\nall:\n\t@true\nendif\n",
    "test:\n\t@echo ok\nifeq (a)\nall:\n\t@true\nendif\n",
    "test:\n\t@echo ok\nifdef X Y\nall:\n\t@true\nendif\n",
])
def test_detect_test_suite_make_malformed_directives_not_a_suite(
        tmp_path, makefile):
    """损坏的条件/define 指令会让 make 解析失败，不能探测成可运行套件。

    回归：未配对 endif / else、缺失 endif、重复 else、缺少 endef 与游离
    endef 原先被静默忽略，探测命中后 `make test` 以退出码 2 失败，候选
    被误判成测试失败（应属没有可运行套件）。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "$(error boom)\ntest:\n\t@true\n",
    "ifeq (1,1)\n$(error boom)\nendif\ntest:\n\t@true\n",
    "$(if a,$(error boom),)\ntest:\n\t@true\n",
    "$(or ,$(error boom))\ntest:\n\t@true\n",
    "$(and a,$(error boom))\ntest:\n\t@true\n",
    "$(strip $(error boom))\ntest:\n\t@true\n",
    "X := $(error boom)\ntest:\n\t@true\n",
    "X != $(error boom)\ntest:\n\t@true\n",
    "test: $(error boom)\n\t@true\n",
    "$(error boom):\n\t@true\ntest:\n\t@true\n",
])
def test_detect_test_suite_make_expanded_error_not_a_suite(tmp_path,
                                                            makefile):
    """读取期会执行的 `$(error ...)` 让 make 停止，后面的 test 不算套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "ifeq (0,1)\n$(error boom)\nendif\ntest:\n\t@true\n",
    "$(if ,$(error boom),)\ntest:\n\t@true\n",
    "$(and ,$(error boom))\ntest:\n\t@true\n",
    "X = $(error boom)\ntest:\n\t@true\n",
    "test:\n\t@echo $(error boom)\n",
])
def test_detect_test_suite_make_inactive_or_recipe_error_keeps_suite(
        tmp_path, makefile):
    """未生效分支/递归赋值/recipe 里的 error 不在探测阶段执行。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("snippet", [
    "ifeq (0,1)\ndefine\nfoo\nendef\nendif\n",
    "ifeq (0,1)\nendef\nendif\n",
])
def test_detect_test_suite_make_inactive_directive_errors_ignored(
        tmp_path, snippet):
    """未生效分支里的空 define / 游离 endef 被 make 忽略，不能误伤套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        snippet + "test:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "define X\nfoo\nendef foo\ntest:\n\t@echo ok\n",
    "define X\nfoo\nendef # comment\ntest:\n\t@echo ok\n",
    "X = foo\ndefine $(X)\nbar\nendef\ntest:\n\t@echo ok\n",
    "define X = x\nfoo\nendef\ntest:\n\t@echo ok\n",
    "private define X\nfoo\nendef\ntest:\n\t@echo ok\n",
    "private override define X\nfoo\nendef\ntest:\n\t@echo ok\n",
])
def test_detect_test_suite_make_define_tail_text_still_detected(
        tmp_path, makefile):
    """endef 的尾随文本、define 的赋值符写法只触发 warning，不是解析错误。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "define X\nfoo\nendef\nifdef X\ntest:\n\t@echo ok\nendif\n",
    "define X\nendef\nifndef X\ntest:\n\t@echo ok\nendif\n",
    "define X\nfoo\nendef\nifeq ($(X),foo)\n"
    "test:\n\t@echo ok\nendif\n",
    "define X = x\nfoo\nendef\nifdef X\ntest:\n\t@echo ok\nendif\n",
    "define T\ntest\nendef\n$(T):\n\t@echo ok\n",
    "X = test\ndefine T\n$(X)\nendef\n$(T):\n\t@echo ok\n",
    "define X\nfoo\nendef\nundefine X\nifndef X\n"
    "test:\n\t@echo ok\nendif\n",
    "define X\nendef\nifeq ($(X),)\ntest:\n\t@echo ok\nendif\n",
])
def test_detect_test_suite_make_define_assigns_variable(tmp_path, makefile):
    """define 定义递归变量，后续 ifdef/ifeq 与目标展开要能看到它的值。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_empty_define_ifdef_false(tmp_path):
    """空 define 变量值为空，ifdef 为假，不能探测成套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    makefile = "define X\nendef\nifdef X\ntest:\n\t@echo ok\nendif\n"
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("name", [
    "$(strip )",
    "$(if ,x)",
    "$(if x,,)",
    "$(foreach v,,x)",
    "$(foreach v,a,)",
    "$(call undefined)",
    "$(value X)",
    "$(info x)",
    "$(warning x)",
    "$(subst a,a,)",
    "$(filter-out a,a)",
    "$(wildcard /nonexistent)",
    "$(eval X=1)",
    "$(eval )",
    "$(eval $(info x))",
])
def test_detect_test_suite_make_function_expanded_empty_define_name(
        tmp_path, name):
    """define 名称里的函数展开为空时 make 报 empty variable name。

    回归：define 名称只展开普通变量引用，`define $(strip )` /
    `define $(info x)` 被当成非空名称，后面合法的 test 目标让探测
    返回可运行套件，实际 make 在读取阶段就失败。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        f"define {name}\nbody\nendef\ntest:\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("name", [
    "$(origin X)",
    "$(flavor X)",
    "$(strip X)",
    "$(if x,a,b)",
    "$(foreach v,a,$(v))",
])
def test_detect_test_suite_make_function_expanded_nonempty_define_name(
        tmp_path, name):
    """define 名称展开后非空时仍是合法定义，不能误伤后面的 test 目标。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        f"define {name}\nbody\nendef\ntest:\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "ifeq (0,1)\nall:\n\t@true\nelse ifeq (0,1)\nall2:\n\t@true\n"
    "else ifeq (1,1)\ntest:\n\t@echo ok\nendif\n",
    "ifeq (0,1)\nall:\n\t@true\nelse ifeq (0,1)\nall2:\n\t@true\n"
    "else\ntest:\n\t@echo ok\nendif\n",
])
def test_detect_test_suite_make_else_if_chain_still_detected(tmp_path,
                                                            makefile):
    """else if 链与「else if 后接普通 else」是合法写法，不能误判失败。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "ifeq ($(strip x),x)\ntest:\n\t@true\nendif\n",
    "ifeq ($(subst a,b,a),b)\ntest:\n\t@true\nendif\n",
    "ifeq ($(filter %.mk,tests.mk),tests.mk)\ntest:\n\t@true\nendif\n",
    "ifeq ($(sort b a),a b)\ntest:\n\t@true\nendif\n",
    "ifeq ($(wildcard tests.mk),tests.mk)\ntest:\n\t@true\nendif\n",
    "ifeq ($(if a,b,c),b)\ntest:\n\t@true\nendif\n",
    "ifeq ($(if ,b,c),c)\ntest:\n\t@true\nendif\n",
    "ifeq ($(or ,b,c),b)\ntest:\n\t@true\nendif\n",
    "ifeq ($(and a,b),b)\ntest:\n\t@true\nendif\n",
    "ifeq ($(and a,),)\ntest:\n\t@true\nendif\n",
    "ifeq ($(if ,$(word x,a),test),test)\ntest:\n\t@true\nendif\n",
    "ifeq ($(subst a,$(if a,b,c),a),b)\ntest:\n\t@true\nendif\n",
    "X = 1\nifdef $(strip X)\ntest:\n\t@true\nendif\n",
])
def test_detect_test_suite_make_condition_static_functions(tmp_path,
                                                           makefile):
    """条件里的静态函数与嵌套逗号要按 make 语义求值。

    回归：`ifeq ($(subst a,b,a),b)` 按第一个逗号切分左值，条件被误判为
    不成立；`ifeq ($(strip x),x)` 里的 strip 也未展开。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    (tmp_path / "tests.mk").write_text("all:\n\t@true\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "X = test\nifeq ($(value X),test)\ntest:\n\t@true\nendif\n",
    "X = test\nifeq ($(foreach v,test,$(v)),test)\n"
    "test:\n\t@true\nendif\n",
    "X = test\n$(if $(value X),test,x):\n\t@true\n",
    # value 返回的逗号属于条件值；先展开 value 再切分 if 参数会把
    # `a,b` 当成两个参数，错选分支或丢掉 test。
    "X = a,b\n$(if $(value X),test,x):\n\t@true\n",
    "X = ,x\n$(if $(value X),test,x):\n\t@true\n",
    # 未生效分支里的 foreach 参数边界错误不能让目标行失败；条件必须先
    # 于 foreach 展开（target-specific 赋值的原始目标预检也一样）。
    "$(if test,test,$(foreach v,${a,b},x)):\n\t@true\n",
    # foreach 的循环变量在 body 展开前才绑定，不能先用外层变量表
    # 展开 body 里的条件函数（那会把 test 误算成 y）。
    "X = y\n$(foreach v,test,$(if $(v),test,x)):\n\t@true\n",
    "f = $(if $(1),test,y)\n$(call f,test):\n\t@true\n",
    "f = $(if $(1),test,y)\nifeq ($(call f,test),test)\n"
    "test:\n\t@true\nendif\n",
])
def test_detect_test_suite_make_condition_value_and_local_scope(
        tmp_path, makefile):
    """条件的 value/foreach/call 展开要看清局部变量作用域。

    回归：ifeq 参数里残留 `$(value X)` / `$(foreach ...)` 原文时条件
    被误判为不成立；条件函数扫描器又会在 foreach/call 绑定参数前，
    用外层变量表展开其 body 里的 if/or/and。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    # 反斜杠不转义变量引用的右括号：变量名是 `X\`，引用在 `)` 处结束。
    "X\\ = test\n$(X\\):\n\t@true\n",
    "$(value X\\)\nX=test\n$(X):\n\t@true\n",
    "${value X\\}\nX=test\n$(X):\n\t@true\n",
    # 动态变量名里的 `\)` 是名字的一部分；`$(strip \)` 展开成 `\`，
    # 后面的 test 目标仍可运行。
    "$(strip \\)=test\ntest:\n\t@true\n",
    # 目标列表里的引用同样不能把 `\)` 当转义吞掉，`$(strip \\)foo`
    # 展开成目标名 `\\foo`，后面的 test 目标仍存在。
    "$(strip \\)foo test:\n\t@true\n",
])
def test_detect_test_suite_make_variable_ref_backslash_close(
        tmp_path, makefile):
    r"""变量引用里的反斜杠是名字的一部分，不会吞掉右括号。

    回归：扫描器把 `\)` 当转义整体跳过，导致引用被误判为未闭合，
    后面合法定义的 test 目标被当成没有套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "X = foo\nifeq ($(value X),test)\ntest:\n\t@true\nendif\n",
    "X = y\n$(foreach v,test,$(if $(v),x,y)):\n\t@true\n",
    "f = $(if $(1),x,y)\n$(call f,test):\n\t@true\n",
])
def test_detect_test_suite_make_condition_value_and_local_scope_negative(
        tmp_path, makefile):
    """value/foreach/call 展开后没有 test 目标时不能误报套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "ifeq ($(origin X),undefined)\ntest:\n\t@true\nendif\n",
    "X = 1\nifeq ($(origin X),file)\ntest:\n\t@true\nendif\n",
    "override X = 1\nifeq ($(origin X),override)\n"
    "test:\n\t@true\nendif\n",
    "X := 1\nifeq ($(flavor X),simple)\ntest:\n\t@true\nendif\n",
    "X = 1\nifeq ($(flavor X),recursive)\ntest:\n\t@true\nendif\n",
    "ifeq ($(flavor X),undefined)\ntest:\n\t@true\nendif\n",
    "Y = X\nifeq ($(origin $(Y)),undefined)\ntest:\n\t@true\nendif\n",
    "$(if $(origin X),test,):\n\t@true\n",
    "$(if $(flavor X),test,):\n\t@true\n",
    "ifeq ($(origin PATH),environment)\ntest:\n\t@true\nendif\n",
])
def test_detect_test_suite_make_origin_flavor_functions(tmp_path, makefile):
    """`$(origin)`/`$(flavor)` 按变量表静态求值，条件分支才能选对。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "$(info ignored)\ntest:\n\t@true\n",
    "$(warning ignored)\ntest:\n\t@true\n",
    "$(addprefix $(info ignored),test):\n\t@true\n",
    "$(strip $(warning x) test):\n\t@true\n",
    "$(info $(if ,$(error boom),))\ntest:\n\t@true\n",
])
def test_detect_test_suite_make_info_warning_expand_empty(tmp_path,
                                                           makefile):
    """`$(info)`/`$(warning)` 结果为空，不能把函数原文当成目标名。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "$(info test foo):\n\t@true\n",
    "$(warning test foo):\n\t@true\n",
    "$(info $(if a,test,)):\n\t@true\n",
])
def test_detect_test_suite_make_info_warning_text_not_target(tmp_path,
                                                             makefile):
    """info/warning 参数里的 test 文本不是目标，展开后目标为空。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "X = 1\nifeq ($(origin X),undefined)\ntest:\n\t@true\nendif\n",
    "X := 1\nifeq ($(flavor X),recursive)\ntest:\n\t@true\nendif\n",
    "ifeq ($(flavor X),simple)\ntest:\n\t@true\nendif\n",
    "$(if $(flavor X),,test):\n\t@true\n",
])
def test_detect_test_suite_make_origin_flavor_negative(tmp_path, makefile):
    """origin/flavor 与 make 的实际元数据不一致时不能探测出套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "test = $(1)\n$(call test,test):\n\t@true\n",
    "test = $(1)\n$(call test,test) foo:\n\t@true\n",
    "T = test\nX = $(1)\n$(call X,$(T)):\n\t@true\n",
    "X = $(2)$(1)\n$(call X,test,x) test:\n\t@true\n",
    "X = $(1)\n$(call X,te$(Y)st):\n\t@true\n",
    # call 参数无法静态求值，但 callable 的值是常量，不影响目标名。
    "test = test\n$(call test,$(shell echo dynamic)):\n\t@true\n",
    # 递归赋值的右值读取期不展开，其中的跨括号逗号不触发读取错误。
    "test = test\nX = $(call test,${a,b})\ntest:\n\t@true\n",
])
def test_detect_test_suite_make_call_function_defines_test(tmp_path,
                                                           makefile):
    """`$(call var,...)` 按参数展开变量值，展开出的 test 目标要能探测。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "test = $(1)\n$(call test):\n\t@true\n",
    "$(call undefined,test):\n\t@true\n",
    "X = literal\n$(call X,$(error boom)):\n\t@true\n",
    # call 先按原文切分参数；花括号里的逗号在外层圆括号 call 中仍是
    # 参数分隔符，切出的 `${a` 是 unterminated variable reference。
    "test = test\n$(call test,${a,b}):\n\t@true\n",
    # 花括号 call 里的 `$(strip (a,b))` 同样先被逗号切开，留下未闭合
    # 的 `$(strip (a`，后面的 test 目标不会执行。
    "test = test\n${call test,test,$(strip (a,b))}:\n\t@true\n",
])
def test_detect_test_suite_make_call_function_not_a_suite(tmp_path,
                                                          makefile):
    """call 展开为空或参数触发 error 时，后面的 test 目标要么不存在
    要么不会执行。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_static_args_keep_expanded_space(tmp_path):
    """变量在静态函数参数里展开为空时，其后的空格属于参数值而不是语法
    空白。`$(subst $x ,test: ,$+)` 的替换是空操作，后面的目标行仍只有
    test；先展开变量再按语法空白 lstrip 会把函数算成追加 "test: "，把
    单冒号规则误变成 `test test::` 双冒号冲突。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@true\n"
        "$(addprefix $(firstword test) , $(subst $x ,test: ,$+)):\n"
        "\t@true\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "$(and ,$(wordlist foo,,x)) test:\n\t@true\n",
    "$(if ,$(wordlist foo,,x),) test:\n\t@true\n",
    "$(or test,$(wordlist foo,,x)) test:\n\t@true\n",
    "$(foreach x,,$(wordlist foo,,x)) test:\n\t@true\n",
])
def test_detect_test_suite_make_short_circuit_skips_static_args(tmp_path,
                                                                makefile):
    """if/or/and/foreach 未求值分支里的静态函数参数错误不能让探测失败：
    make 不展开这些分支，后面的 test 目标仍可运行。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "ifeq ($(if a,b,c),x)\ntest:\n\t@true\nendif\n",
    "ifeq ($(or ,,),x)\ntest:\n\t@true\nendif\n",
    "ifeq ($(and a,),x)\ntest:\n\t@true\nendif\n",
    # and 在遇到空参数时立即短路，纯空白展开结果则算非空。
    "ifeq ($(and a,$(if x, ,y)),)\ntest:\n\t@true\nendif\n",
    "ifeq ($(if a,test ),test)\ntest:\n\t@true\nendif\n",
    # if 只取前三个参数；多余的逗号属于 else 分支，目标不是 test。
    "$(if ,b,test,c):\n\t@true\n",
    # 变量展开出的空白对 if 来说是非空值，不能按源码空白去掉。
    "space := $(empty) $(empty)\n$(if $(space),x,test):\n\t@true\n",
])
def test_detect_test_suite_make_condition_functions_negative(tmp_path,
                                                              makefile):
    """if/or/and 求值后不成立时，未生效分支里的 test 目标不算套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "X := $(or $(subst a,test,a),x)\n$(X):\n\t@true\n",
    "$(if a,test,x):\n\t@true\n",
    "$(and a,test):\n\t@true\n",
    "X = test\nifeq ($(or $(X) ,a),test)\ntest:\n\t@true\nendif\n",
    "X = test\nifeq ($(and a,$(X) ),test)\ntest:\n\t@true\nendif\n",
    "X := $(strip $(or ,test))\n$(X):\n\t@true\n",
    "$(if a,test,b,c):\n\t@true\n",
    # foreach 循环体里的空格是展开结果，if 的真值判断不能把它当源码
    # 空白丢掉。
    "$(if $(foreach x,test, ),test,x):\n\t@true\n",
    "space := $(empty) $(empty)\n$(if $(space),test,x):\n\t@true\n",
    "ifeq ($(if $(foreach x,test, ),yes,no),yes)\n"
    "test:\n\t@true\nendif\n",
    # 未生效分支里的非法下标不会被 make 展开，不能因此拒绝套件。
    "$(if ,$(wordlist x,x,foo),test):\n\t@true\n",
])
def test_detect_test_suite_make_condition_functions_in_targets(
        tmp_path, makefile):
    """目标名与条件里的 if/or/and 都要静态展开；or/and 的生效参数去空白。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "ifeq (a,a) junk\ntest:\n\t@echo ok\nendif\n",
    'ifeq "a" "a"junk\ntest:\n\t@echo ok\nendif\n',
    # 未生效分支里的非法条件语法会被 make 忽略；不能因此拒绝后面的套件。
    "ifeq (0,1)\nifeq (a)\nall:\n\t@true\nendif\nendif\n"
    "test:\n\t@echo ok\n",
])
def test_detect_test_suite_make_condition_tail_text_still_detected(
        tmp_path, makefile):
    """条件指令后的多余文本只警告；未生效分支里的非法条件也不报错。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_conditional_missing_include(tmp_path):
    """未生效分支里的必需 include 不会让 make 失败，不能因此漏掉套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "ifeq (0,1)\ninclude missing.mk\nendif\n"
        "test:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]

    (tmp_path / "Makefile").write_text(
        "ifeq (1,1)\ninclude missing.mk\nendif\n"
        "test:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_required_include_error_blocks_suite(tmp_path):
    """必需的 include 读不到时 make 在执行 test 前就失败，不能算有套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include missing.mk\ntest:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_optional_missing_include_keeps_suite(tmp_path):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "-include missing.mk\ntest:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_nested_required_include_error_blocks_suite(
        tmp_path):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "include tests.mk\ntest:\n\t@true\n", encoding="utf-8")
    (tmp_path / "tests.mk").write_text(
        "include missing.mk\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "T = test\n$(T):\n\t@true\n",
    "T := test\n${T}:\n\t@true\n",
    "T ?= test\n$(T):\n\t@true\n",
    "T = $(U)\nU = test\n$(T):\n\t@true\n",
    "T = test\nT += foo\n$(T):\n\t@true\n",
    "T = test\n$(T) foo:\n\t@true\n",
    "T = test\n$(T)&:\n\t@true\n",
    "T = U\n$(T) = test\n$(U):\n\t@true\n",
    "T = U\n$(T) := test\n$(U):\n\t@true\n",
    "T = U\n$(T) += test\n$(U):\n\t@true\n",
    "T = test # c\n$(T)-unit:\n\t@true\n",
    "T = test # c\n$(T)x:\n\t@true\n",
    "T = test # c\n$(T) foo:\n\t@true\n",
    "T = $(subst x,test,x)\n$(T):\n\t@true\n",
    "T := $(subst x,test,x)\n$(T):\n\t@true\n",
    "T = $(filter %test,test)\n$(T):\n\t@true\n",
    "$(subst x,test,x):\n\t@true\n",
    # 普通赋值/undefine 的变量名也可含 / % + @ ! ^ & * ? 等字符：
    # 目标头引用同样要能静态展开。
    "X/Y = test\n$(X/Y):\n\t@true\n",
    "X%Y := test\n$(X%Y):\n\t@true\n",
    "X+Y = test\n${X+Y}:\n\t@true\n",
    "X? = test\n$(X?):\n\t@true\n",
    "X@Y = test\n$(X@Y):\n\t@true\n",
    "X&Y = test\n$(X&Y):\n\t@true\n",
])
def test_detect_test_suite_make_variable_target(tmp_path, makefile):
    """test 目标写在简单变量展开后的规则头里时也要探测到。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    # 变量展开出的 export/unexport 只是目标名；make 在展开前已经完成
    # 指令识别，仍会定义同一行里的 test 目标。
    "$(T) export test:\n\t@true\n",
    "$(T) unexport test:\n\t@true\n",
    "$(T)export test:\n\t@true\n",
    "X = export\n$(X) test:\n\t@true\n",
    "X = unexport\n$(X) test:\n\t@true\n",
    "X = export\n$(X) foo test:\n\t@true\n",
])
def test_detect_test_suite_make_expanded_export_is_target(tmp_path, makefile):
    """展开后才变成 export/unexport 的行仍是目标列表，不能漏掉 test。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    # 变量展开后以 foo=bar 开头的目标列表仍是规则；make 在展开前
    # 就完成了赋值/规则判定，不能反过来按展开结果当成赋值。
    "$(T) foo=bar test:\n\t@true\n",
    "$(T) test=1 test:\n\t@true\n",
    "$(T) foo\\=bar test:\n\t@true\n",
])
def test_detect_test_suite_make_expanded_assignment_like_target(
        tmp_path, makefile):
    """展开后看似赋值的动态目标行仍要探测出 test。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "T = test-unit\n$(T):\n\t@true\n",
    "T = test\n$(T)-unit:\n\t@true\n",
    "$(T):\n\t@true\nT = test\n",
    "T = test\n$(T) := x\n",
    "T = test\nundefine T\n$(T):\n\t@true\n",
    "T = test\nprivate undefine T\n$(T):\n\t@true\n",
    "T = test\nexport undefine T\n$(T):\n\t@true\n",
    "T = test\nprivate export undefine T\n$(T):\n\t@true\n",
    "T = test\nundefine T # c\n$(T):\n\t@true\n",
    "X/Y = test\nundefine X/Y\n$(X/Y):\n\t@true\n",
    "X%Y = test\nprivate undefine X%Y\n$(X%Y):\n\t@true\n",
])
def test_detect_test_suite_make_variable_target_negative(tmp_path, makefile):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    # make 在读取阶段把反斜杠-换行（及两侧空白）压成一个空格：
    # `T = test \\` + `  unit` 的 T 是 "test unit"，目标列表含 test。
    "T = test \\\n  unit\n$(T):\n\t@echo ok\n",
    "T = test\nT += \\\n foo\n$(T):\n\t@echo ok\n",
    "T = test \\\n# comment\n$(T):\n\t@echo ok\n",
    # 条件行也能跨续行
    "ifeq (x,\\\n x)\ntest:\n\t@echo ok\nendif\n",
    # include 前的变量赋值跨续行
    "T = other.mk \\\n tests.mk\ninclude $(T)\n",
])
def test_detect_test_suite_make_continued_assignment_detected(tmp_path,
                                                              makefile):
    """跨反斜杠续行的变量/条件/include 按 make 语义合并后仍要探测到。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@echo ok\n",
                                       encoding="utf-8")
    (tmp_path / "other.mk").write_text("all:\n\t@true\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("slashes, has_suite", [
    (1, False),
    (2, True),
    (3, False),
    (4, True),
])
def test_detect_test_suite_make_recipe_backslash_parity(tmp_path, slashes,
                                                        has_suite):
    """recipe 行尾反斜杠按奇偶决定是否续行；偶数后的 test: 仍是真目标。

    回归：负向后顾只看「反斜杠+换行」，把 `\\`（转义反斜杠、不续行）
    后面的 test 目标也当成 recipe 续行，漏掉可运行套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "all:\n\t@echo " + "\\" * slashes
        + "\ntest:\n\t@echo RAN\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert (p.returncode == 0 and "RAN" in p.stdout) is has_suite
    expected = ["make", "test"] if has_suite else None
    assert detect_test_suite(tmp_path) == expected


def test_detect_test_suite_make_comment_continuation_swallows_target(tmp_path):
    """注释行末尾的反斜杠会继续吞掉下一行，规则里的 test 不能算套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "# comment \\\ntest:\n\t@echo ok\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "T = test\n$(T:test=test):\n\t@true\n",
    "T = test-unit\n$(T:test-unit=test):\n\t@true\n",
    "T = test.x\n$(T:.x=):\n\t@true\n",
    "T = test\n$(T:%=%):\n\t@true\n",
    "T = te\n$(T:=st):\n\t@true\n",
    "T = tesst\n$(T:tesst=test):\n\t@true\n",
    "T = a.o\n$(T:%.o=test):\n\t@true\n",
])
def test_detect_test_suite_make_substitution_reference(tmp_path, makefile):
    """变量替换引用 $(T:old=new) / $(T:%=%) 要按 make 语义展开目标名。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_substitution_reference_include(tmp_path):
    """include 文件名里的变量替换引用同样要展开。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "T = tests.txt\ninclude $(T:.txt=.mk)\n", encoding="utf-8")
    (tmp_path / "tests.mk").write_text("test:\n\t@true\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]

    # 转义的 % 是字面后缀：xa% 的后缀 a% 换成 xtest.mk。
    (tmp_path / "Makefile").write_text(
        "T = xa%\ninclude $(T:a\\%=test.mk)\n", encoding="utf-8")
    (tmp_path / "xtest.mk").write_text("test:\n\t@true\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    # 变量名本身由变量展开得到：内层先展开成 B，再用 B 的值查表。
    "A = B\nB = test\n$($(A)):\n\t@true\n",
    "A = B\nB = C\nC = test\n$($($(A))):\n\t@true\n",
    # 变量名恰好与函数同名且后面没有空白时，make 按变量而不是函数处理。
    "sort = test\n$(sort):\n\t@true\n",
    "A = B\nB = test\nfoo $($(A)):\n\t@true\n",
])
def test_detect_test_suite_make_dynamic_target_variable(tmp_path, makefile):
    """`$($(A))` 这类动态变量名要按 make 语义展开后再判断 test 目标。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "$($(A)) = x",
    "$($(A)) := x",
    "$($(A)) += x",
    "$($(A)) ?= x",
    "$($(A)) != echo x",
    "export $($(A)) = x",
    "export $($(A)):= x",
    "${${A}} = x",
])
def test_detect_test_suite_make_computed_assignment_empty_name(tmp_path,
                                                               line):
    """变量名由变量展开得到且为空时 make 报错，不能探测出 test 套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "A = B\nB = X\n$($(A)) = test\n$(X):\n\t@true\n",
    "A = B\nB = X\n$($(A)) := test\n$(X):\n\t@true\n",
    "A = B\nB = X\n${${A}} = test\n${X}:\n\t@true\n",
    "A = B\nB = C\nC = X\n$($($(A))) = test\n$(X):\n\t@true\n",
])
def test_detect_test_suite_make_computed_assignment(tmp_path, makefile):
    """嵌套变量名赋值的名字要展开后再查表，定义的 test 目标不能漏掉。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "$(strip ):=x",
    "$(if ,x)=1",
    "$(and ,x)=1",
    "$(firstword ):=x",
    "?=x",
    "+=x",
    "!=x",
    ":=x",
    "::=x",
    "=x",
    r"A\:B=x",
    r"A\ B=x",
    r"test\:$(X)=1",
    r"$(info $(if x,a\ b)) = :",
])
def test_detect_test_suite_make_empty_or_invalid_assignment_blocks_suite(
        tmp_path, line):
    """顶层赋值名展开为空/含非法转义字符时 make 直接停止读取。

    回归：`$(strip ):=x` / `?=x` 被普通赋值正则当成合法语句，后面的
    test 目标被探测成可运行套件；`A\:B=x` 实际报 missing separator。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "X$(Y)=1",
    "X$(Y)?=test",
    "X$(Y) =$$",
    "A;B=x",
    "X;=x",
    "$(if x,y,)=1",
    "$(subst ,,x)=1",
    "private  +=a b",
    "export  ?=test",
    "override ::=x",
    "test:$(if x, ,)=1",
    "test:$(subst x, ,x)=1",
    r"$(patsubst a\ b,test,$$) = x",
    r"$(subst a\ b,test,$$) = x",
    r"$(info $(if x,a\ b))foo = x",
    "$(eval x=1)foo = x",
    # 规则头左侧的 eval 也会展开并应用其中的赋值，后面的目标名随之可见。
    "$(eval X=test)$(X):\n\t@true\n",
    "$(eval $(eval x=1))foo = x",
    "$(eval x=1) #c := $$",
])
def test_detect_test_suite_make_dynamic_assignment_keeps_suite(tmp_path,
                                                               line):
    """动态变量名/含分号名字/修饰词当名字的合法赋值不能漏掉 test 套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "$(eval x)foo = 1",
    "$(eval x) = 1",
    # eval 的参数只展开一次，`$$` 在生成的 Makefile 行里是字面 `$`，
    # 会继续展开/形成非法行，不能当成普通未解析引用放过。
    "$(eval $$)foo = 1",
    "$(eval $$,x)foo = 1",
    "$(eval $$$$)foo = 1",
    "X = test\n$(eval $$(X))foo = 1",
    "$(eval $(eval x))foo = 1",
    "$(eval $(eval x=1),x)foo = 1",
])
def test_detect_test_suite_make_eval_invalid_assignment_name_blocks_suite(
        tmp_path, line):
    """赋值名里的 eval 参数会作为 Makefile 行解析，`$(eval x)` 缺少分隔符。

    原先只处理 eval 里的赋值、忽略其他行，`$(eval x)foo = 1` 被当成
    合法动态赋值，后面的 test 目标因此被误判成可运行套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$(eval x) #c := $$",
    "$(eval x) # comment",
])
def test_detect_test_suite_make_eval_line_with_trailing_comment_blocks_suite(
        tmp_path, line):
    """eval 行尾注释不阻止 eval 在读取期执行。

    `$(eval x) #c := $$` 去掉注释后仍是独立的 eval 调用，参数 `x`
    缺少分隔符，make 读取失败；原先整行只有 eval 的识别被注释打断，
    后面的 test 目标因此被误判成可运行套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "$(eval x):\ntest:\n\t@echo ok\n",
    "$(eval x) test:\n\t@echo ok\n",
    "X = test\n$(eval $(X)):\ntest:\n\t@echo ok\n",
    "test: $(eval x) = x\ntest:\n\t@echo ok\n",
    "test: foo $(eval x)\ntest:\n\t@echo ok\n",
    "X = test\ntest: $(X) $(eval x) = x\ntest:\n\t@echo ok\n",
    "test: A := $(eval x)\ntest:\n\t@echo ok\n",
    "%: $(X) := $(eval x)\ntest:\n\t@echo ok\n",
])
def test_detect_test_suite_make_eval_in_rule_target_blocks_suite(
        tmp_path, makefile):
    """规则头左侧的 eval 参数没有分隔符时 make 读取失败。

    `$(eval x):` 先展开成 `x:`，eval 参数 `x` 本身不是合法的 Makefile
    行；原先只展开赋值名里的 eval，规则头里的调用被当成空变量引用，
    后面的 test 目标因此被误判成可运行套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "test ::= $(eval x)\ntest:\n\t@echo ok\n",
    "X := $(eval x)\ntest:\n\t@echo ok\n",
    "x?y != $(eval x)\ntest:\n\t@echo ok\n",
    "./x != $(eval x)\ntest:\n\t@echo ok\n",
    "X = test\n$(X) := $(eval x)\ntest:\n\t@echo ok\n",
    "$(origin X) ::= $(eval x)\ntest:\n\t@echo ok\n",
    "X := a\nX += $(eval x)\ntest:\n\t@echo ok\n",
])
def test_detect_test_suite_make_eval_in_immediate_assignment_value_blocks_suite(
        tmp_path, makefile):
    """立即赋值右值的 eval 先于变量引用展开，参数行错误会让 make 停止。

    `X := $(eval x)` / `test ::= $(eval x)` 都会先解析 eval 参数 `x`
    并报 missing separator；原先只校验赋值名里的 eval，右侧被当成普通
    变量值，后面的 test 目标因此被误判成可运行套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "ifeq ($(eval x),a)\nendif\ntest:\n\t@echo ok\n",
    "ifeq ($(basename,$(eval x),-lfoo),)\nendif\n"
    "test:\n\t@echo ok\n",
    "ifeq ($(info $(eval x)),)\nendif\ntest:\n\t@echo ok\n",
    "ifeq ($(warning $(eval x)),)\nendif\ntest:\n\t@echo ok\n",
    "X := $(if $(eval x),a,b)\ntest:\n\t@echo ok\n",
    "X := $(if $(basename,$(eval x),-lfoo),a,b)\n"
    "test:\n\t@echo ok\n",
])
def test_detect_test_suite_make_eval_in_condition_blocks_suite(
        tmp_path, makefile):
    """条件参数在读取期立即展开，其中的 eval 同样会解析参数行。

    `ifeq ($(eval x),a)` 的 eval 参数 `x` 没有分隔符，make 在判定条件
    前就报 missing separator；原先条件展开只处理静态函数/引用，eval
    原文被当成非空条件值，后面的 test 目标被误判成可运行套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "export $(eval x)",
    "vpath $(eval x)",
    "include $(eval x)",
])
def test_detect_test_suite_make_eval_in_directive_blocks_suite(
        tmp_path, line):
    """include/vpath/export 的参数在读取期展开，eval 也在此时执行。

    `export $(eval x)` / `include $(eval x)` 里的 eval 参数 `x` 没有
    分隔符，make 报 missing separator；原先非规则指令整行跳过，后面的
    test 目标被误判成可运行套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "foo bar = x",
    "$(X) $(strip ) := x",
    "foo\\ bar = x",
    "$x $y = z",
    "override foo bar := x",
])
def test_detect_test_suite_make_assignment_lhs_space_blocks_suite(
        tmp_path, line):
    """独立赋值左侧在运算符前有空白分隔的多个词时 make 读取失败。

    `foo bar = x` 报 missing separator，`foo bar := x` 报 empty variable
    name；只有运算符前的尾部空白会被去掉。原先动态名扫描在第一个空白
    处停止，`$(X) $(strip ) := x` 被当成普通行，后面的 test 目标因此
    被误判成可运行套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "X = test\nY = x\n" + line + "\ntest:\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "export X Y = z",
    "export $(X) $(strip ) := z",
    "foo bar = x: y",
])
def test_detect_test_suite_make_assignment_lhs_space_keeps_suite(
        tmp_path, line):
    """export 多变量行与带规则冒号的延迟运算符行仍是合法 Makefile。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "X = test\n" + line + "\ntest:\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "$(addprefix $(shell ))",
    "$(addsuffix $(shell echo x))",
    "$(subst $(shell ),x)",
    "$(patsubst x,$(shell ))",
])
def test_detect_test_suite_make_function_arity_with_unresolved_arg(
        tmp_path, line):
    """函数参数个数与参数能否静态求值无关。

    `$(addprefix $(shell ))` 只有一个参数，make 展开 shell 后仍报
    insufficient number of arguments；原先遇到 shell 就跳过整个函数，
    后面的 test 目标被误判成可运行套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + ":\n\t@echo ok\ntest:\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$(foreach,$(if x,a,b)) = 1",
    "$(call,$(if x,a,b)) = 1",
    "test: $(foreach,$(if x,a,b))=1",
])
def test_detect_test_suite_make_nested_ref_in_unspaced_function_name(
        tmp_path, line):
    """`$(foreach,...)` / `$(call,...)` 没有空白时是普通变量引用。

    变量名里的嵌套 if 会在读取期展开，整个名字仍未定义 -> 空变量名；
    原先扫描器把无空白的 foreach/call 也当成函数调用整段跳过，嵌套
    条件不展开，名字原文被当成非空，后面的 test 目标被误判成可运行。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "$(eval test:)",
    "$(eval test: )",
    "$(eval test: ; @true)",
    "$(eval test:; @true)",
    "$(eval test: ;)",
    "$(eval X=test)\n$(X):\n\t@true\n",
    "$(eval X := test:)\n$(X) ; @true\n",
])
def test_detect_test_suite_make_eval_defines_test(tmp_path, makefile):
    """`$(eval ...)` 在读取时解析参数，参数里的 test 目标要能探测到。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_eval_include_reads_targets(tmp_path):
    """`$(eval include ...)` 的文件在读取期就解析，里面的 test 目标要能
    探测到；只把 eval 留到第二遍会让这种套件被当成没有测试。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "inc.mk").write_text("test:\n\t@true\n",
                                      encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "$(eval include inc.mk)\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_eval_required_include_error(tmp_path):
    """`$(eval include missing.mk)` 同样是读取期 fatal，后面的 test 目标
    不会执行，不能探测成套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "$(eval include missing.mk)\ntest:\n\t@true\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_eval_optional_include_missing(tmp_path):
    """eval 里的可选 include 缺失时 make 继续读取，后面的 test 目标可用。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "$(eval -include missing.mk)\ntest:\n\t@true\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "$(eval test:)\n\t@echo hi\n",
    "test:\n\t@echo ok\n$(eval X=1)\n\t@true\n",
    "$(eval foo)\n",
])
def test_detect_test_suite_make_eval_does_not_keep_target_context(
        tmp_path, makefile):
    """eval 行不建立当前目标，其后的 tab 行仍是 recipe commences 错误。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    # 展开后的变量名（含空格）未定义，整体是空目标而不是名为 test 的目标。
    "A = test foo\n$($(A)):\n\t@true\n",
    "A = test foo\n$($(A) test):\n\t@true\n",
    "V = foo\n$($(addsuffix test,test) $(V)):\n\t@true\n",
    # 函数名后有空白时是函数调用，空结果不定义 test。
    "sort = test\n$(sort ):\n\t@true\n",
])
def test_detect_test_suite_make_dynamic_target_variable_negative(tmp_path,
                                                                 makefile):
    """动态变量名未定义 / 函数参数为空时不能把引用里的 test 字面量算目标。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "T = a.o\n$(T:%.c=test):\n\t@true\n",
    "T = foo bar\n$(T:baz=test):\n\t@true\n",
    "$(UNDEFINED:%.c=test):\n\t@true\n",
    # 赋值里的 \\# 是字面 #，变量值是 a#b；替换引用的 old 不是 a#b。
    "T = a\\#b\n$(T:a\\#b=test):\n\t@true\n",
])
def test_detect_test_suite_make_substitution_reference_negative(tmp_path,
                                                                makefile):
    """替换后不产生 test 目标（或变量未定义）时不能探测成套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile, expected", [
    # 参数展开后自带逗号，仍属于同一个函数参数，不能重新按逗号切分。
    ("$(findstring $(filter-out a,test,test foo),"
     "$(firstword test foo)):\n\t@true\n", False),
    # 无 % 但含空白的 patsubst 模式按连续词序列匹配。
    ("V = test foo\n$(addsuffix $(findstring  , ),"
     "$(patsubst test test,bar,test test)):\n\t@true\n", False),
    ("V = test foo\n$(filter-out $(patsubst test foo,x,test foo),"
     "$(filter-out dir/test,test foo)):\n\t@true\n", True),
])
def test_detect_test_suite_make_nested_function_arguments(tmp_path, makefile,
                                                          expected):
    """嵌套函数的参数边界与含空白 patsubst 模式要按 make 语义展开。"""
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert (detect_test_suite(tmp_path) is not None) is expected


@pytest.mark.parametrize("makefile, expected", [
    # 裸括号也参与函数引用的配对，其中的逗号不能当参数分隔符。
    ("$(if x,test,y(z)):\n\t@true\n", True),
    ("$(if (x,y),test,z):\n\t@true\n", True),
    ("${if {x,y},test,z}:\n\t@true\n", True),
    ("f = $(if x,test,y(z))\n$(call f):\n\t@true\n", True),
    # 只有与引用自身相同的括号参与配对；另一种括号里的逗号仍是分隔符。
    ("$(if {x,y},test,z):\n\t@true\n", False),
    ("${if (x,y),test,z}:\n\t@true\n", False),
    # 另一种括号里的右括号也不会结束外层引用；`${foo)}` 是未定义变量。
    ("$(if x,test,${foo)}):\n\t@true\n", False),
    ("${if x,test,$(foo{)}:\n\t@true\n", False),
    ("$(if x,test,${subst {a,b},X,{a,b}}):\n\t@true\n", True),
])
def test_detect_test_suite_make_bare_parentheses_in_function_arguments(
        tmp_path, makefile, expected):
    """函数参数扫描按 make 语义配对裸括号，不能提前结束引用。"""
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    assert (detect_test_suite(tmp_path) is not None) is expected


def test_detect_test_suite_make_single_char_variable_target(tmp_path):
    """`$T` 是 make 的单字符变量写法，目标名也要按变量展开。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "T = test\n$T:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "$(addsuffix $@,test):\n\t@true\n",
    "$(addprefix $<,test):\n\t@true\n",
    "$@ test:\n\t@true\n",
    "$(or $@,test):\n\t@true\n",
    "$(if $@,,test):\n\t@true\n",
    "ifeq ($@,)\ntest:\n\t@true\nendif\n",
    # 原文不是 recipe，展开后自动变量消失留下的 tab 只是目标列表空白。
    "$<\ttest:\n\t@true\n",
    "$<\tfoo test:\n\t@true\n",
])
def test_detect_test_suite_make_automatic_variables_expand_empty(
        tmp_path, makefile):
    """目标/条件读取期的 `$@` 等自动变量为空，函数参数里的也要展开。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "$(if $@,test,):\n\t@true\n",
    "$(and $@,test):\n\t@true\n",
    "$(wordlist $@ , test ,a b):\n\t@true\n",
])
def test_detect_test_suite_make_empty_automatic_argument_blocks_suite(
        tmp_path, makefile):
    """空自动变量参与的函数要么分支不生效，要么暴露 make 的参数错误。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_define_body_is_data(tmp_path):
    """define 体里的 include/test 不是 Makefile 指令，不能误读或误判。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "define BODY\ninclude missing.mk\nendef\ntest:\n\t@true\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]

    (tmp_path / "Makefile").write_text(
        "define BODY\ntest:\n\t@true\nendef\nall:\n\t@true\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) is None

    # 多行 define 覆盖旧值后，$(BODY) 的目标行展开不会得到 test。
    (tmp_path / "Makefile").write_text(
        "BODY = test\ndefine BODY\nfoo\nbar\nendef\n"
        "$(BODY):\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None

    (tmp_path / "Makefile").write_text(
        "ifeq (0,1)\ndefine BODY\ntest:\n\t@true\nendef\nendif\n"
        "test:\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_define_special_name_target(tmp_path):
    """define 名称含 ? 等特殊字符时，目标头里的引用也要展开。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    for ref in ("$(X?)", "${X?}"):
        (tmp_path / "Makefile").write_text(
            f"define X?\ntest\nendef\n{ref}:\n\t@true\n",
            encoding="utf-8")
        assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    # 多行 define 的前导空行不会让最后一行成为目标名的一部分。
    "define BODY\n\ntest\nendef\n$(BODY):\n\t@echo ok\n",
    "define BODY\n\n\n  test  \nendef\n$(BODY):\n\t@echo ok\n",
    # 最后一行的前导空白会把前面的行与它分开，test 仍是独立目标。
    "define BODY\nfoo\n test\nendef\n$(BODY):\n\t@echo ok\n",
    "define BODY\nfoo\nbar\n test\nendef\n$(BODY):\n\t@echo ok\n",
    # 注释行在前、最后一行带前导空白时，同样能执行 test。
    "define BODY\n# c\n test\nendef\n$(BODY):\n\t@echo ok\n",
    # 续行后接空行时，反斜杠-换行替换出的空格留在行尾；丢掉它会
    # 让 `test \n` 变成 `test\n`，换行粘进目标名而不是分隔目标。
    "define BODY\ntest\\\n\nendef\n$(BODY):\n\t@echo ok\n",
    "define BODY\ntest\\\n\nfoo\nendef\n$(BODY):\n\t@echo ok\n",
])
def test_detect_test_suite_make_multiline_define_target(tmp_path, makefile):
    """多行 define 展开后仍可能定义可执行的 test 目标，不能一律置空。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0


@pytest.mark.parametrize("ref, expected", [
    ("$(firstword $(BODY))", False),
    ("$(lastword $(BODY))", True),
])
def test_detect_test_suite_make_multiline_define_function_target(
        tmp_path, ref, expected):
    """多行 define 交给函数展开时要保留真实换行，不能只取最后一行。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        f"define BODY\nfoo\n test\nendef\n{ref}:\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert (p.returncode == 0) == expected
    assert bool(detect_test_suite(tmp_path)) == expected


def test_detect_test_suite_make_define_trailing_space_splits_target(tmp_path):
    """上一行以空格结尾时，换行也会把最后一行拆成独立目标。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "define BODY\nfoo \ntest\nendef\n$(BODY):\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("body", [
    "\t test",
    "test \n# c",
    "# c\n test",
])
def test_detect_test_suite_make_define_body_comment_and_tab(tmp_path, body):
    """define 体里的 # 是字面量，前导制表符也只是目标列表分隔。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        f"define BODY\n{body}\nendef\n$(BODY):\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    # 最后一行没有前导空白且前面有非空行时，整段值是一个目标名。
    "define BODY\nfoo\ntest\nendef\n$(BODY):\n\t@echo ok\n",
    "define BODY\n# c\ntest\nendef\n$(BODY):\n\t@echo ok\n",
    # 尾部空行/文本会让 test 不再是独立目标。
    "define BODY\n\ntest\n \nendef\n$(BODY):\n\t@echo ok\n",
    "define BODY\nfoo\n test\nx\nendef\n$(BODY):\n\t@echo ok\n",
])
def test_detect_test_suite_make_multiline_define_not_a_target(tmp_path,
                                                              makefile):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_repeated_include_reprocessed(tmp_path):
    """同一 include 文件被包含两次时要各处理一次：条件分支依赖的变量
    可能在两次之间变化，只处理第一次会漏掉第二次才生效的 test 目标。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "tests.mk").write_text(
        "ifeq ($(T),test)\ntest:\n\t@true\nendif\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "T = other\ninclude tests.mk\nT = test\ninclude tests.mk\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_makefile_list_updates(tmp_path):
    """MAKEFILE_LIST 要按 include 顺序追加，lastword 才能指向子目录文件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "mk").mkdir()
    (tmp_path / "mk" / "vars.mk").write_text("", encoding="utf-8")
    (tmp_path / "mk" / "tests.mk").write_text("test:\n\t@true\n",
                                              encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "include mk/vars.mk\n"
        "include $(dir $(lastword $(MAKEFILE_LIST)))tests.mk\n",
        encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_makefile_list_uses_matched_names(tmp_path):
    """通配符 include 的 MAKEFILE_LIST 要记录实际文件，不是 `*.mk`。

    `include mk/*.mk` 后 `lastword $(MAKEFILE_LIST)` 必须是最后一个匹配
    文件；记录通配符表达式会让条件判断走错分支，漏掉可运行套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "mk").mkdir()
    (tmp_path / "mk" / "a.mk").write_text("", encoding="utf-8")
    (tmp_path / "mk" / "tests.mk").write_text("", encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "include mk/*.mk\n"
        "ifeq ($(lastword $(MAKEFILE_LIST)),mk/tests.mk)\n"
        "test:\n\t@true\nendif\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]

    # `./tests.mk` 在 make 的 MAKEFILE_LIST 里规整为 `tests.mk`。
    (tmp_path / "Makefile").write_text(
        "include ./only.mk\n"
        "ifeq ($(lastword $(MAKEFILE_LIST)),only.mk)\n"
        "test:\n\t@true\nendif\n", encoding="utf-8")
    (tmp_path / "only.mk").write_text("", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_include_variable_order(tmp_path):
    """include 插入位置要保留变量赋值顺序，规则头才能按 make 语义展开。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "vars.mk").write_text("T = test\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "include vars.mk\n$(T):\n\t@true\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]

    (tmp_path / "tests.mk").write_text(
        "$(T):\n\t@true\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "T = test\ninclude tests.mk\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "test := x",
    "test::= x",
    "test:::= x",
    "test : = x",
    "test ?= x",
    "test += x",
    "test != echo x",
    "test = x",
    "test: foo=bar",
    "test: 1=2",
    "test: .FOO=1",
    "test: CFLAGS := -g",
    "test: export X=1",
    "test: private X:=1",
    "test: override X+=1",
    "test: X?=1",
    "test: X!=echo 1",
    "test: X=1 dep",
    "test: X:::=1",
    "test: export X:::=1",
    "test: override X :::=1",
    "test: X/Y:::=1",
    # GNU make 的变量名可含 / % + @ ! ^ & * 等字符：只有赋值、没有
    # 可执行 test 目标时仍不能当作测试套件（% 与 := 组合尤其容易被
    # 误认成静态模式规则 `test: %.o: %.c`）
    "test: X/Y=1",
    "test: X+Y=1",
    "test: X@Y=1",
    "test: X%Y=1",
    "test: X%Y:=1",
    "test: X%Y::=1",
    "test: X&Y!=true",
    "test: X*Y?=1",
    "test: X\\;Y=1",
    "test: X\\ =1",
    "test: X\\\\=1",
    "foo test: X=1",
    "foo test := x",
    "test foo: export X=1",
    "foo test:::",
    # 行首 export/unexport 是导出指令而不是规则头：make 把 test 当变量名
    # 导出、不定义目标，`make test` 以退出码 2 失败，探测命中会把候选
    # 误判成测试失败（leading 空白 / tab / 续行展开后仍是同一指令）
    "export test:",
    "export foo test:",
    "unexport test:",
    " export test:",
    "export\ttest:",
    "export \\\n test:",
    "unexport \\\n test:",
])
def test_detect_test_suite_make_variable_assignment_is_not_a_suite(tmp_path,
                                                                   line):
    """变量赋值行不是 test 目标：`make test` 会以退出码 2 失败，探测命中
    会被误判为「测试失败」拒绝候选（应属「没有可运行套件」）。

    target-specific 变量赋值（`test: VAR=...`）同样只作用于目标、不定义
    可执行目标，不能按套件探测。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(line + "\nall:\n\t@echo hi\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "test foo\\;bar: ;",
    "foo\\;bar test: ;",
    "test foo\\;bar:: ;",
    "test foo\\;bar: ; @:",
])
def test_detect_test_suite_make_escaped_semicolon_target_with_recipe(
        tmp_path, line):
    r"""\; 是目标名的一部分，但 make 只有在同一逻辑行有 ; 时才接受。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(line + "\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "foo\\;bar:",
    "foo\\;bar: dep",
    "foo\\;bar: X=1",
    "private foo\\;bar:",
    "override foo\\;bar:",
    "foo\\;bar:: dep",
    "foo\\;bar&: dep",
])
def test_detect_test_suite_make_other_escaped_semicolon_target_blocks_suite(
        tmp_path, line):
    r"""其他目标名里的 `\;` 缺少同行命令分隔符时 make 读取失败。

    回归：原先只校验命中 test 的规则行，`private foo\;bar:` 等会让
    make 在读取阶段报 missing separator，即使别处有合法 test 目标也
    不会执行，探测必须返回「没有可运行套件」。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\n\t@true\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "foo\\;bar: ;",
    "foo\\;bar: dep ; @true",
    "foo: a\\;b",
    "foo: X\\;Y=1",
])
def test_detect_test_suite_make_other_escaped_semicolon_target_keeps_suite(
        tmp_path, line):
    r"""同行有命令分隔符（或 `\;` 不在目标名里）时 make 仍可执行 test。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "test:",
    "test::",
    "test :",
    " test:",
    " \ttest:",
    "  \t test :",
    "test:; echo ok",
    "test: dep",
    "foo test:",
    "test test2:",
    "foo test bar:",
    "test: %.o: %.c",
    "test: %.o : %.c",
    "test: %.o: %.c: extra",
    "test: %.o:: %.c",
    "test:: %.o:: %.c",
    # GNU make 4.3 把带 % 的三冒号写法当静态模式规则（即使告警仍会
    # 执行 recipe），不是 target-specific 赋值。
    "test: X%Y:::=1",
    "test: foo%bar\\ baz: dep",
    # unexport 不是 target-specific 变量修饰符：make 把它当依赖名，
    # `test` 目标本身仍然存在（缺依赖会失败，但不是「没有套件」）。
    "test: unexport X=1",
    # GNU make 4.3 grouped target：& 与冒号之间不需要空白
    "test&:",
    "test&::",
    "test&: dep",
    "foo test&:",
    "test test2&:",
    "test: ${X:--x}",
    "foo ${X:--x} test:",
    "$(X:--x) test:",
    "test:: %.o: %.c",
    "test::dep",
    # 其他目标名里的转义冒号 / 井号 / 空格是名字本身，不影响 test 目标
    "foo\\:bar test:",
    "foo\\#bar test:",
    "test foo\\:bar:",
    "test foo\\#bar:",
    "test foo\\ bar:",
    "foo\\% test:",
    # 反斜杠空格是目标名的一部分；后面的普通空格仍分隔下一个目标。
    "foo\\ bar test:",
    "foo\\ \tbar test:",
    # 变量名里的空白就是分隔符（即使写成反斜杠转义）；`foo\ x=y`
    # 不是赋值，后面的 test 仍是目标列表的一部分。
    "foo\\ x=y test:",
    "foo\\ bar=1 test:",
    "foo\\ bar\\ baz=1 test:",
    # target-specific 变量名里的空白同样终止变量名：这些是 test 的前置
    # 依赖名，不是 target-specific 赋值，test 目标仍然存在。
    "test: X\\ Y=1",
    "test: X\\#Y=1",
    "test: X\\:Y=1",
    # 第一个变量名 token 展开为空时，后面的 X=1 只是前置依赖，不是
    # target-specific 赋值；test 目标仍然存在。
    "test: $(U) X=1",
    "test: $(U)override X=1",
    # 没有未转义分号时，\; 结束依赖列表，后面的 := / :::= 不再属于
    # 规则头；make 仍定义 test（依赖 a / X 等缺失时失败但不是没套件）。
    "test: a\\;b X:=1",
    "test: X\\;Y:::=1",
    "test: export X\\;Y:::=1",
    "test: export $(U) X=1",
    "test:: $(U) X=1",
    # `endef` 只是第一个词时是普通目标名/变量名，不是游离指令。
    "endef test:",
    "endef test% test ::",
    "endef = x\ntest:",
    # 目标列表里的未转义等号是词分隔符：`foo test=1:` 定义 foo / test /
    # 1；`+=` / `?=` 的运算符前缀也被吸收（test 仍是目标）。
    "test foo=bar:",
    "test foo\\=bar:",
    "foo test=1:",
    "foo test =1:",
    "foo bar test==1:",
    "foo test+=1:",
    "foo test?=1:",
    "all test=1 test:",
    "all foo=bar test:",
    "all foo\\=bar test:",
    "all X = test:",
    "all override test=1 test:",
    "test foo = bar:",
    "test foo += bar:",
    "test foo?=bar:",
    "test foo=bar baz:",
    # 目标列表末尾紧贴分隔符的 `$` 必须成对：`$$` 是字面 `$`，
    # 单个 `$` 会与 `:` 拼成变量引用并报 missing separator。
    "test $$:",
    "test $ x:",
    "test $ :",
    # 单字符变量引用会吃掉后一个字符：`$:` 吃掉第一个冒号后第二个冒号
    # 仍是规则分隔符；`$ ` 吃掉空白后下一词与前一词粘连（这也意味着
    # 粘出来的名字不能再算独立的 test）。
    "test test$::",
    "test$::",
    "test $$$::",
    "test \\$::",
    "foo $ test:",
    "test$x:",
    "test $#:",
    "test $;::",
    "test$  test:",
    "test test$ x:",
    # make 会规范化目标名前导的 `./`：`make test` 仍能执行 `./test`。
    "./test:",
    ".//test:",
    "././test:",
    "foo ./test:",
    # 首目标是普通名时，后面混入模式目标只会触发 deprecated 警告，
    # make 仍把精确的 test 定义成普通目标并执行。
    "foo %test test:",
    "foo % test:",
    "foo %test %bar test:",
    "test %test:",
    "\\%foo %test test:",
    # private / override 后跟规则头时只是目标名，不是指令；它们后面的
    # recipe 属于真实目标，不能误判成「首个目标前出现 recipe」。
    "private foo:\n\t@true\ntest:",
    "override foo:\n\t@true\ntest:",
    "private foo: dep\n\t@true\ntest:",
    # 目标名里带 & 的静态模式规则同样不是 grouped target。
    "private export&: %.o: %.c\n\t@true\ntest:",
])
def test_detect_test_suite_make_target_forms_still_detected(tmp_path, line):
    """真正的 test 目标（含双冒号规则、前导空格、同行命令）仍要探测到。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(line + "\n\techo ok\n",
                                       encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("gap", [
    "X=1",
    "X := 1",
    "export X=1",
    "override X=1",
    "private X=1",
    "undefine X",
    "vpath %.c src",
    "test: X=1",
    "foo&: X=1",
    "define X\nfoo\nendef",
    "private undefine X",
    "override undefine X",
    "private undefine ?&: dep",
    "$(info hi)",
    "$(eval X=1)",
    "$:",
    "$(X)",
    "$x ;",
    "$: ;",
])
def test_detect_test_suite_make_recipe_after_non_rule_not_a_suite(
        tmp_path, gap):
    """规则/recipe 之间夹着赋值、指令或 define 时，后面的 tab 行是
    recipe commences before first target，make 读取阶段直接失败。

    回归：探测只检查第一个目标之前是否有 recipe，一旦见过规则就把后续
    所有 tab 行都当成该规则的 recipe，导致这类 Makefile 被误判成可运行
    套件。真正的注释和空行不会清空当前目标，仍需放行。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo ok\n" + gap + "\n\t@true\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("gap", [
    "",
    "# comment",
    "\n# comment\n",
])
def test_detect_test_suite_make_recipe_after_comment_keeps_suite(tmp_path,
                                                                 gap):
    """空行/注释不会清空当前目标，后面的 tab 行仍是有效 recipe。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo ok\n" + gap + "\n\t@true\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("included", [
    "",
    "X=1\n",
    "# comment\n",
    "foo:\n",
    "foo:\n\t@true\n",
])
def test_detect_test_suite_make_recipe_after_include_not_a_suite(
        tmp_path, included):
    """include 指令会清空当前目标，之后紧跟的 tab 行不是 recipe。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "inc.mk").write_text(included, encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo ok\ninclude inc.mk\n\t@true\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "test:::",
    "test::::",
    "test::: dep",
    "test: :x",
    "test: : = x",
    "foo test: :x",
    "test: a::b",
    "test: dep::x",
    "test: a:b",
    "test: dep :x",
    "test: dep: x",
    "test: foo bar: dep",
    # `&` 与冒号之间有空白时是名为 test& 的普通目标，不是 grouped test
    "test& :",
    # 变量展开为空也不能把 `test&$(T):` 变回 grouped test 目标。
    "test&$(T):",
    "test: foo\\%: dep",
    "test:: dep: x",
    "test::X=1",
    "test::export X=1",
    "test:: += x",
    "foo test::X=1",
    "test: foo\\=bar",
    "test::foo\\=bar",
    # 转义空白后的赋值运算符不是 target-specific 赋值：make 会把第二个
    # 冒号当成静态模式分隔符并报 target pattern contains no '%'。
    "test: X\\ Y:=1",
    "test: $(U) X:=1",
    # 后面还有未转义分号时，前面的 \; 属于依赖名，依赖里的冒号仍非法。
    "test: a\\;b:c ; recipe",
    # test 之前出现未转义的 % / 分号会让整行不是可执行的目标规则；
    # 首目标本身是模式时（%test test: / foo% %test test:）仍是 fatal。
    "foo% test:",
    "%test test:",
    "% test:",
    "foo% %test test:",
    "foo;bar test:",
    # 反斜杠后的整段空白都属于同一个目标名，不再分隔出 test。
    "foo\\ test:",
    "foo\\  test:",
    "foo\\\ttest:",
    "foo\\ \\ test:",
    "test ${X:--x}",
    "test \\\n ${X:--x}",
    "a test ${X:--x} X=1",
    "test foo;bar:",
    # 目标名里的 \; 没有同行命令分隔符时 make 报 missing separator。
    "foo\\;bar test:",
    "test foo\\;bar:",
    # 行首目标名里的 \= 会让整行按变量赋值解析，不定义 test。
    "foo\\=bar test:",
    "test=1 test:",
    "all = test:",
    "override test=1 test:",
    "private test=1 test:",
    "export test=1 test:",
    # 紧跟 test 的赋值形式不是目标（`test foo = bar:` 才是）
    "test = bar:",
    "test ?= bar:",
    "test += bar:",
    "test != bar:",
    "test := bar:",
    "test ::= bar:",
    "test foo:=bar:",
    "test foo::=bar:",
    # 反斜杠转义/感叹号后的等号不是分隔符，目标名是 test=1 / test!；
    # `:=` 会让 make 报 empty variable name，同样没有 test 目标。
    "foo test\\=1:",
    "foo test!=1:",
    "foo test:=1:",
    "foo test:=",
    # 末尾奇数个 `$` 紧贴规则分隔符时 make 报 missing separator。
    "test $:",
    "test $$$:",
    "test x$:",
    "test \\$:",
    # `$ ` 吃掉唯一的词间空白后，后面的 test 被粘成 testtest；
    # `test$$` 是名为 test$ 的目标，都不能算可执行的 test。
    "test$ test:",
    "test$:",
    "test$$:",
    "foo$ test:",
    "test$\ttest:",
    # 只有前导 `./` 会被规范化，`../test` / `foo/./test` 不是 test 目标。
    "../test:",
    "foo/./test:",
    "./../test:",
    # 续行里紧跟 test 的赋值形式同样不是目标（续行压成空格后与
    # `test = bar:` 等价）
    "test \\\n = bar:",
    "test \\\n test \\\n : \\\n :",
])
def test_detect_test_suite_make_invalid_target_is_not_a_suite(tmp_path, line):
    """三冒号、空白+冒号、依赖里带冒号等写法都不是合法 test 目标
    （GNU make 报 missing target pattern / target pattern contains no
    '%'），探测命中会让 `make test` 以退出码 2 误伤候选。静态模式规则
    test: %.o: %.c 与 test: %.o:: %.c 的冒号由 target-pattern 里的 % 放行。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(line + "\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "test: a:b",
    "test::: dep",
    "test: :x",
    "test: = x",
    "test:::= x",
    "test:: = x",
    "test: X:::=1",
    "test: export X:::=1",
])
def test_detect_test_suite_make_invalid_extra_rule_blocks_suite(tmp_path,
                                                                line):
    """已有合法 test 规则时，另一条非法 test 规则仍会让 make 读取失败。

    回归：探测原先只跳过非法规则头，看到别处的合法 test 规则就返回套件；
    但 make 在读取阶段遇到非法规则会直接退出，根本不会执行 test。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo ok\n" + line + "\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "foo: a:b",
    "foo bar: a:b",
    "foo &: a:b",
    "foo: a:b ; @true",
    "foo: :x",
    "foo::: dep",
    "foo:: a:b",
    "foo: = x",
    "foo:: = x",
    "foo: +=x",
    "foo: !=x",
    "foo: =%.o: %.c",
    "foo $:",
    "foo x$: ;",
    "override $: X:=1",
    "override \\$: # c",
    r"override a\\: = 1",
    r"foo\$\\: : ;",
    r"override *\$\\: : ;",
    r"\;test&:: ; #x",
    r"?,\\: = 1",
    "$: X = 1",
    "$x$: dep",
    "$ $: X=1",
    "x$::$(X)=1",
    "x$:::$(X)=1",
    "x$::::$(X)=1",
    "x$:X:::=1",
    "x$:X\\:Y=1",
    "foo$:X:::=1",
    "foo$:X\\:Y=1",
    "$:X:::=1",
    "foo $::$(X)=1",
    "foo $:::$(X)=1",
    "foo $: =x",
    "foo $:+=1",
    "foo $:!=1",
    "foo $::=x",
    "foo $:::=x",
    "foo $:$(X)::=1",
    "foo $:$:X=1",
    "foo foo$:$:X=1",
    "foo $::$(X):=1",
    "&&::$(U) X=1",
    "&&::$(X) X=1",
    "&$::$(X)=1",
    "&&$::$(X)=1",
])
def test_detect_test_suite_make_invalid_other_rule_blocks_suite(tmp_path, line):
    """其他目标的非法规则头同样会让 make 读取失败，不能只看 test 行。

    回归：`foo: a:b` 等规则的第二个冒号不是合法静态模式规则，make 在
    读取阶段报 target pattern contains no '%'；`foo: = x` 报 empty
    variable name。即使另有合法 test 规则，整份 Makefile 也不会执行，
    探测必须返回「没有可运行套件」。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo ok\n" + line + "\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_dynamic_name_triple_colon(tmp_path):
    """`$(X):::=x` 不是 GNU make 4.3 的赋值：X 非空时读取即报空变量名，
    X 为空时目标列表为空、make 接受。探测必须跟随变量值，不能一律吞成
    动态变量赋值。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "X=foo\n$(X):::=x\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None

    (tmp_path / "Makefile").write_text(
        "X=\n$(X):::=x\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_value_target_conflict_not_a_suite(tmp_path):
    """`$(value X)` 返回原始值 test，后面的 :: 与已有 test: 冲突。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "X=test\ntest:\n\t@echo ok\n$(value X)::\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_undefined_value_keeps_suite(tmp_path):
    """未定义变量的 `$(value X)` 展开为空，后面的目标列表不能凭空报错。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo ok\n$(value X): a:b\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_value_target_detected(tmp_path):
    """`$(value X)` 展开出的 test 目标必须探测到套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "X=test\n$(value X):\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "$(foreach x,test foo,$(x))::",
])
def test_detect_test_suite_make_foreach_target_conflict_not_a_suite(
        tmp_path, line):
    """foreach 展开出的目标与已有 test 规则冲突时 make 读取失败。

    回归：`$(foreach x,test foo,$(x))::` 会同时定义 test/foo 的 :: 规则，
    与前面的 `test:` 冲突；不展开函数原文会漏掉这个冲突，把必然失败的
    Makefile 误判成可运行套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo ok\n" + line + "\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$(foreach x,foo test,$(x)):",
    "$(foreach x,$(TESTS),$(x)):",
    "$(foreach x,foo test,$(foreach y,$(x),$(y) z)):",
])
def test_detect_test_suite_make_foreach_target_detected(tmp_path, line):
    """foreach 展开出 test 目标的合法规则必须探测到套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "TESTS := foo test\n" + line + "\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "$:$(X)=1",
    "$x$:$(X)=1",
    "$:X = 1",
])
def test_detect_test_suite_make_bare_dollar_dynamic_assignment_keeps_suite(
        tmp_path, line):
    """`$:` 吃掉冒号后剩下动态变量名赋值时 make 接受，不能误拒套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "X=foo\ntest:\n\t@echo ok\n" + line + "\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("assignment", [
    "F = $(foreach x,foo test,$(x))",
    "F := $(foreach x,foo test,$(x))",
    "F = foo\nF += $(foreach x,bar test,$(x))",
    "define F\n$(foreach x,foo test,$(x))\nendef",
])
def test_detect_test_suite_make_foreach_in_variable_detected(
        tmp_path, assignment):
    """变量值里的 foreach 也要展开，否则 $(F): 定义 test 会漏检。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        assignment + "\n$(F):\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("assignment", [
    "F = $(foreach x,test foo,$(x))",
    "F := $(foreach x,test foo,$(x))",
])
def test_detect_test_suite_make_foreach_in_variable_conflict(
        tmp_path, assignment):
    """变量值里的 foreach 展开出 test 的 :: 时也要识别冒号风格冲突。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo ok\n" + assignment + "\n$(F)::\n",
        encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "foo: %.o: %.c",
    "foo: a\\:b",
    "foo: X:=1",
    "foo: export X::=1",
    "foo: +X=1",
    "export foo:bar",
    "vpath %.c src:x",
    "vpath test:$(X)=1",
    "$:",
    "$x$:",
    "foo $$:",
    "foo $: a:b",
    "foo $::",
    "foo $: %.o: %.c",
    "$: a:b",
    "$: ;",
    "$x$: a:b",
    r"a\; = x",
    r"a\ = x",
])
def test_detect_test_suite_make_valid_other_rule_keeps_suite(tmp_path, line):
    """其他目标的合法规则/指令不能把可运行 test 套件误拒。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo ok\n" + line + "\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("prefix", [
    ":?= $(X)\n\t@true\n",
    ": test=: X:=1\n\t@true\n",
    "&: test+= X=1\n\t@true\n",
    ": dep\n\t@true\n",
    "&:\n\t@true\n",
])
def test_detect_test_suite_make_empty_target_recipe_keeps_suite(
        tmp_path, prefix):
    """空目标列表/裸 `&:` 后的 recipe 行不触发「首个目标前 recipe」误判。

    make 把这类行当成可挂 recipe 的空目标/特殊 grouped 目标，后面的
    合法 test 目标仍可执行；探测不能把 tab 行一律当成读取错误。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        prefix + "test:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "define = x",
    "define += x",
    "define +=:: X::=1",
    "define ?= x",
    "define != echo hi",
    "private define = x",
    "override define += x",
    "export define := x",
])
def test_detect_test_suite_make_define_named_assignment_keeps_suite(
        tmp_path, line):
    """`define = x` 是名为 define 的变量赋值，不是 define 指令。

    回归：按 define 指令解析会把后面的 test 目标吞进变量值，进而误报
    缺少 endef，把可运行套件判成没有测试。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "foo&: X=1",
    "foo&: X:=1",
    "foo&:: X=1",
    "&&:: X=1",
    "private foo&: X=1",
    "override foo bar&: X:=1",
])
def test_detect_test_suite_make_grouped_target_assignment_keeps_suite(
        tmp_path, line):
    """带 & 的目标只做 target-specific 变量赋值时不需要 recipe。

    回归：原先把所有 `foo&: dep` 形式的行都当成缺少 recipe 的 grouped
    target，导致后面合法的 test 套件被误判成不可运行。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "test:= x",
    "test ::= x",
    "test: X=1",
    "test::X=1",
    "test: X::=1",
    "test: export X=1",
    "test: private X:=1",
    "test: override X+=1",
    "test: X != echo hi",
    "test: 1=2",
    # 反斜杠转义的分号/空白属于 target-specific 变量名本身。
    "test: X\\;Y=1",
    "test: X\\ =1",
    "test: X\\\\=1",
    # 变量引用与赋值名粘在同一 token 时仍是 target-specific 赋值；
    # 全行展开后即使空变量消失也不能把 test 当成可执行目标。
    "test: $(U)X=1",
])
def test_detect_test_suite_make_valid_assignment_keeps_suite(tmp_path, line):
    """合法变量赋值/target-specific 赋值不能把别处的可运行 test 套件拒掉。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo ok\n" + line + "\n", encoding="utf-8")
    p = subprocess.run(["make", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_exact_target_alongside_suffixed(tmp_path):
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test-unit:\n\techo unit\ntest:\n\techo ok\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("text", [
    # 反斜杠续行压成一个空格：与单行的目标列表写法等价，test 同样是
    # 可执行目标，漏检会让可运行的套件被降级成评分兜底
    "test \\\n\tfoo:\n\techo ok\n",
    "foo \\\n\ttest:\n\techo ok\n",
    "test \\\n foo:\n\techo ok\n",
    "test\\\n:\n\techo ok\n",
    "foo\\\n\ttest:\n\techo ok\n",
    "test \\\n\tfoo \\\n\tbar:\n\techo ok\n",
])
def test_detect_test_suite_make_continued_target_list_detected(tmp_path,
                                                               text):
    """目标列表跨反斜杠续行时仍要识别 test：make 把续行与周围空白压成
    一个空格（`test \\` + `foo:` 与 `test foo:` 等价、`test\\` + `:` 与
    `test :` 等价），漏检会让可运行的测试套件被当成「没有套件」降级
    成评分兜底。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(text, encoding="utf-8")
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
    assert detect_test_suite(tmp_path) == ["/usr/bin/npm", "test"]


def test_detect_test_suite_npm_uses_resolved_executable(tmp_path, monkeypatch):
    """探测结果必须带上 which 解析出的完整路径。

    Windows 上 npm 实际是 npm.cmd；CreateProcess 对无扩展名的程序只补
    .exe，裸 "npm" 启动会以 WinError 2 失败，套件被误判成不可用。"""
    real_which = shutil.which

    def which(name, *args, **kwargs):
        if name == "npm":
            return r"C:\Program Files\nodejs\npm.cmd"
        return real_which(name, *args, **kwargs)

    monkeypatch.setattr("xuen.rounds.shutil.which", which)
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "vitest run"}}', encoding="utf-8")
    assert detect_test_suite(tmp_path) == [
        r"C:\Program Files\nodejs\npm.cmd", "test"]


def test_detect_test_suite_npm_with_bom(tmp_path, monkeypatch):
    """带 UTF-8 BOM 的 package.json（Windows 记事本常见）仍要探测到。

    npm 自己会忽略 BOM 并正常执行 test 脚本，但探测器按 utf-8 读取后
    json.loads 报「Unexpected UTF-8 BOM」，套件被误判为不存在。"""
    _fake_npm(monkeypatch)
    (tmp_path / "package.json").write_text(
        '\ufeff{"scripts": {"test": "vitest run"}}', encoding="utf-8")
    assert detect_test_suite(tmp_path) == ["/usr/bin/npm", "test"]


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


@pytest.mark.parametrize("relpath", [
    "vendor/dep/dep.go",
    "testdata/fixture.go",
    "_ignored/gen.go",
    ".hidden/gen.go",
])
def test_detect_test_suite_go_ignored_dirs_not_a_suite(tmp_path, monkeypatch,
                                                       relpath):
    """`go test ./...` 不匹配的位置（vendor/testdata/._ 开头目录）里的
    .go 文件不能算套件：只命中这些位置时 go 报「matched no packages」
    并以退出码 1 失败，探测会把「没有可用测试」误记成测试失败。"""
    _fake_go(monkeypatch)
    (tmp_path / "go.mod").write_text("module example.com/demo\n",
                                     encoding="utf-8")
    path = tmp_path / relpath
    path.parent.mkdir(parents=True)
    path.write_text("package demo\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_go_ignored_file_names_not_a_suite(tmp_path,
                                                             monkeypatch):
    """以 . 或 _ 开头的 .go 文件同样被 go 工具忽略，不算套件。"""
    _fake_go(monkeypatch)
    (tmp_path / "go.mod").write_text("module example.com/demo\n",
                                     encoding="utf-8")
    (tmp_path / "_generated.go").write_text("package demo\n",
                                            encoding="utf-8")
    (tmp_path / ".hidden.go").write_text("package demo\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_go_files_without_mod_not_a_suite(tmp_path,
                                                            monkeypatch):
    """没有 go.mod 时根目录的 .go 也不能探测成套件：模块模式下从仓库根
    执行 `go test ./...` 会因找不到 go.mod 失败，探测命中只会把「没有
    可用测试」误记成测试失败并拒绝候选。"""
    _fake_go(monkeypatch)
    (tmp_path / "main.go").write_text("package main\n", encoding="utf-8")
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


def test_tests_mode_pending_when_pytest_collects_nothing(ws, tmp_path):
    """pytest 配置把测试文件全排除时退出码 5（未收集到测试）：
    这不是测试失败，而是没有可执行的验证 → 挂起等待用户评分。

    回归：探测只看 test_*.py 是否存在，随后 `pytest -q` 因 python_files
    只匹配 check_*.py 而返回 5，原先把「没有测试可跑」误判成测试失败并
    拒绝候选（auto 模式还会跳过兜底评分）。
    """
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_never.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8")
    (repo / "pytest.ini").write_text(
        "[pytest]\npython_files = check_*.py\n", encoding="utf-8")
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="tests", repo=str(repo))
    guard.start()
    write_idea(state_path, "pytest 收集不到测试时的想法")
    assert guard.on_round_end(1) == "pending"
    assert read_idea(state_path) == "（暂无）"


def test_tests_mode_pending_when_go_matches_no_packages(ws, tmp_path):
    """仓库的 .go 文件全被构建约束排除时，go test ./... 以退出码 1 报
    「matched no packages」：这不是测试失败，而是没有可执行的验证 →
    挂起等待用户评分。

    回归：探测只看是否有 go 文件，随后的 go test 因 //go:build windows
    在 Linux 上匹配不到包，原先把「没有可测试的包」误判成测试失败并
    拒绝候选（auto 模式还会跳过兜底评分）。
    """
    if not shutil.which("go"):
        pytest.skip("go 不可用")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text("module example.com/nopkg\n",
                                 encoding="utf-8")
    (repo / "x_windows.go").write_text(
        "//go:build windows\n\npackage nopkg\n", encoding="utf-8")
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="tests", repo=str(repo))
    guard.start()
    write_idea(state_path, "go 构建约束排除全部包时的想法")
    assert guard.on_round_end(1) == "pending"
    assert read_idea(state_path) == "（暂无）"


def test_tests_mode_pending_when_go_has_no_test_files(ws, tmp_path):
    """模块只有 .go 源码、没有任何 *_test.go 时 go test 以 0 退出并打印
    [no test files]：没有可执行的验证 → 挂起等待用户评分，不能当成测试
    全部通过把候选采纳为最佳。"""
    if not shutil.which("go"):
        pytest.skip("go 不可用")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text("module example.com/notests\n",
                                 encoding="utf-8")
    (repo / "main.go").write_text(
        "package main\n\nfunc main() {}\n", encoding="utf-8")
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="tests", repo=str(repo))
    guard.start()
    write_idea(state_path, "go 没有测试文件时的想法")
    assert guard.on_round_end(1) == "pending"
    assert read_idea(state_path) == "（暂无）"


def test_auto_mode_falls_back_when_go_has_no_test_files(ws, tmp_path):
    """auto 模式下 go 包没有测试文件时不算验证通过：应转兜底评分。"""
    if not shutil.which("go"):
        pytest.skip("go 不可用")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text("module example.com/notests\n",
                                 encoding="utf-8")
    (repo / "main.go").write_text(
        "package main\n\nfunc main() {}\n", encoding="utf-8")
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="auto", fallback="ai",
                       repo=str(repo), judge=lambda p: (True, "评分: 8"))
    guard.start()
    write_idea(state_path, "go 没有测试文件时的想法")
    assert guard.on_round_end(1) == "adopted"
    assert guard.best["verifier"] == "ai"


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


def test_run_suite_pytest_no_tests_collected_is_unavailable(tmp_path):
    """pytest 的退出码 5 是「没有收集到测试」，不是测试失败：套件实际
    没有验证任何东西，按不可用处理（转兜底评分 / 挂起），不能拒绝候选。"""
    (tmp_path / "test_x.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\npython_files = check_*.py\n", encoding="utf-8")
    res = rounds.run_suite(
        [sys.executable, "-m", "pytest", "-q"], tmp_path, 30.0)
    assert (res.available, res.ok) == (False, False)
    assert "未收集到测试" in res.reason


def test_run_suite_go_no_packages_is_unavailable(tmp_path):
    """go test ./... 报「matched no packages」时套件实际没有验证任何东西，
    按不可用处理（转兜底评分 / 挂起），不能拒绝候选。"""
    if not shutil.which("go"):
        pytest.skip("go 不可用")
    (tmp_path / "go.mod").write_text("module example.com/nopkg\n",
                                     encoding="utf-8")
    (tmp_path / "x_windows.go").write_text(
        "//go:build windows\n\npackage nopkg\n", encoding="utf-8")
    res = rounds.run_suite(["go", "test", "./..."], tmp_path, 60.0)
    assert (res.available, res.ok) == (False, False)
    assert "未匹配到任何包" in res.reason
    assert "matched no packages" in res.detail


def test_run_suite_go_no_test_files_is_unavailable(tmp_path):
    """模块里有 .go 源码但没有任何 *_test.go 时，go test ./... 以退出码 0
    打印 [no test files]。这与 pytest 退出码 5 同义（没有可执行的验证），
    不能当成「测试全部通过」：tests 模式会把未验证候选直接采纳为最佳，
    auto 模式也会跳过兜底评分。"""
    if not shutil.which("go"):
        pytest.skip("go 不可用")
    (tmp_path / "go.mod").write_text("module example.com/notests\n",
                                     encoding="utf-8")
    (tmp_path / "main.go").write_text(
        "package main\n\nfunc main() {}\n", encoding="utf-8")
    res = rounds.run_suite(["go", "test", "./..."], tmp_path, 60.0)
    assert (res.available, res.ok) == (False, False)
    assert "no test files" in res.detail


def test_run_suite_go_with_some_real_tests_is_a_pass(tmp_path):
    """混有真实测试的模块仍按通过处理：[no test files] 的包不能把同一
    命令里其他包真正跑过的测试否掉。"""
    if not shutil.which("go"):
        pytest.skip("go 不可用")
    (tmp_path / "go.mod").write_text("module example.com/mixed\n",
                                     encoding="utf-8")
    (tmp_path / "main.go").write_text(
        "package main\n\nfunc main() {}\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "sub.go").write_text("package sub\n", encoding="utf-8")
    (sub / "sub_test.go").write_text(
        "package sub\n\nimport \"testing\"\n\nfunc TestX(t *testing.T) {}\n",
        encoding="utf-8")
    res = rounds.run_suite(["go", "test", "./..."], tmp_path, 60.0)
    assert (res.available, res.ok) == (True, True)


@pytest.mark.parametrize("detail", [
    "?   \texample.com/m\t[no test files]",
    "?   \texample.com/a\t[no test files]\n"
    "?   \texample.com/b\t[no test files]",
    "go: downloading example.com/dep v1.0.0\n"
    "?   \texample.com/m\t[no test files]",
])
def test_go_no_tests_ran_detects_all_no_test_files(detail):
    assert rounds._go_no_tests_ran(detail) is True


@pytest.mark.parametrize("detail", [
    "?   \texample.com/m\t[no test files]\n"
    "ok  \texample.com/sub\t0.002s",
    "?   \texample.com/m\t[no test files]\n"
    "ok  \texample.com/sub\t(cached)",
    "ok  \texample.com/m\t0.002s",
    "",
])
def test_go_no_tests_ran_false_when_some_package_ran(detail):
    assert rounds._go_no_tests_ran(detail) is False


@pytest.mark.parametrize("makefile", [
    "test:\n",
    ".PHONY: test\ntest:\n",
    "ifeq (0,1)\ntest:\n\t@echo TEST\nendif\n",
])
def test_run_suite_make_noop_target_is_unavailable(tmp_path, makefile):
    """空 test 目标 / 已存在的 test 文件让 make 以 0 退出但没有跑任何
    测试：不能当成「测试全部通过」采纳候选。第三例模拟 target 只在
    未生效条件分支里、工作区恰好有 test 文件时的假阳性。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    if "ifeq" in makefile:
        (tmp_path / "test").write_text("", encoding="utf-8")
    res = rounds.run_suite(["make", "test"], tmp_path, 60.0)
    assert (res.available, res.ok) == (False, False)
    assert "没有执行任何测试" in res.reason


@pytest.mark.parametrize("detail", [
    "make: Nothing to be done for 'test'.",
    "make: Nothing to be done for `test'.",
    'make: Nothing to be done for "test".',
    "make: 'test' is up to date.",
    "make: `test' is up to date.",
    'make: "test" is up to date.',
])
def test_make_noop_test_target_detected(detail):
    assert rounds._make_noop_test_target(detail) is True


@pytest.mark.parametrize("detail", [
    "make[1]: Nothing to be done for 'test'.",
    "make: Nothing to be done for 'test-unit'.",
    "make: 'test-unit' is up to date.",
    "make: *** [test] Error 1",
    "",
])
def test_make_noop_test_target_false_for_other_output(detail):
    assert rounds._make_noop_test_target(detail) is False


def test_run_suite_make_conditional_target_is_unavailable(tmp_path):
    """test 目标写在未生效的 ifeq 分支里：静态探测误以为有套件，而
    make test 以退出码 2 报「No rule to make target 'test'」。这与 make
    跑测试失败同码，不能据此拒绝候选——按套件不可用处理。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "ifeq (0,1)\ntest:\n\t@echo TEST\nendif\n", encoding="utf-8")
    res = rounds.run_suite(["make", "test"], tmp_path, 60.0)
    assert (res.available, res.ok) == (False, False)
    assert "没有 test 目标" in res.reason
    assert "No rule to make target" in res.detail


def test_run_suite_make_recipe_failure_is_still_a_failure(tmp_path):
    """make 真的运行了 test 失败时仍按测试失败处理，不能误判成不可用。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "test:\n\t@echo boom; false\n", encoding="utf-8")
    res = rounds.run_suite(["make", "test"], tmp_path, 60.0)
    assert (res.available, res.ok) == (True, False)
    assert "No rule" not in res.detail


@pytest.mark.parametrize("detail", [
    "make: *** No rule to make target 'test'.  Stop.",
    "make[1]: *** No rule to make target 'test'.  Stop.",
    "make: *** No rule to make target `test'.  Stop.",
    'make: *** No rule to make target "test".  Stop.',
])
def test_make_missing_test_target_detected(detail):
    assert rounds._make_missing_test_target(detail) is True


@pytest.mark.parametrize("detail", [
    "make: *** No rule to make target 'prereq', needed by 'test'.  Stop.",
    "make: *** No rule to make target 'test-unit'.  Stop.",
    "make: *** [test] Error 1",
    "",
])
def test_make_missing_test_target_false_for_other_errors(detail):
    assert rounds._make_missing_test_target(detail) is False


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


def test_atomic_write_removes_tmp_on_keyboard_interrupt(tmp_path, monkeypatch):
    """中断原子写不能在工作区留下半成品临时文件。"""
    path = tmp_path / "best.json"

    def interrupted(src, dst):
        raise KeyboardInterrupt

    monkeypatch.setattr(rounds.os, "replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        rounds._atomic_write(path, "new")
    assert not path.exists()
    assert not list(tmp_path.glob(path.name + ".*.tmp"))


def test_interrupt_during_best_md_write_rolls_back_json(ws, monkeypatch):
    """best.json 已写、best.md 写入时中断：元数据必须回滚。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    baseline_best = guard.best["id"]
    baseline_md = (guard.dir / rounds.BEST_MD_NAME).read_text(encoding="utf-8")
    write_idea(state_path, "中断写盘时的候选")

    real_write = rounds._atomic_write

    def boom(path, text):
        if Path(path).name == rounds.BEST_MD_NAME:
            raise KeyboardInterrupt
        return real_write(path, text)

    monkeypatch.setattr(rounds, "_atomic_write", boom)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)

    assert json.loads((guard.dir / rounds.BEST_JSON_NAME).read_text(
        encoding="utf-8"))["id"] == baseline_best
    assert (guard.dir / rounds.BEST_MD_NAME).read_text(
        encoding="utf-8") == baseline_md
    assert guard.best["id"] == baseline_best
    s = guard.stats
    assert (s.candidates, s.adopted, s.pending) == (1, 0, 1)


def test_interrupt_after_best_commit_reconciles_adopted(ws, monkeypatch):
    """两次写盘都完成、内存尚未更新时中断：按已采纳补记账，不能挂起。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "中断前已提交的最佳")

    real_commit = guard._commit_best

    def commit_then_interrupt(text, best):
        real_commit(text, best)
        raise KeyboardInterrupt

    monkeypatch.setattr(guard, "_commit_best", commit_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)

    cid = guard.best["id"]
    assert cid != [e for e in events(guard)
                   if e["event"] == "baseline"][-1]["id"]
    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending) == (1, 1, 0, 0)
    assert read_idea(state_path) == "中断前已提交的最佳"
    assert read_idea(guard.best_md) == "中断前已提交的最佳"
    assert json.loads((guard.dir / rounds.BEST_JSON_NAME).read_text(
        encoding="utf-8"))["id"] == cid
    verdicts = [e for e in events(guard)
                if e["event"] == "verdict" and e.get("id") == cid]
    assert len(verdicts) == 1
    assert verdicts[0]["result"] == "adopted"


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


def test_start_recovers_best_when_best_md_and_json_both_lost(ws):
    """best.md 与 best.json 同时丢失时，history.jsonl 里的最后采纳事件
    和对应候选快照仍足以找回最佳。

    回归：start() 只在 best.json 可读时才按 id 找快照；元数据也丢失后
    直接拿当前 research.md 重建基线，把旧最佳降级成未验证的当前内容。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    baseline_events = [e for e in events(guard) if e["event"] == "baseline"]
    write_idea(state_path, "第一轮晋升的最佳")
    assert guard.on_round_end(1) == "adopted"
    cid = guard.best["id"]
    (guard.dir / rounds.BEST_MD_NAME).unlink()
    (guard.dir / rounds.BEST_JSON_NAME).unlink()
    write_idea(state_path, "未验证的脏内容")

    sink = RecordingSink()
    restarted = make_guard(workspace, state_path, sink, verify="off")
    restarted.start()
    assert restarted.best["id"] == cid
    assert restarted.best["round"] == 1
    assert read_idea(restarted.best_md) == "第一轮晋升的最佳"
    assert json.loads(restarted.best_json.read_text(encoding="utf-8"))["id"] \
        == cid
    assert [e for e in events(restarted)
            if e["event"] == "baseline"] == baseline_events
    assert any("history.jsonl 与候选快照恢复" in m
               for lvl, m in sink.messages if lvl == "warn")


def test_start_restores_dirty_research_to_best(ws):
    """进程在轮次中途退出后重启：research.md 里未验证的半截内容不能
    留给下一轮 agent 当起点，必须先从 best.md 还原。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "已晋升的最佳")
    assert guard.on_round_end(1) == "adopted"
    best_id = guard.best["id"]
    # 模拟下一轮 agent 已写入但进程在 on_round_end 前被 kill
    write_idea(state_path, "未验证的半截内容")

    sink = RecordingSink()
    restarted = make_guard(workspace, state_path, sink, verify="off")
    restarted.start()
    assert read_idea(state_path) == "已晋升的最佳"
    assert restarted.best["id"] == best_id
    assert restarted.stats.restored == 1
    restored = [e for e in events(restarted) if e["event"] == "restored"]
    assert restored and restored[-1]["round"] == 0
    assert any("启动时还原" in m for lvl, m in sink.messages if lvl == "warn")


def test_start_recovers_older_best_when_current_snapshot_missing(ws):
    """当前最佳快照丢失、best.md 也丢失时，退回历史里仍有快照的较早最佳。

    回归：best.json 可读时只按它的 id 找快照，找不到就直接拿当前
    research.md 重建基线——旧最佳被降级，未验证的半截内容反而固化成基线。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    baseline_events = [e for e in events(guard) if e["event"] == "baseline"]
    write_idea(state_path, "第一轮晋升的最佳")
    assert guard.on_round_end(1) == "adopted"
    first_id = guard.best["id"]
    write_idea(state_path, "第二轮晋升的最佳")
    assert guard.on_round_end(2) == "adopted"
    second_id = guard.best["id"]

    (guard.dir / rounds.BEST_MD_NAME).unlink()
    (guard.dir / f"{rounds.CAND_PREFIX}{second_id}.md").unlink()
    write_idea(state_path, "未验证的脏内容")

    sink = RecordingSink()
    restarted = make_guard(workspace, state_path, sink, verify="off")
    restarted.start()
    assert restarted.best["id"] == first_id
    assert restarted.best["round"] == 1
    assert read_idea(restarted.best_md) == "第一轮晋升的最佳"
    assert json.loads(restarted.best_json.read_text(
        encoding="utf-8"))["id"] == first_id
    assert [e for e in events(restarted)
            if e["event"] == "baseline"] == baseline_events
    assert any("较早的最佳" in m
               for lvl, m in sink.messages if lvl == "warn")


def test_start_damaged_best_md_recovers_older_readable_snapshot(ws):
    """best.md 结构损坏且 best.json 丢失时，也要优先恢复快照可读的最佳。

    回归：该组合会走 _recover_best 取 history 最新采纳事件（不检查快照），
    best.md 又损坏不能充当内容源；若最新快照恰好丢了，内容就退回脚手架，
    而更早的最佳快照明明完整可读——旧最佳被静默丢弃。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    baseline_events = [e for e in events(guard) if e["event"] == "baseline"]
    write_idea(state_path, "第一轮晋升的最佳")
    assert guard.on_round_end(1) == "adopted"
    first_id = guard.best["id"]
    write_idea(state_path, "第二轮晋升的最佳")
    assert guard.on_round_end(2) == "adopted"
    second_id = guard.best["id"]

    (guard.dir / rounds.BEST_MD_NAME).write_text(
        "被外部截断的垃圾内容，没有区块标记", encoding="utf-8")
    (guard.dir / rounds.BEST_JSON_NAME).unlink()
    (guard.dir / f"{rounds.CAND_PREFIX}{second_id}.md").unlink()

    sink = RecordingSink()
    restarted = make_guard(workspace, state_path, sink, verify="off")
    restarted.start()
    assert restarted.best["id"] == first_id
    assert restarted.best["round"] == 1
    assert read_idea(restarted.best_md) == "第一轮晋升的最佳"
    assert json.loads(restarted.best_json.read_text(
        encoding="utf-8"))["id"] == first_id
    assert [e for e in events(restarted)
            if e["event"] == "baseline"] == baseline_events
    assert any("从候选快照恢复" in m
               for lvl, m in sink.messages if lvl == "warn")


def test_start_damaged_best_md_without_snapshot_rebuilds_scaffold(ws):
    """best.md 损坏、无快照且元数据丢失时，重建有效脚手架而不是留下坏文件。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    guard.best_md.write_text("被外部截断的垃圾内容，没有区块标记",
                             encoding="utf-8")
    guard.best_json.unlink()

    sink = RecordingSink()
    restarted = make_guard(workspace, state_path, sink, verify="off")
    restarted.start()
    assert read_idea(restarted.best_md) == "（暂无）"
    assert state._first_section(
        restarted.best_md.read_text(encoding="utf-8"),
        state.SECTION_ARTIFACT) is not None


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
    # 「score」粘在英文单词尾部只是后缀，不是评分标签；空格/下划线前缀照常
    assert parse_score("prescore: 3") is None
    assert parse_score("underscore: 3") is None
    assert parse_score("overall_score: 6") == 6.0
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


def test_read_state_file_heals_invalid_utf8_without_rewriting_line_endings(
        tmp_path):
    """修坏字节时不能顺手把整个文件的 CRLF/CR 混合行尾改成 LF。

    回归：read_state_file 的回写路径用 Path.read_text/write_text 的通用
    换行模式，一个非法字节就会让整份 research.md 的行尾被重写；与
    update_section_file 已有修复的「更新一个区块不得改写无关行尾」同一
    类数据损坏。返回值仍应与普通读取路径一样规整为 \\n。"""
    state_path = tmp_path / "research.md"
    start = state.start_marker(state.SECTION_IDEA)
    end = state.end_marker(state.SECTION_IDEA)
    prefix = ("head\r\n" + start + "\r\n" + "坏").encode("utf-8")
    suffix = ("\r\n" + end + "\r\n" + "mid\rtail\n").encode("utf-8")
    state_path.write_bytes(prefix + b"\xff" + suffix)

    text = state.read_state_file(state_path)

    assert "\r" not in text
    assert state.get_section(text, state.SECTION_IDEA) == "坏\ufffd"
    expected = prefix + "\ufffd".encode("utf-8") + suffix
    assert state_path.read_bytes() == expected


def test_ensure_state_file_does_not_overwrite_concurrent_update(
        tmp_path, monkeypatch):
    """启动补建 scaffold 不能覆盖另一个实例已写入的研究进度。

    回归：exists() 与 write_text() 之间没有状态锁，两个实例同时启动时后者
    的裸写会把前者已完成的 research.md 整份换回「（暂无）」。测试让预检在
    决定补建后暂停，期间并发 update_section_file；修复前更新会被 scaffold
    盖掉，修复后 update 等锁并在补建之后完成。
    """
    state_path = tmp_path / "research.md"
    scaffold_started = threading.Event()
    concurrent_update_done = threading.Event()
    original_scaffold = state.scaffold

    def slow_scaffold(task):
        if task == "新任务":
            scaffold_started.set()
            # 修复后并发 update 会被状态锁挡住，等到这里超时；修复前它会
            # 立即完成并 set 事件，于是随后的 scaffold 写入把更新覆盖掉。
            concurrent_update_done.wait(0.5)
        return original_scaffold(task)

    monkeypatch.setattr(state, "scaffold", slow_scaffold)
    errors = []

    def create():
        try:
            state.ensure_state_file(state_path, "新任务")
        except BaseException as exc:  # pragma: no cover - 失败时报告
            errors.append(exc)

    creator = threading.Thread(target=create)
    creator.start()
    assert scaffold_started.wait(2), "ensure_state_file 未进入补建路径"

    state.update_section_file(state_path, state.SECTION_IDEA, "并发更新")
    concurrent_update_done.set()
    creator.join(5)
    assert not creator.is_alive()
    assert not errors
    assert state.get_section(
        state.read_state_file(state_path), state.SECTION_IDEA) == "并发更新"


def test_ensure_state_file_interrupt_leaves_no_partial_file(tmp_path, monkeypatch):
    """补建 scaffold 被中断时不得留下半截目标文件。

    回归：ensure_state_file 直接 write_text 目标文件，写入途中中断后
    exists() 为真，后续启动不再补建；这里让 os.replace 抛
    KeyboardInterrupt，模拟写完临时文件、发布前的最后一次中断。
    """
    state_path = tmp_path / "research.md"

    def interrupted(src, dst):
        raise KeyboardInterrupt

    monkeypatch.setattr(state.os, "replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        state.ensure_state_file(state_path, "中断")
    assert not state_path.exists()
    assert not list(tmp_path.glob("research.md.*.tmp"))


def test_read_state_file_heal_interrupt_cleans_tmp(tmp_path, monkeypatch):
    """非法 UTF-8 回写被中断时不能把临时文件留在工作区。"""
    state_path = tmp_path / "research.md"
    state_path.write_bytes(b"bad \xff bytes")

    def interrupted(src, dst):
        raise KeyboardInterrupt

    monkeypatch.setattr(state.os, "replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        state.read_state_file(state_path)
    assert state_path.read_bytes() == b"bad \xff bytes"
    assert not list(tmp_path.glob("research.md.*.tmp"))


def test_update_section_interrupt_cleans_tmp(tmp_path, monkeypatch):
    """更新区块被中断时目标保持旧内容，且不留下临时半成品。"""
    state_path = tmp_path / "research.md"
    state.ensure_state_file(state_path, "测试任务")
    before = state_path.read_text(encoding="utf-8")

    def interrupted(src, dst):
        raise KeyboardInterrupt

    monkeypatch.setattr(state.os, "replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        state.update_section_file(state_path, state.SECTION_IDEA, "新想法")
    assert state_path.read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob("research.md.*.tmp"))


def test_write_helper_interrupt_cleans_tmp(tmp_path, monkeypatch):
    """写助手脚本被中断时不能留下语法未完成的模板文件。"""
    state_path = tmp_path / "research.md"
    helper = tmp_path / state.HELPER_NAME

    def interrupted(src, dst):
        raise KeyboardInterrupt

    monkeypatch.setattr(state.os, "replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        state.write_helper_script(tmp_path, state_path)
    assert not helper.exists()
    assert not list(tmp_path.glob("write_section.py.*.tmp"))


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


def test_update_section_preserves_other_section_past_fixed_pass_limit(tmp_path):
    """抢先配对的残片多于 64 个时也必须保住另一区块。

    回归：_preserve_other_section 固定只跑 64 轮，耗尽后静默返回仍被
    残片抢先的文本；80 个交叉 IDEA 标记让 ARTIFACT 从 WANT 变成 A65，
    模块与写入助手都会把另一区块的大部分历史当游离标记删掉。
    """
    import subprocess

    idea_s = state.start_marker(state.SECTION_IDEA)
    idea_e = state.end_marker(state.SECTION_IDEA)
    art_s = state.start_marker(state.SECTION_ARTIFACT)
    art_e = state.end_marker(state.SECTION_ARTIFACT)
    parts = []
    for n in range(1, 80):
        parts += [art_s, f"A{n}", idea_s, art_e, "cross", idea_e]
    parts += [art_s, "WANT", art_e, idea_s, "OWN", idea_e]
    original = "\n".join(parts) + "\n"
    state_path = tmp_path / "research.md"

    state_path.write_text(original, encoding="utf-8")
    state.update_section_file(state_path, state.SECTION_IDEA, "NEW")
    text = state_path.read_text(encoding="utf-8")
    assert state.get_section(text, state.SECTION_ARTIFACT) == "WANT"
    assert state.get_section(text, state.SECTION_IDEA) == "NEW"

    state_path.write_text(original, encoding="utf-8")
    helper = state.write_helper_script(tmp_path, state_path)
    r = subprocess.run([sys.executable, str(helper), "idea"],
                       input=b"NEW", capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    text = state_path.read_text(encoding="utf-8")
    assert state.get_section(text, state.SECTION_ARTIFACT) == "WANT"
    assert state.get_section(text, state.SECTION_IDEA) == "NEW"


def test_update_section_preserves_unrelated_line_endings(tmp_path):
    """更新一个区块不得把自由文本及其他区块的行尾统统改成 LF。

    回归：读写都用 Path.read_text/write_text 的通用换行模式，更新任意
    区块都会把整个文件的 CRLF/CR 行尾重写成 LF；混合行尾仓库里即使只
    改 IDEA，suffix 及其他区块的字节也会被悄悄改写。
    """
    import subprocess
    import sys

    def raw(path):
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()

    state_path = tmp_path / "research.md"
    s = state.start_marker(state.SECTION_IDEA)
    e = state.end_marker(state.SECTION_IDEA)
    original = (f"prefix\nline1\r\nline2\n{s}\nold\n{e}\n"
                "suffix\r\nend\n")
    state_path.write_bytes(original.encode("utf-8"))
    state.update_section_file(state_path, state.SECTION_IDEA, "new")
    assert raw(state_path) == (
        f"prefix\nline1\r\nline2\n{s}\nnew\n{e}\nsuffix\r\nend\n")

    helper = state.write_helper_script(tmp_path, state_path)
    r = subprocess.run([sys.executable, str(helper), "idea"],
                       input=b"helper", capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert raw(state_path) == (
        f"prefix\nline1\r\nline2\n{s}\nhelper\n{e}\nsuffix\r\nend\n")

    crlf_path = tmp_path / "crlf.md"
    crlf_path.write_bytes(
        f"head\r\n{s}\r\nold\r\n{e}\r\ntail\r\n".encode("utf-8"))
    state.update_section_file(crlf_path, state.SECTION_IDEA, "a\nb")
    assert raw(crlf_path) == f"head\r\n{s}\r\na\r\nb\r\n{e}\r\ntail\r\n"


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


def test_helper_interrupt_cleans_tmp(tmp_path):
    """写入助手被 Ctrl+C 打断时不能留下半成品临时文件。

    回归：生成的 write_section.py 只捕 OSError，且临时文件名固定为
    research.md.tmp。KeyboardInterrupt 落在 os.replace 上时半成品残留，
    agent 每次被中断都往工作区堆一个垃圾文件；固定名还会让并发实例
    互踩。与 xuen.state / rounds 的原子写同一口径：临时名带 PID，
    任何中断都先清临时文件再传播。
    """
    import subprocess

    state_path = tmp_path / "research.md"
    state.ensure_state_file(state_path, "测试任务")
    helper = state.write_helper_script(tmp_path, state_path)
    driver = tmp_path / "_ki_driver.py"
    driver.write_text(
        "import os, runpy, sys\n"
        "helper = sys.argv[1]\n"
        "sys.argv = [helper, 'idea']\n"
        "def boom(src, dst):\n"
        "    raise KeyboardInterrupt\n"
        "os.replace = boom\n"
        "runpy.run_path(helper, run_name='__main__')\n",
        encoding="utf-8")
    subprocess.run([sys.executable, str(driver), str(helper)],
                   input="中断想法".encode("utf-8"), capture_output=True)

    text = state_path.read_text(encoding="utf-8")
    assert state.get_section(text, state.SECTION_IDEA) == "（暂无）"
    assert not (tmp_path / "research.md.tmp").exists()
    assert not list(tmp_path.glob("research.md.*.tmp"))


def test_interrupt_after_snapshot_before_verdict_settles_candidate(ws, monkeypatch):
    """快照后、判定入账前的中断不能留下「候选 1、结论全 0」的统计。

    回归：候选快照成功、候选事件已落盘后，sink.info 输出（或其他未覆盖
    点）收到 KeyboardInterrupt 时，candidates 已 +1 却没有任何结论桶；
    轮次已在 _handled_rounds，runner 的 on_round_failed 只补做还原，补
    不了统计——汇总永久违反 adopted+rejected+pending==candidates。
    中断语义不变：不写 verdict 事件（不能把中断伪装成已决），候选按
    「待评分」计入并还原最佳，用户补分仍可翻案。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "中断也要保住的新想法")

    real_info = guard.sink.info

    def boom(text):
        if "候选快照" in text:
            raise KeyboardInterrupt
        return real_info(text)

    monkeypatch.setattr(guard.sink, "info", boom)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)

    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending) == (1, 0, 0, 1)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert guard.best["round"] == 0
    assert read_idea(state_path) == "（暂无）"
    verdicts = [e for e in events(guard) if e["event"] == "verdict"]
    assert verdicts == []

    # runner 的失败处理（轮次已处理，只补还原）不能让统计再次失衡
    guard.on_round_failed(1, "被中断，轮次未完成")
    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending, s.skipped) \
        == (1, 0, 0, 1, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    guard.finish()


def test_candidate_event_failure_retracts_before_settle(ws, monkeypatch):
    """候选快照成功、候选事件写盘失败：按跳过撤销后兜底不能补成待评分。

    回归：兜底记账只看 _inflight_cid 仍指向刚被撤销的候选，会把它补记
    成「待评分」——candidates 已 -1，pending 却 +1，汇总反而多出一个
    并不存在的待评分候选。任何撤销候选（candidates -= 1）的路径都必须
    同步清空 in-flight 标记。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "候选事件写盘失败的想法")
    real_append = guard._append_event

    def boom(ev):
        if ev.get("event") == "candidate":
            raise OSError("磁盘满（模拟）")
        return real_append(ev)

    monkeypatch.setattr(guard, "_append_event", boom)
    with pytest.raises(OSError):
        guard.on_round_end(1)

    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending, s.skipped) \
        == (0, 0, 0, 0, 1)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert guard.best["round"] == 0


def test_sink_failure_after_adoption_does_not_pend_committed_candidate(ws):
    """晋升提交成功后 sink.ok 抛错，不能把已采纳候选再挂起。

    回归：_adopt 已完成 best.md/best.json 写盘、self.best 赋值与 adopted
    计数，最后才 sink.ok。TUI 已退出等情况下该通知可能抛错，调用方的
    except 会把同一个候选再计入 pending，adopted+pending 超过
    candidates；应按已提交的 best 对账并保持 adopted。"""
    workspace, state_path = ws

    class FailingSink(RecordingSink):
        def __init__(self):
            super().__init__()
            self.fail_ok = False

        def ok(self, text):
            if self.fail_ok:
                raise RuntimeError("界面已退出（模拟）")
            super().ok(text)

    sink = FailingSink()
    guard = make_guard(workspace, state_path, sink=sink, verify="off")
    guard.start()
    write_idea(state_path, "已写盘但通知失败的新想法")
    sink.fail_ok = True

    assert guard.on_round_end(1) == "adopted"

    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending) == (1, 1, 0, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert guard.best["id"] in guard._adopted_ids
    assert read_idea(state_path) == "已写盘但通知失败的新想法"
    verdicts = [e for e in events(guard) if e["event"] == "verdict"]
    assert len(verdicts) == 1 and verdicts[0]["result"] == "adopted"
    assert any("收尾失败" in m for _, m in sink.messages)


def test_interrupt_after_best_assignment_before_count(ws, monkeypatch):
    """晋升中断落在 best 赋值之后、统计入账之前：不能漏记 adopted。

    回归：_adopt 先提交 best.md/best.json、再 self.best = best、最后才
    stats.adopted += 1。若 Ctrl+C 正好落在后两步之间，中断兜底看到
    best 已指向候选就直接跳过，候选既不在 adopted 也不在 pending，
    汇总永久违反 adopted+rejected+pending==candidates。
    """
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "中断前已提交的新想法")

    def interrupted_adopt(cid, round_no, verdict):
        text = guard._read_candidate_text(cid)
        best = {"id": cid, "round": round_no, "verifier": verdict.verifier,
                "score": verdict.score, "ts": rounds._ts(),
                "reason": verdict.reason}
        guard._commit_best(text, best)
        guard.best = best
        raise KeyboardInterrupt

    monkeypatch.setattr(guard, "_adopt", interrupted_adopt)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)

    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending) == (1, 1, 0, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert guard._load_best()["id"] == guard.best["id"]
    verdicts = [e for e in events(guard) if e["event"] == "verdict"]
    assert len(verdicts) == 1 and verdicts[0]["result"] == "adopted"

    guard.on_round_failed(1, "被中断，轮次未完成")
    assert guard.stats.skipped == 0
    guard.finish()
    assert guard.stats.adopted == 1


def test_interrupt_inside_adopted_count_does_not_double_count(ws, monkeypatch):
    """设置 adopted 集合后、同步统计/已决标记前中断：对账不能重复 +1。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "计数中途被打断的想法")

    real_count = guard._count_adopted
    armed = True

    def half_count(cid):
        nonlocal armed
        if armed:
            armed = False
            guard._adopted_ids.add(cid)
            guard.stats.adopted = len(guard._adopted_ids)
            raise KeyboardInterrupt
        return real_count(cid)

    monkeypatch.setattr(guard, "_count_adopted", half_count)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)

    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending) == (1, 1, 0, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert guard.best["id"] in guard._adopted_ids
    assert guard.best["id"] in guard._settled_cids
    guard.on_round_failed(1, "被中断，轮次未完成")
    guard.finish()
    assert guard.stats.adopted == 1


def test_interrupt_after_rejected_count_before_settled(ws, monkeypatch):
    """拒绝记账中断：rejected 已加但已决标记未落时不能补成 pending。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="off")
    guard.start()
    write_idea(state_path, "会被拒绝的想法")

    monkeypatch.setattr(
        guard, "_verify",
        lambda round_no, cid: rounds.Verdict(
            verifier="tests", result="rejected", reason="模拟拒绝"))
    real_count = guard._count_rejected
    armed = True

    def half_count(cid):
        nonlocal armed
        if armed:
            armed = False
            guard._rejected_ids.add(cid)
            guard.stats.rejected += 1
            raise KeyboardInterrupt
        return real_count(cid)

    monkeypatch.setattr(guard, "_count_rejected", half_count)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)

    s = guard.stats
    assert (s.candidates, s.adopted, s.rejected, s.pending) == (1, 0, 1, 0)
    assert s.adopted + s.rejected + s.pending == s.candidates
    assert guard._inflight_cid is None
    assert all(cid in guard._settled_cids for cid in guard._rejected_ids)
    guard.on_round_failed(1, "被中断，轮次未完成")
    guard.finish()
    assert guard.stats.rejected == 1
    assert guard.stats.pending == 0


@pytest.mark.parametrize("text", [
    "override A = test\nA = foo\n$(A):",
    "override A ?= test\nA = foo\n$(A):",
    "override A += test\nA = foo\n$(A):",
    "override A := test\nA = foo\n$(A):",
    "A = foo\noverride A = test\n$(A):",
    "override A = test\nundefine A\n$(A):",
    "override define A\ntest\nendef\nA = foo\n$(A):",
])
def test_detect_test_suite_make_override_variable_keeps_suite(
        tmp_path, text):
    """override 变量不能被后续普通赋值/undefine 覆盖。

    回归：探测按出现顺序直接覆盖变量表，`override A = test` 后的
    `A = foo` 会把 test 目标展开成 foo，漏掉 make 实际能运行的套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        text + "\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_override_undefine_removes_suite(tmp_path):
    """override undefine 才是真正删除 override 变量的写法。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "override A = test\noverride undefine A\n$(A):\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_override_in_include_keeps_suite(tmp_path):
    """include 文件里的 override 变量在主文件中仍然不可被普通赋值覆盖。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "inc.mk").write_text("override A = test\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "include inc.mk\nA = foo\n$(A):\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("text, expected", [
    # ?= 不覆盖已定义变量：test 只存在于 define 体里，没有真实目标。
    ("A = foo\ndefine A ?=\ntest\nendef\n$(A):", None),
    ("A = foo\noverride define A ?=\ntest\nendef\n$(A):", None),
    # += 追加值；A 展开成 `foo test`，规则里确实有 test 目标。
    ("A = foo\ndefine A +=\ntest\nendef\n$(A):", ["make", "test"]),
    # := 立即覆盖旧值，test 目标消失。
    ("A = test\ndefine A :=\nfoo\nendef\n$(A):", None),
    # 普通 define 不能覆盖 override 变量。
    ("override A = test\ndefine A\nfoo\nendef\n$(A):", ["make", "test"]),
    # override define 可以覆盖普通变量。
    ("A = foo\noverride define A\ntest\nendef\n$(A):", ["make", "test"]),
])
def test_detect_test_suite_make_define_assignment_operators(
        tmp_path, text, expected):
    """define 名称后的 ?=/+=/:= 必须按 make 语义生效。

    回归：原先把运算符从名称里截掉后一律用 define 体替换变量，
    `define A ?=` 会覆盖已有值，把不存在的 test 目标误判成可运行套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        text + "\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert (p.returncode == 0) is (expected is not None)
    assert detect_test_suite(tmp_path) == expected


@pytest.mark.parametrize("line", [
    "export test::",
    "export test:: dep",
    "export test: a:b",
    "export test:$(X)=1",
    "export foo:$(X)+=1",
    "unexport test:$(X)=1",
    "unexport foo:",
    "export foo:\nfoo::",
    r"export foo\;bar:",
    "export foo&::",
])
def test_detect_test_suite_make_export_directive_is_not_rule(tmp_path, line):
    """行首 export/unexport 是导出指令，不是规则头。

    回归：`export test::` 被混合冒号风格检查当成 test 的 :: 规则，
    与后面合法的 test: 规则制造假冲突，可运行的套件被误判成没有测试。
    导出指令后的 `test::` / `a:b` 等都只是变量名列表的一部分。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "test:$(X)=1",
    "test:$X=1",
    "test:$(X) =1",
    "test:$(X)+=1",
    "test: $X+=1",
    "test:$(X)!=1",
    "test:$(X)?=1",
    "test:$(X):=1",
    "&$x:$(X)=1",
    "&$(U):$(X)=1",
    "$(X)& :$(X)=1",
])
def test_detect_test_suite_make_empty_target_assignment_name_blocks_suite(
        tmp_path, line):
    """target-specific 赋值变量名展开为空时 make 报 empty variable name。

    回归：`test:$(X)=1`（X 未定义）整行展开后变成 `test:=1`，下游把它
    当成合法的变量赋值 test := 1 而放过，误以为存在可运行的 test 目标；
    make 实际在读取阶段直接失败。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "test:$(if ,x)=1",
    "test:$(if x)=1",
    "test:$(if x,,)=1",
    "test:$(if $(Y),x,)=1",
    "test:$(and ,x)=1",
    "test:$(strip )=1",
    "test:$(subst a,,a)=1",
    "test:$(filter-out a,a)=1",
    "test:$(wildcard /nonexistent)=1",
])
def test_detect_test_suite_make_function_empty_assignment_name_blocks_suite(
        tmp_path, line):
    """target-specific 赋值名里的静态/条件函数也可能展开为空。

    回归：`test:$(strip )=1` / `test:$(if ,x)=1` 的变量名原文非空，
    但 make 展开后报 empty variable name；只检查变量引用的探测会把
    随后的合法 test 目标误判成可运行套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "test:$(if x,y,)=1",
    "test:$(or ,x)=1",
    "test:$(and x,y)=1",
    "test:$(subst ,,x)=1",
    "$(if ,x):$(Y)=1",
    "$(strip ):$(Y)=1",
    "$(subst a,,a):$(Y)=1",
    "$(if x,,):$(Y)=1",
])
def test_detect_test_suite_make_function_assignment_names_keep_suite(
        tmp_path, line):
    """函数展开后变量名非空、或目标列表展开为空时仍是合法写法。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "test:$(X)X=1",
    "test:X$(X)=1",
    "test:$(X) X=1",
])
def test_detect_test_suite_make_nonempty_or_split_target_assignment_keeps_suite(
        tmp_path, line):
    """展开后的变量名非空、或空引用后面只是普通前置依赖时不变。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    assert detect_test_suite(tmp_path, ) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "foo",
    "foo bar",
    "echo hi",
    "test\\:",
    "test\\: dep",
    "test\\:$(X)=1",
    "foo\\: dep",
    "a\\:b",
    "private export foo",
])
def test_detect_test_suite_make_missing_separator_line_blocks_suite(
        tmp_path, line):
    """展开后没有规则分隔符的非指令行让 make 在读取阶段直接失败。

    回归：原先只扫描带冒号的行，`foo` / `test\\: dep` 这类 missing
    separator 被漏掉，别处存在的合法 test 目标会让探测误以为套件可运行，
    随后 `make test` 失败并误伤候选。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$: ;",
    "$x ;",
    "$(X) ;",
    "$(info hi)",
    "export foo",
    "vpath %.c src",
    "test $#:",
    "test $;::",
    "test $$:",
])
def test_detect_test_suite_make_no_separator_but_valid_lines_keep_suite(
        tmp_path, line):
    """变量引用展开为空、读取期函数和导出/vpath 指令不是 missing separator。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    if line.startswith("test "):
        text = line + "\n\techo ok\n"
    else:
        text = line + "\ntest:\n\t@echo ok\n"
    (tmp_path / "Makefile").write_text(text, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "&:$(X)=1",
    "&::$(X)=1",
    "$(X):$(Y)=1",
    "$(X) $(Y):$(Z)=1",
    "$x:$(X)=1",
    "$x&:$(X)=1",
    "$(X)&:$(X)=1",
    "foo$:$(X)=1",
    "$:X:=1",
    "x$:X:=1",
    "foo$:bar:=1",
    "$x$:X:=1",
    "$::$(X)=1",
    "$x$::$(X)=1",
    "$x $::$(X)=1",
    "foo $:: x=1",
])
def test_detect_test_suite_make_empty_target_list_assignment_keeps_suite(
        tmp_path, line):
    """目标列表本身展开为空时 make 接受 target-specific 赋值。

    回归：为空 target-specific 变量名加的读取期检查只看赋值名，没先看
    目标列表；`$(X):$(Y)=1` / `&:$(X)=1` 被误判成 empty variable name，
    可运行的 test 套件被漏检。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("makefile", [
    "T =\n$(T): A=$(word x,a b)\ntest:\n\t@echo ok\n",
    "$(X): A:=$(word x,a b)\ntest:\n\t@echo ok\n",
    "test: A=$(word x,a b)\ntest:\n\t@echo ok\n",
    "test: A=$(call f,\ntest:\n\t@echo ok\n",
    "test: A=$(error boom)\ntest:\n\t@echo ok\n",
    "test: A=$(eval x)\ntest:\n\t@echo ok\n",
    "$(X): A:=$(eval x)\ntest:\n\t@echo ok\n",
    "X = test\nX += $(eval x)\ntest:\n\t@echo ok\n",
    "X = test\nX ?= $(eval x)\ntest:\n\t@echo ok\n",
])
def test_detect_test_suite_make_deferred_target_assignment_value_keeps_suite(
        tmp_path, makefile):
    """target-specific 赋值右侧不一定在读取期展开，不能提前报错。

    回归：`=`/`?=`/`+=` 的值延迟到变量被使用时才展开；目标列表展开为空
    时 make 连 `:=`/`!=` 的右侧也忽略。整行预展开会误报右侧静态函数的
    fatal 错误，漏掉后面的合法 test 目标。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("op", [":=", "::=", "!=", ":::="])
def test_detect_test_suite_make_immediate_target_assignment_value_blocks_suite(
        tmp_path, op):
    """非空目标列表的立即赋值右侧仍在读取期展开，静态函数错误是 fatal。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        f"test: A{op}$(word x,a b)\ntest:\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$(X)",
    "$(X) $(Y)",
    "foo$(X) bar",
    "${a}${X}b",
    "$(strip )$(X)",
])
def test_detect_test_suite_make_expanded_missing_separator_blocks_suite(
        tmp_path, line):
    """原始行以 `$` 开头、展开后仍有非空文本且无规则分隔符时 make 读取失败。

    回归：missing separator 只在变量展开前扫描，而展开前以 `$` 开头的行
    被交给后续展开逻辑；`X = test` + `$(X)` 展开成裸 `test` 后漏检，
    后面合法 test 目标会让探测误以为套件可运行。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "X = test\nY = foo\n" + line + "\ntest:\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$(info x)=1",
    "$(warning x)=1",
    "$(foreach v,,x)=1",
    "$(value X)=1",
    "$(call undefined,)=1",
    "$(call undefined,x)=1",
    "$(addprefix ,)=1",
    "$(eval X=1)=1",
    "$(eval )=1",
    "$(eval $(info x))=1",
])
def test_detect_test_suite_make_empty_expanded_assignment_name_blocks_suite(
        tmp_path, line):
    """赋值名里的 value/foreach/call/info 展开为空时 make 报空变量名。

    回归：赋值名展开只处理普通引用与条件/静态函数，`$(info x)=1` /
    `$(foreach v,,x)=1` 被当成合法赋值整行吞掉，后面存在的 test 目标让
    探测误以为套件可运行，实际 `make test` 在读取阶段就失败。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "test:$(foreach v,,x)=1",
    "test:$(foreach v,a,)=1",
    "test:$(call undefined)=1",
    "test:$(value X)=1",
    "test:$(info x)=1",
    "test:$(warning x)=1",
])
def test_detect_test_suite_make_empty_target_assignment_function_name(
        tmp_path, line):
    """target-specific 赋值名里的 value/foreach/call/info 同样会展开为空。

    回归：普通赋值名已覆盖这些函数，target-specific 赋值名却仍只展开
    普通引用与条件函数，`test:$(foreach v,,x)=1` 被当成合法赋值吞掉，
    后面存在的 test 目标让探测误以为套件可运行，实际 make 读取失败。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$(shell ) = x",
    "$(shell true) = x",
    "test: $(shell ) = x",
    "define $(shell )\nbody\nendef",
    "undefine $(shell )",
])
def test_detect_test_suite_make_unknown_shell_name_may_be_empty(
        tmp_path, line):
    """名字里只剩无法静态求值的 shell 引用时，输出可能为空。

    `$(shell )` 展开为空会让 make 报 empty variable name；静态探测无法
    知道任意 shell 命令的输出，不能把原文当成非空名字继续探测套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$(foreach v,test,$(v)) = 1",
    "$(foreach v,test,$(v)) := 1",
])
def test_detect_test_suite_make_foreach_assignment_name_binds_variable(
        tmp_path, line):
    """foreach 的循环变量必须先绑定再展开循环体。

    回归：赋值名展开先做普通引用展开，`$(foreach v,test,$(v))` 里的
    `$(v)` 被当成未定义变量清空，整个名字变成空串并误报 empty variable
    name；make 实际定义名为 test 的变量，后面的 test 目标可正常运行。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "$(strip,\\)=1",
    "$(strip,\\):=1",
])
def test_detect_test_suite_make_backslash_before_ref_close_empty_name(
        tmp_path, line):
    r"""变量名里的 `\,` / `\)` 不构成函数调用或转义。

    `$(strip,\)` 没有函数名后的空白，是名字为 `strip,\)` 的变量引用；
    未定义时展开为空，make 报 empty variable name。回归：引用扫描器把
    `\)` 当转义整体跳过，引用被误判为未闭合，后面的 test 目标被误报
    成可运行套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$(origin X)=1",
    "$(flavor X)=1",
    "$(if ,foo,bar)=1",
    "$(info x)foo=1",
])
def test_detect_test_suite_make_nonempty_expanded_assignment_name_keeps_suite(
        tmp_path, line):
    """赋值名展开后非空（origin/flavor 返回文本）时仍是合法赋值。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "test: $(findstring $(subst $$,1),x)",
    "$(info $(findstring $(subst $$,1),x))",
    "X := $(findstring $(subst $$,1),x)",
])
def test_detect_test_suite_make_literal_dollar_does_not_hide_arity_error(
        tmp_path, line):
    """`$$` 展开后是字面 `$`，不能把含它的静态函数当成无法求值跳过。

    回归：参数值里的 `$$` 被误判成未展开引用，`$(subst $$,1)` 的参数
    不足错误因此被吞掉；make 在读取阶段失败，探测却返回可运行套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


def test_detect_test_suite_make_literal_dollar_condition_keeps_suite(
        tmp_path):
    """字面 `$` 在条件里是非空值，`$(if $$,test,x)` 仍定义 test。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "$(if $$,test,x):\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


def test_detect_test_suite_make_literal_dollar_origin_eval_blocks_suite(
        tmp_path):
    """eval 里的 `$(origin $$)` 展开为 undefined，作为 Makefile 行无分隔符。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "$(eval $(origin $(if b,$$, )))\ntest:\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    # 递归变量值里的 foreach 列表由静态函数决定；不展开静态函数会把
    # `$(suffix \)` 拆成多个词，空列表被误算成非空，选中 test 分支。
    "Y = $(if $(foreach test,$(suffix \\,),$(abspath \\,)),test,x)\n"
    "$(Y):\n\t@true\n",
    "Y = $(foreach v,$(suffix \\,),$(abspath \\,))\n$(Y):\n\t@true\n",
])
def test_detect_test_suite_make_recursive_foreach_static_functions(
        tmp_path, makefile):
    """变量值里的 foreach 要能调用静态函数并得到正确的空/非空列表。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "Y = $(foreach v,$(basename test.c),$(v))\n$(Y):\n\t@true\n",
    "Y = $(foreach v,test,$(if $(v),$(v),x))\n$(Y):\n\t@true\n",
    "Y = $(if x,test,$(foreach v,${a,b},x))\n$(Y):\n\t@true\n",
    "Y = $(if ,$(foreach v,${a,b},x),test)\n$(Y):\n\t@true\n",
])
def test_detect_test_suite_make_recursive_foreach_keeps_suite(
        tmp_path, makefile):
    """变量值里 foreach 的静态函数与未生效分支不能误伤 test 目标。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "$(join test,:)",
    "$(subst x,a:,x)",
    "$(subst x,a::,x)",
])
def test_detect_test_suite_make_expanded_target_trailing_colon_blocks_suite(
        tmp_path, line):
    """目标表达式展开后以裸冒号结尾时 make 报 missing target pattern。

    回归：`$(join test,:):` 展开成 `test::`，在展开后的文本上与合法
    双冒号规则无法区分，导致后面存在的 test 目标被误判成套件可运行。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + ":\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("line", [
    "$(subst x,:,x)",
    "$(subst x,:a,x)",
])
def test_detect_test_suite_make_expanded_empty_target_colon_keeps_suite(
        tmp_path, line):
    """展开后目标列表只有/以冒号开头时 make 接受空目标，不能误伤套件。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + ":\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "undefine $(strip )",
    "undefine $(info x)",
    "undefine $(foreach v,,$(v))",
    "undefine $(call undefined)",
    "undefine $(value X)",
    "undefine $(X)",
    "undefine $(subst a, ,a)",
    "undefine $(foreach v,a, )",
])
def test_detect_test_suite_make_function_expanded_empty_undefine_name(
        tmp_path, line):
    """undefine 名称里的函数展开为空时 make 报 empty variable name。

    回归：undefine 只按固定变量名正则处理，函数形式既不展开也不判空，
    后面存在的 test 目标让探测误以为套件可运行，实际 make 读取失败。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "X = a\nundefine $(strip X)\ntest:\n\t@echo ok\n",
    "X = a\nundefine $(foreach v,X,$(v))\ntest:\n\t@echo ok\n",
    "undefine X Y\ntest:\n\t@echo ok\n",
    "undefine = x\ntest:\n\t@echo ok\n",
])
def test_detect_test_suite_make_undefine_function_name_keeps_suite(
        tmp_path, makefile):
    """undefine 名称展开后非空（含空格/等号）仍是合法指令。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("name", [
    "$(if x,A=B,C)",
    "$(if x,A:=B,C)",
    "$(subst =,x,A)",
    "$(filter a=b,a=b c)",
    "$(findstring =,a=b)",
    "$(word 1,a=b)",
    "$(foreach v,a=b,$(v))",
    "$(strip X=Y)",
    "$(strip X := Y)",
])
def test_detect_test_suite_make_define_operator_inside_reference(
        tmp_path, name):
    """define 名称里的赋值符在函数参数内时不是运算符。

    回归：按第一个 `=` / `:=` 粗暴截断会得到未闭合引用，把
    `define $(if x,A=B,C)` / `define $(subst =,x,A)` 这类 make 完全
    接受的写法误判成读取失败，后面的 test 套件因此漏检。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        f"X = test\nY = A\ndefine {name}\nbody\nendef\n"
        "test:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("name", [
    "$(findstring =,a=b)",
    "$(strip =)",
    "$(subst a,=,a)",
])
def test_detect_test_suite_make_define_expands_to_operator_name(
        tmp_path, name):
    """define 名称展开后以 `=` 开头时仍是合法变量名，不是空名。"""
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        f"define {name}\nbody\nendef\ntest:\n\t@echo ok\n",
        encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert detect_test_suite(tmp_path) == ["make", "test"]


@pytest.mark.parametrize("line", [
    "$(X)",
    "$(sort =)",
    "$(subst a,=,a)",
])
def test_detect_test_suite_make_expanded_assignment_like_line_blocks_suite(
        tmp_path, line):
    """非赋值行展开成赋值形态仍是 missing separator。

    回归：展开后的缺分隔符扫描跳过了所有匹配赋值正则的行，
    `X = =` 后的 `$(X)` / `$(sort =)` 展开成 `=` 被当成合法赋值，
    后面存在的 test 目标让探测误以为套件可运行，实际 make 读取失败。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(
        "X = =\n" + line + "\ntest:\n\t@echo ok\n", encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None


@pytest.mark.parametrize("makefile", [
    "include $(info $(word x,a b))\ntest:\n\t@echo ok\n",
    "include $(warning $(addprefix a))\ntest:\n\t@echo ok\n",
    "ifeq ($(info $(subst a,b)),)\ntest:\n\t@echo ok\nendif\n",
    "ifeq ($(warning $(wordlist x,1,a b)),)\ntest:\n\t@echo ok\nendif\n",
    "$(foreach v,a,$(info $(word x,a b))):\ntest:\n\t@echo ok\n",
])
def test_detect_test_suite_make_info_warning_argument_error_blocks_suite(
        tmp_path, makefile):
    """info/warning 的参数会先展开，里面的静态函数错误仍是 fatal。

    回归：info/warning 被整块删除时没有检查参数，`$(info $(word x,...))`
    的非法下标丢失，探测把读取期必然失败的 Makefile 当成可运行套件。
    """
    if not shutil.which("make"):
        pytest.skip("make 不可用")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    p = subprocess.run(["make", "-n", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert detect_test_suite(tmp_path) is None
