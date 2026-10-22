"""轮次守卫单元测试：快照、候选/最佳分离、验证级联、用户/AI 评分、还原语义。

对应 xuen/rounds.py 的全面重写版：守卫状态机（快照→候选→验证→晋升/
还原）、渐进翻案（verdicts.txt 补分）、best 恢复链（best.json →
history.jsonl → 候选快照 → best.md 镜像）、套件探测与运行语义
（pytest / make / npm / go，Makefile 语义判定委托给 make 运行时）。
"""
import json
import os
import shutil
import sys
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
    run_suite,
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

    def texts(self, level):
        return [t for lv, t in self.messages if lv == level]


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
    return RoundGuard(cfg, "测试任务", state_path, workspace,
                      sink or RecordingSink(),
                      judge=judge, suite_runner=suite_runner)


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


def judge_ok(score):
    """评审员桩：正常返回指定分数。"""
    return lambda prompt: (True, f"候选更聚焦。\n评分: {score}")


# ------------------------------------------------------------- 基线与恢复
def test_start_creates_baseline(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    assert guard.best["round"] == 0
    assert guard.best["verifier"] == "baseline"
    assert guard.best_json.exists() and guard.best_md.exists()
    # best.md 是「基线已建立」的存在标志，内容与当前状态一致
    assert (guard.best_md.read_text(encoding="utf-8")
            == state_path.read_text(encoding="utf-8"))
    assert [e["event"] for e in events(guard)] == ["baseline"]
    assert any("轮次守卫已启用" in t for t in guard.sink.texts("info"))


def test_start_reuses_existing_best(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    first_id = guard.best["id"]
    guard2 = make_guard(workspace, state_path)
    guard2.start()
    assert guard2.best["id"] == first_id
    # 复用已有最佳：不重复建立基线
    assert len([e for e in events(guard2) if e["event"] == "baseline"]) == 1


def test_start_heals_mirror_from_snapshot(ws):
    """best.md 镜像丢失时从候选快照自愈（内容权威在快照）。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, judge=judge_ok(9), verify="ai")
    guard.start()
    write_idea(state_path, "更好的想法")
    assert guard.on_round_end(1) == "adopted"
    adopted_id = guard.best["id"]
    guard.best_md.unlink()

    guard2 = make_guard(workspace, state_path)
    guard2.start()
    assert guard2.best["id"] == adopted_id
    assert state.get_section(
        guard2.best_md.read_text(encoding="utf-8"), state.SECTION_IDEA
    ) == "更好的想法"


def test_start_recovers_metadata_from_history(ws):
    """best.json 损坏/丢失时从 history.jsonl 恢复最佳元数据。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, judge=judge_ok(9), verify="ai")
    guard.start()
    write_idea(state_path, "更好的想法")
    guard.on_round_end(1)
    adopted_id = guard.best["id"]
    guard.best_json.unlink()

    guard2 = make_guard(workspace, state_path)
    guard2.start()
    assert guard2.best["id"] == adopted_id
    assert guard2.best["round"] == 1
    assert read_idea(state_path) == "更好的想法"


def test_start_rebaseline_uses_mirror_when_metadata_lost(ws):
    """best.json 与 history 全丢但镜像还在：以镜像内容重建基线，
    不把可能未验证的当前状态悄悄固化成基线。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, judge=judge_ok(9), verify="ai")
    guard.start()
    write_idea(state_path, "已验证的想法")
    guard.on_round_end(1)
    guard.best_json.unlink()
    guard.history_path.unlink()
    # 模拟轮次中途被 kill：research.md 留下未验证内容
    write_idea(state_path, "未验证的半截想法")

    guard2 = make_guard(workspace, state_path)
    guard2.start()
    assert guard2.best["verifier"] == "baseline"
    # 基线内容来自镜像（已验证），而不是半截的当前状态
    assert read_idea(state_path) == "已验证的想法"


def test_start_restores_unfinished_round_to_best(ws):
    """轮次中途被 kill/断电：启动时把 research.md 拨回当前最佳。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, judge=judge_ok(9), verify="ai")
    guard.start()
    write_idea(state_path, "已采纳想法")
    guard.on_round_end(1)
    write_idea(state_path, "半截想法")

    guard2 = make_guard(workspace, state_path)
    guard2.start()
    assert read_idea(state_path) == "已采纳想法"


# ------------------------------------------------------------- 每轮主流程
def test_heartbeat_when_no_change(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    assert guard.on_round_end(1) == "heartbeat"
    assert guard.stats.heartbeat == 1
    assert cand_files(guard) == []
    assert not any(e["event"] == "verdict" for e in events(guard))


def test_corrupt_markers_rejected_and_restored(ws):
    """区块标记被外部 agent 弄坏：直接拒绝（守卫级判定），损坏内容也留档。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    state_path.write_text("# 缺少区块标记的损坏内容\n", encoding="utf-8")
    assert guard.on_round_end(1) == "rejected"
    assert guard.stats.rejected == 1
    # 损坏候选照样留快照（审计）；还原后状态文件结构被修复回基线
    assert len(cand_files(guard)) == 1
    evs = events(guard)
    assert any(e["event"] == "candidate" and e.get("corrupt") for e in evs)
    assert any(e["event"] == "verdict" and e["result"] == "rejected"
               for e in evs)
    assert any(e["event"] == "restored" for e in evs)
    assert read_idea(state_path) == "（暂无）"


def test_missing_state_file_skipped(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    state_path.unlink()
    assert guard.on_round_end(1) == "skipped"
    assert guard.stats.skipped == 1
    # 还原把状态文件重建回最佳内容
    assert state_path.exists()
    assert read_idea(state_path) == "（暂无）"


def test_ai_adopt_promotes_candidate(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, judge=judge_ok(9), verify="ai")
    guard.start()
    write_idea(state_path, "更好的想法")
    write_artifact(state_path, "可落地的伪代码")
    assert guard.on_round_end(1) == "adopted"
    best = json.loads(guard.best_json.read_text(encoding="utf-8"))
    assert best["round"] == 1 and best["verifier"] == "ai"
    assert best["score"] == 9 and best["id"].endswith("-r1")
    assert read_idea(state_path) == "更好的想法"
    # 快照与镜像留档；候选计数与统计一致
    assert len(cand_files(guard)) == 1
    assert state.get_section(
        guard.best_md.read_text(encoding="utf-8"), state.SECTION_ARTIFACT
    ) == "可落地的伪代码"
    assert guard.stats.candidates == 1 and guard.stats.adopted == 1


def test_ai_adopt_promotes_snapshot_not_live_state(ws):
    """评审期间 research.md 被外部再改：晋升的必须是【被验证的快照】，
    而不是评审期间被改写的实时状态。"""
    workspace, state_path = ws

    def tamper_during_judge(prompt):
        write_idea(state_path, "评审期间被外部改写")
        return True, "评分: 9"

    guard = make_guard(workspace, state_path, judge=tamper_during_judge,
                       verify="ai")
    guard.start()
    write_idea(state_path, "被验证的新想法")
    assert guard.on_round_end(1) == "adopted"
    assert state.get_section(
        guard.best_md.read_text(encoding="utf-8"), state.SECTION_IDEA
    ) == "被验证的新想法"
    # 下一轮心跳判定也以快照内容为基准
    write_idea(state_path, "被验证的新想法")
    assert guard.on_round_end(2) == "heartbeat"


def test_ai_judge_prompt_shows_candidate_snapshot(ws):
    workspace, state_path = ws
    prompts = []

    def judge(prompt):
        prompts.append(prompt)
        # 评审进行时状态文件又被改（不能影响评审看到的内容）
        write_idea(state_path, "评审期间的干扰内容")
        return True, "评分: 8"

    guard = make_guard(workspace, state_path, judge=judge, verify="ai")
    guard.start()
    write_idea(state_path, "候选想法")
    guard.on_round_end(1)
    assert "候选想法" in prompts[0]
    assert "评审期间的干扰内容" not in prompts[0]
    # 提示词包含双方完整内容与任务
    assert "测试任务" in prompts[0]
    assert "（暂无）" in prompts[0]      # 基线区块内容


def test_ai_reject_restores_best_and_keeps_snapshot(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, judge=judge_ok(3), verify="ai")
    guard.start()
    write_idea(state_path, "更差的想法")
    assert guard.on_round_end(1) == "rejected"
    assert guard.stats.rejected == 1
    # 更差的候选被还原，但快照留档（事后可补分翻案）
    assert read_idea(state_path) == "（暂无）"
    assert len(cand_files(guard)) == 1
    assert any(e["event"] == "restored" for e in events(guard))


def test_ai_unparseable_score_pends(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path,
                       judge=lambda p: (True, "说了很多但没有分数"),
                       verify="ai")
    guard.start()
    write_idea(state_path, "新想法")
    assert guard.on_round_end(1) == "pending"
    assert guard.stats.pending == 1
    assert read_idea(state_path) == "（暂无）"
    assert any("给候选打分" in t for t in guard.sink.texts("info"))


def test_ai_judge_infrastructure_failure_pends(ws):
    """评审员崩了（超时/非零退出）≠ 候选差：不下结论，挂起。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path,
                       judge=lambda p: (False, ""),
                       verify="ai")
    guard.start()
    write_idea(state_path, "新想法")
    assert guard.on_round_end(1) == "pending"


def test_ai_score_threshold_boundary(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, judge=judge_ok(7),
                       verify="ai", adopt_score=7)
    guard.start()
    write_idea(state_path, "达标想法")
    assert guard.on_round_end(1) == "adopted"

    guard2 = make_guard(workspace, state_path, judge=judge_ok(6.9),
                        verify="ai", adopt_score=7)
    write_idea(state_path, "差一点的想法")
    assert guard2.on_round_end(2) == "rejected"


def test_verify_off_adopts_without_judge(ws):
    """verify=off：不验证，最新即最佳（快照照存的防丢失模式）。"""
    workspace, state_path = ws
    called = []

    def judge(prompt):
        called.append(prompt)
        return True, "评分: 9"

    guard = make_guard(workspace, state_path, judge=judge, verify="off")
    guard.start()
    write_idea(state_path, "未验证但直接采纳")
    assert guard.on_round_end(1) == "adopted"
    assert called == []          # off 模式绝不调用评审员
    assert guard.best["verifier"] == "none"


def test_ai_snapshot_deleted_during_judge_stays_pending(ws):
    """评审通过但快照在晋升前被外部删除：无法证明被验证过 → 挂起，
    绝不能拿实时状态顶替晋升。"""
    workspace, state_path = ws

    def delete_then_score(prompt):
        for p in guard.dir.glob("cand-*.md"):
            p.unlink()
        return True, "评分: 9"

    guard = make_guard(workspace, state_path, judge=delete_then_score,
                       verify="ai")
    guard.start()
    write_idea(state_path, "新想法")
    with pytest.raises(OSError):
        guard.on_round_end(1)
    # 候选已计入、挂起等待用户补分（快照恢复后仍可翻案）
    assert guard.stats.candidates == 1
    assert guard.stats.pending == 1
    assert any(e["event"] == "verdict" and e["result"] == "pending"
               for e in events(guard))
    assert read_idea(state_path) == "（暂无）"


def test_guard_internal_exception_pends_and_raises(ws):
    """验证/晋升途中守卫自身异常：候选挂起（统计一致）+ 还原 + 向上传播。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    write_idea(state_path, "新想法")

    def explode(self, round_no, cid):
        raise OSError("模拟晋升写盘失败")

    guard._verify = explode.__get__(guard, RoundGuard)
    with pytest.raises(OSError):
        guard.on_round_end(1)
    assert guard.stats.candidates == 1 and guard.stats.pending == 1
    assert any(e["event"] == "verdict" and e["result"] == "pending"
               and "晋升失败" in e.get("reason", "") for e in events(guard))
    assert read_idea(state_path) == "（暂无）"


def test_interrupt_mid_verify_pends_without_verdict_event(ws):
    """Ctrl+C 落在验证途中：候选挂起（不写 verdict 事件——不能把中断
    伪装成已决），还原最佳后传播。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    write_idea(state_path, "新想法")

    def interrupt(self, round_no, cid):
        raise KeyboardInterrupt

    guard._verify = interrupt.__get__(guard, RoundGuard)
    with pytest.raises(KeyboardInterrupt):
        guard.on_round_end(1)
    evs = events(guard)
    assert any(e["event"] == "candidate" for e in evs)
    assert not any(e["event"] == "verdict" for e in evs)
    assert any(e["event"] == "restored" for e in evs)
    assert guard.stats.pending == 1
    assert read_idea(state_path) == "（暂无）"


def test_snapshot_write_failure_skips_round(ws):
    """候选快照写盘失败：本轮按跳过记账（不留半截候选），还原最佳。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    write_idea(state_path, "新想法")

    def explode(round_no, text):
        raise OSError("磁盘满")

    guard._snapshot_candidate = explode
    with pytest.raises(OSError):
        guard.on_round_end(1)
    assert guard.stats.candidates == 0
    assert guard.stats.skipped == 1
    assert any(e["event"] == "skipped" and "快照写盘失败" in e.get("reason", "")
               for e in events(guard))
    assert read_idea(state_path) == "（暂无）"


def test_on_round_failed_records_skip_and_restores(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    write_idea(state_path, "半截产物")
    guard.on_round_failed(1, "退出码 1")
    assert guard.stats.rounds == 1 and guard.stats.skipped == 1
    assert any(e["event"] == "skipped" and "退出码 1" in e["reason"]
               for e in events(guard))
    assert read_idea(state_path) == "（暂无）"


def test_on_round_failed_after_end_not_double_counted(ws):
    """中断晚于 on_round_end 到达：只补做还原，不重复记账、不产生
    自相矛盾的事件。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, judge=judge_ok(9), verify="ai")
    guard.start()
    write_idea(state_path, "更好的想法")
    assert guard.on_round_end(1) == "adopted"
    n_events = len(events(guard))
    guard.on_round_failed(1, "被中断，轮次未完成")
    assert len(events(guard)) == n_events
    assert guard.stats.rounds == 1 and guard.stats.skipped == 0
    assert read_idea(state_path) == "更好的想法"


def test_finish_summary_format(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, judge=judge_ok(9), verify="ai")
    guard.start()
    write_idea(state_path, "更好的想法")
    guard.on_round_end(1)
    guard.finish()
    summary = [t for t in guard.sink.texts("info")
               if "轮次守卫汇总" in t][-1]
    assert "轮次 1（候选 1：采纳 1 / 拒绝 0 / 待评分 0；" \
           "心跳 0 / 跳过 0 / 还原 0）" in summary
    assert f"当前最佳：{guard.best['id']}（第 1 轮，ai，" \
           f"评分 {guard.best['score']}）" in summary


# ------------------------------------------------- 渐进翻案（verdicts.txt）
def test_late_adoption_rehabilitates_old_candidate(ws):
    """核心卖点：挂起的旧候选补高分 → 前进式翻案（写回 research.md）。

    可翻案的是「挂起待评分」的候选（verify=user / 评审无结论等）；
    已被 AI/测试明确拒绝的候选已有终局，不再翻案。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path,
                       judge=lambda p: (True, "评审员没给出分数"),
                       verify="ai")
    guard.start()
    write_idea(state_path, "当时被低估的想法")
    assert guard.on_round_end(1) == "pending"
    cid = [e for e in events(guard) if e["event"] == "candidate"][0]["id"]

    # 用户事后补 9 分 → finish() 兑现：旧快照前进式晋升并写回状态文件
    guard.verdicts_path.write_text(f"{cid} 9 想法其实很有深度\n",
                                   encoding="utf-8")
    guard.finish()
    best = json.loads(guard.best_json.read_text(encoding="utf-8"))
    assert best["id"] == cid and best["late"] is True
    assert best["verifier"] == "user" and best["score"] == 9
    assert read_idea(state_path) == "当时被低估的想法"
    assert any(e["event"] == "restored" and e.get("why") == "旧候选被补评采纳"
               for e in events(guard))
    assert guard.stats.adopted == 1 and guard.stats.pending == 0


def test_late_adoption_dedup_across_cashins(ws):
    """同一行评分只兑现一次：on_round_end 与 finish 双通道去重。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path,
                       judge=lambda p: (True, "解析不出"), verify="ai")
    guard.start()
    write_idea(state_path, "想法 A")
    guard.on_round_end(1)                     # pending
    cid = [e for e in events(guard) if e["event"] == "candidate"][0]["id"]
    guard.verdicts_path.write_text(f"{cid} 9\n", encoding="utf-8")
    write_idea(state_path, "想法 B")
    guard.on_round_end(2)                     # 本轮结束后兑现补分
    assert guard.best["id"] == cid
    guard.finish()                            # 再次兑现：不得重复采纳
    late = [e for e in events(guard)
            if e["event"] == "verdict" and e.get("late")]
    assert len(late) == 1
    assert guard.stats.adopted == 1


def test_late_rejection_recorded(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path,
                       judge=lambda p: (True, "解析不出"), verify="ai")
    guard.start()
    write_idea(state_path, "想法")
    guard.on_round_end(1)
    cid = [e for e in events(guard) if e["event"] == "candidate"][0]["id"]
    guard.verdicts_path.write_text(f"{cid} 2 确实不行\n", encoding="utf-8")
    guard.finish()
    assert guard.best["verifier"] == "baseline"
    assert guard.stats.rejected == 1
    assert read_idea(state_path) == "（暂无）"


def test_cross_session_rehabilitation_on_start(ws):
    """跨会话翻案：上个会话挂起的候选，新会话 start() 时兑现补分。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "跨会话的想法")
    guard.on_round_end(1)                     # verify=user：挂起
    cid = [e for e in events(guard) if e["event"] == "candidate"][0]["id"]

    guard2 = make_guard(workspace, state_path, verify="user")
    guard2.verdicts_path.write_text(f"{cid} 8\n", encoding="utf-8")
    guard2.start()
    assert guard2.best["id"] == cid
    assert read_idea(state_path) == "跨会话的想法"


def test_unknown_cid_in_verdicts_warned_once(ws):
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    guard.verdicts_path.write_text("不存在的候选 9\n", encoding="utf-8")
    guard.finish()
    guard.finish()
    warns = [t for t in guard.sink.texts("warn") if "不存在" in t]
    assert len(warns) == 1


def test_badscore_line_keeps_pending_then_recovers(ws):
    """评分打错的行保持挂起（可修正）；修正后补分照常翻案。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "想法")
    guard.on_round_end(1)
    cid = [e for e in events(guard) if e["event"] == "candidate"][0]["id"]

    guard.verdicts_path.write_text(f"{cid} abc 打错了\n", encoding="utf-8")
    guard.finish()
    assert guard.best["verifier"] == "baseline"
    assert guard.stats.pending == 1

    guard.verdicts_path.write_text(f"{cid} 9 改好了\n", encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    assert read_idea(state_path) == "想法"


def test_verdict_for_current_best_ignored(ws):
    """当前最佳天然已决：对它补分不得重复采纳或自相矛盾拒绝。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, judge=judge_ok(9), verify="ai")
    guard.start()
    write_idea(state_path, "已采纳想法")
    guard.on_round_end(1)
    adopted_id = guard.best["id"]
    guard.verdicts_path.write_text(f"{adopted_id} 1\n", encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == adopted_id
    assert guard.stats.adopted == 1 and guard.stats.rejected == 0
    assert read_idea(state_path) == "已采纳想法"


def test_bad_round_field_in_history_normalized(ws):
    """历史行的 round 字段被外部改坏（字符串）：按第 0 轮归一化，
    采纳本身照常兑现（候选快照仍有效）。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path, verify="user")
    guard.start()
    write_idea(state_path, "想法")
    guard.on_round_end(1)
    cid = [e for e in events(guard) if e["event"] == "candidate"][0]["id"]
    # 把 candidate 事件的 round 改成字符串
    lines = guard.history_path.read_text(encoding="utf-8").splitlines()
    patched = []
    for ln in lines:
        ev = json.loads(ln)
        if ev.get("event") == "candidate":
            ev["round"] = "第一轮"
        patched.append(json.dumps(ev, ensure_ascii=False))
    guard.history_path.write_text("\n".join(patched) + "\n", encoding="utf-8")

    guard.verdicts_path.write_text(f"{cid} 9\n", encoding="utf-8")
    guard.finish()
    assert guard.best["id"] == cid
    assert read_idea(state_path) == "想法"


# --------------------------------------------------------- 审计日志健壮性
def test_history_truncated_line_isolated_on_append(ws):
    """上次写入中途被杀留下的无换行残行：追加时补换行把它隔离成独立
    行（保留可人工检查），新事件照常可读，不会与残行拼接成一条。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    guard.history_path.write_text(
        '{"event": "candidate", "id": "baseline-x"', encoding="utf-8")  # 无换行
    guard._append_event({"event": "heartbeat", "round": 9})
    # 新事件独立可读（残行本身是半截 JSON，照常被跳过但不会吞掉新事件）
    evs = events(guard)
    assert [e["event"] for e in evs] == ["heartbeat"]
    assert evs[0]["round"] == 9
    raw = guard.history_path.read_text(encoding="utf-8")
    assert '"id": "baseline-x"' in raw       # 残行保留、独立成行
    assert raw.endswith("\n")
    assert len(raw.strip().split("\n")) == 2


def test_history_bad_lines_skipped(ws):
    """坏行（半截 JSON / 非 JSON）不影响其余事件：逐行跳过。"""
    workspace, state_path = ws
    guard = make_guard(workspace, state_path)
    guard.start()
    with open(guard.history_path, "a", encoding="utf-8") as f:
        f.write('{"event": "candidate", "id": "坏行\n')   # 半截 JSON
        f.write('这根本不是 JSON\n')                          # 非 JSON
    guard._append_event({"event": "heartbeat", "round": 1})
    evs = events(guard)
    assert [e["event"] for e in evs] == ["baseline", "heartbeat"]


# ------------------------------------------------------------ 套件探测
def test_detect_pytest(ws, tmp_path):
    workspace, state_path = ws
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_x.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8")
    assert detect_test_suite(repo) == [sys.executable, "-m", "pytest", "-q"]


def test_detect_pytest_nested(ws, tmp_path):
    workspace, state_path = ws
    repo = tmp_path / "repo"
    (repo / "src" / "pkg" / "tests").mkdir(parents=True)
    (repo / "src" / "pkg" / "tests" / "test_x.py").write_text("", encoding="utf-8")
    assert detect_test_suite(repo) == [sys.executable, "-m", "pytest", "-q"]


def test_detect_pytest_ignores_venv_and_node_modules(ws, tmp_path):
    """虚拟环境/依赖目录里的第三方测试不会被 pytest 收集，不算套件。"""
    workspace, state_path = ws
    repo = tmp_path / "repo"
    (repo / ".venv" / "lib").mkdir(parents=True)
    (repo / ".venv" / "lib" / "test_third_party.py").write_text("", encoding="utf-8")
    (repo / "node_modules" / "pkg").mkdir(parents=True)
    (repo / "node_modules" / "pkg" / "test_x.py").write_text("", encoding="utf-8")
    assert detect_test_suite(repo) is None


def test_detect_makefile(ws, tmp_path, monkeypatch):
    """Makefile 只做存在性检查：有没有 test 目标由 make 运行时回答。"""
    workspace, state_path = ws
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Makefile").write_text("test:\n\techo ok\n", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/make")
    assert detect_test_suite(repo) == ["make", "test"]
    # 条件分支里才定义 test 目标的 Makefile 也照样探测（语义留给 make）
    (repo / "Makefile").write_text(
        "ifeq ($(OS),Windows_NT)\ntest:\n\techo win\nendif\n", encoding="utf-8")
    assert detect_test_suite(repo) == ["make", "test"]


def test_detect_makefile_search_order(ws, tmp_path, monkeypatch):
    """GNUmakefile → makefile → Makefile：make 取第一个存在的文件。"""
    workspace, state_path = ws
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Makefile").write_text("test:\n\techo ok\n", encoding="utf-8")
    (repo / "GNUmakefile").write_text("test:\n\techo gnu\n", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/make")
    assert detect_test_suite(repo) == ["make", "test"]
    assert (repo / "GNUmakefile").exists()


def test_detect_makefile_directory_is_not_suite(ws, tmp_path, monkeypatch):
    """名为 Makefile 的目录/悬空符号链接会被 make 选中后失败：按无套件。"""
    workspace, state_path = ws
    repo = tmp_path / "repo"
    (repo / "Makefile").mkdir(parents=True)
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/make")
    assert detect_test_suite(repo) is None


def test_detect_npm(ws, tmp_path, monkeypatch):
    workspace, state_path = ws
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps({"scripts": {"test": "node --test"}}), encoding="utf-8")
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/npm" if n == "npm" else None)
    assert detect_test_suite(repo) == ["/usr/bin/npm", "test"]


def test_detect_npm_placeholder_ignored(ws, tmp_path, monkeypatch):
    workspace, state_path = ws
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps({"scripts": {
            "test": "echo \"Error: no test specified\""}}), encoding="utf-8")
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/npm" if n == "npm" else None)
    assert detect_test_suite(repo) is None


def test_detect_go(ws, tmp_path, monkeypatch):
    workspace, state_path = ws
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text("module m\n", encoding="utf-8")
    (repo / "x.go").write_text("package m\n", encoding="utf-8")
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/go" if n == "go" else None)
    assert detect_test_suite(repo) == ["go", "test", "./..."]


def test_detect_go_ignores_testdata_and_vendor(ws, tmp_path, monkeypatch):
    workspace, state_path = ws
    repo = tmp_path / "repo"
    (repo / "testdata").mkdir(parents=True)
    (repo / "testdata" / "x.go").write_text("package t\n", encoding="utf-8")
    (repo / "go.mod").write_text("module m\n", encoding="utf-8")
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/go" if n == "go" else None)
    assert detect_test_suite(repo) is None


def test_detect_none(ws, tmp_path):
    workspace, state_path = ws
    assert detect_test_suite(tmp_path / "empty-repo") is None
    (tmp_path / "empty-repo").mkdir()
    assert detect_test_suite(tmp_path / "empty-repo") is None


# --------------------------------------------------------- 套件运行语义
def test_run_suite_exit_zero_ok(tmp_path):
    res = run_suite([sys.executable, "-c", "print('ok')"], tmp_path, 60)
    assert res.available and res.ok and res.reason == "exit 0"


def test_run_suite_nonzero_fails(tmp_path):
    res = run_suite([sys.executable, "-c", "import sys; sys.exit(1)"],
                    tmp_path, 60)
    assert res.available and not res.ok
    assert res.reason == "退出码 1"


def test_run_suite_pytest_exit5_unavailable(tmp_path):
    """pytest 退出码 5（未收集到测试）= 没有可执行的验证，不是失败。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    res = run_suite([sys.executable, "-m", "pytest", "-q"], empty, 120)
    assert not res.available and not res.ok
    assert "未收集到测试" in res.reason


def _fake_bin(tmp_path, name, body):
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    exe = d / name
    exe.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    exe.chmod(0o755)
    return str(exe)


def test_run_suite_make_no_rule_unavailable(tmp_path):
    """make 报「No rule to make target 'test'」：条件分支未生效等场景，
    静态探测无法判定、由 make 运行时回答 → 套件不可用，不拒绝候选。"""
    make = _fake_bin(
        tmp_path, "make",
        'echo "make: *** No rule to make target \'test\'.  Stop."; exit 2')
    res = run_suite([make, "test"], tmp_path, 60)
    assert not res.available and not res.ok
    assert "没有 test 目标" in res.reason


def test_run_suite_make_noop_unavailable(tmp_path):
    """make 退出 0 但「Nothing to be done」：没有真正执行测试。"""
    make = _fake_bin(tmp_path, "make",
                     "echo \"make: Nothing to be done for 'test'.\"; exit 0")
    res = run_suite([make, "test"], tmp_path, 60)
    assert not res.available and not res.ok
    assert "没有执行任何测试" in res.reason


def test_run_suite_go_no_tests_ran(tmp_path):
    """go 全部包 [no test files] 且退出 0：编译通过 ≠ 测试验证。"""
    go = _fake_bin(tmp_path, "go",
                   "printf '?   example.com/m\\t[no test files]\\n'; exit 0")
    res = run_suite([go, "test", "./..."], tmp_path, 60)
    assert not res.available and not res.ok
    assert "no test files" in res.reason


def test_run_suite_go_matched_no_packages(tmp_path):
    go = _fake_bin(
        tmp_path, "go",
        'echo \'go: warning: "./..." matched no packages\'; '
        'echo "no packages to test"; exit 1')
    res = run_suite([go, "test", "./..."], tmp_path, 60)
    assert not res.available
    assert "未匹配到任何包" in res.reason


def test_run_suite_go_with_real_tests_passes(tmp_path):
    go = _fake_bin(tmp_path, "go",
                   "printf 'ok  example.com/m\\t0.1s\\n'; exit 0")
    res = run_suite([go, "test", "./..."], tmp_path, 60)
    assert res.available and res.ok


def test_run_suite_timeout_fails(tmp_path):
    res = run_suite([sys.executable, "-c", "import time; time.sleep(30)"],
                    tmp_path, 0.4)
    assert res.available and not res.ok
    assert "测试超时" in res.reason


def test_run_suite_stop_callback_stops(tmp_path):
    """stop 回调在轮询间隔内兑现：整组终止，返回 stopped（无结论）。"""
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 1     # 第一次 False（启动前检查），之后 True

    res = run_suite([sys.executable, "-c", "import time; time.sleep(30)"],
                    tmp_path, 60, stop=stop)
    assert not res.available and res.stopped
    assert "用户请求停止" in res.reason


def test_run_suite_unlaunchable(tmp_path):
    res = run_suite([str(tmp_path / "no-such-cmd")], tmp_path, 60)
    assert not res.available and not res.stopped
    assert "无法启动" in res.reason


# ------------------------------------------------------- repo 解析与评分
def test_resolve_repo(ws, tmp_path, monkeypatch):
    workspace, state_path = ws
    # 显式配置优先
    assert resolve_repo("/some/repo", workspace) == Path("/some/repo")
    # 无 git：工作区本身
    assert resolve_repo("", workspace) == workspace.resolve()
    # 有 git：向上找到仓库根
    repo = tmp_path / "proj"
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()
    monkeypatch.chdir(workspace.parent)
    guard_ws = nested / "workspace"
    guard_ws.mkdir()
    assert resolve_repo("", guard_ws) == repo.resolve()


def test_parse_score():
    assert parse_score("评语\n评分: 8") == 8.0
    assert parse_score("Score: 7.5") == 7.5
    assert parse_score("评分:8（中文无空格）") == 8.0
    # 多次出现取最后一个；prescore 之类不算
    assert parse_score("评分: 3\n后面改主意了 score: 9") == 9.0
    assert parse_score("prescore: 3") is None
    assert parse_score("没有分数") is None
    # 越界夹取；负数不是合法的 0-10 分（解析不出，按挂起处理）
    assert parse_score("评分: 99") == 10.0
    assert parse_score("评分: -2") is None
    assert parse_score("") is None
