"""runner 集成测试：完整跑通研究循环，验证轮次守卫在真实循环里的行为。

用一个小 Python 脚本当「外部 agent」：每轮把想法区/产物区覆盖为
递增版本（research.md 每轮都在变）。测试仓库（rounds.repo）分别给出
通过的测试与失败的测试，验证：
  - 测试全绿 → 各轮候选依次晋升为最佳，research.md 停在最新轮；
  - 测试全红 → 各轮候选全部被拒并还原，research.md 停在基线——
    即「下一轮绝不继承更差的方案」这一核心语义；
  - 守卫自身崩溃 → 研究循环照常完成（失败一律降级、不阻断循环）。
"""
import json
import sys
from pathlib import Path

import pytest

from xuen import runner
from xuen.config import Config
from xuen.sink import Sink

# 假 agent：读 counter.txt 自增，把想法区/产物区覆盖为「第 N 版」。
# argv: <workspace> <repo_root> <prompt_file(忽略)>
AGENT_SCRIPT = r'''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from xuen import state

ws = Path(sys.argv[1])
counter = ws / "counter.txt"
n = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(n))
state.update_section_file(ws / "research.md", state.SECTION_IDEA,
                          f"第 {n} 版想法")
state.update_section_file(ws / "research.md", state.SECTION_ARTIFACT,
                          f"第 {n} 版产物")
print(f"agent round {n} done")
'''


class NullSink(Sink):
    def info(self, text): pass
    def ok(self, text): pass
    def warn(self, text): pass
    def err(self, text): pass
    def round_header(self, index, label): pass
    def agent_output(self, line): pass
    def agent_stderr(self, line): pass
    def section(self, name, content): pass


XUEN_ROOT = Path(__file__).resolve().parents[1]


def _make_repo(base: Path, ok: bool) -> Path:
    repo = base / ("repo_ok" if ok else "repo_bad")
    (repo / "tests").mkdir(parents=True)
    body = "def test_ok():\n    assert True\n" if ok \
        else "def test_bad():\n    assert False, '故意失败'\n"
    (repo / "tests" / ("test_ok.py" if ok else "test_bad.py")).write_text(
        body, encoding="utf-8")
    return repo


def _make_cfg(ws: Path, agent_script: Path, repo: Path) -> Config:
    cfg = Config()
    # 假 agent 需要 import xuen：把 xuen 包所在仓库根作为 argv[2] 传进去
    cfg.agent.command = (
        f'{sys.executable} "{agent_script}" "{ws}" '
        f'"{XUEN_ROOT}" "$prompt_file"'
    )
    cfg.agent.timeout = 120.0
    cfg.words.pick = 0                 # 跳过词库生成，循环直接开始
    cfg.loop.iterations = 3
    cfg.workspace = str(ws)
    cfg.rounds.verify = "tests"
    cfg.rounds.repo = str(repo)
    cfg.rounds.verify_timeout = 120.0
    return cfg


@pytest.fixture
def env(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    script = tmp_path / "fake_agent.py"
    script.write_text(AGENT_SCRIPT, encoding="utf-8")
    return ws, script


def _read(ws: Path, name):
    from xuen import state
    return state.get_section((ws / "research.md").read_text(encoding="utf-8"),
                             name)


def _events(ws: Path):
    return [json.loads(ln) for ln in
            (ws / "rounds" / "history.jsonl").read_text(encoding="utf-8")
            .splitlines() if ln.strip()]


def test_green_repo_each_round_promoted(env, tmp_path):
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)
    runner.run(_make_cfg(ws, script, repo), "测试任务", sink=NullSink())
    # 3 轮全绿：每轮候选都被采纳，最终停在最新轮
    assert (ws / "counter.txt").read_text() == "3"
    assert _read(ws, "IDEA") == "第 3 版想法"
    assert _read(ws, "ARTIFACT") == "第 3 版产物"
    best = json.loads((ws / "rounds" / "best.json").read_text(encoding="utf-8"))
    assert best["round"] == 3 and best["verifier"] == "tests"
    verdicts = [e for e in _events(ws) if e["event"] == "verdict"]
    assert [v["result"] for v in verdicts] == ["adopted"] * 3
    assert len(list((ws / "rounds").glob("cand-*.md"))) == 3


def test_red_repo_never_overwrites_baseline(env, tmp_path):
    """核心回归：测试全红时，更差的新方案绝不覆盖基线最佳。"""
    ws, script = env
    repo = _make_repo(tmp_path, ok=False)
    runner.run(_make_cfg(ws, script, repo), "测试任务", sink=NullSink())
    # agent 确实跑了 3 轮、每轮都写了「更新」的内容
    assert (ws / "counter.txt").read_text() == "3"
    # 但循环状态一步都没离开基线：更差的候选全部被拒并还原
    assert _read(ws, "IDEA") == "（暂无）"
    assert _read(ws, "ARTIFACT") == "（暂无）"
    best = json.loads((ws / "rounds" / "best.json").read_text(encoding="utf-8"))
    assert best["round"] == 0 and best["verifier"] == "baseline"
    verdicts = [e for e in _events(ws) if e["event"] == "verdict"]
    assert [v["result"] for v in verdicts] == ["rejected"] * 3
    restored = [e for e in _events(ws) if e["event"] == "restored"]
    assert len(restored) == 3
    # 三轮候选快照全部留档（产物不丢失，用户可事后在 verdicts.txt 补分翻案）
    assert len(list((ws / "rounds").glob("cand-*.md"))) == 3


def test_guard_crash_degrades_not_blocks(env, tmp_path, monkeypatch):
    """守卫自身崩溃 → 降级为无守卫模式，研究循环必须照常完成。"""
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)

    class ExplodingGuard:
        def __init__(self, *a, **k): pass
        def start(self): raise OSError("守卫目录不可写")
        def finish(self): raise RuntimeError("收尾也崩")
        def on_round_end(self, i): raise RuntimeError("本轮也崩")
        def on_round_failed(self, i, r): raise RuntimeError("记账也崩")

    monkeypatch.setattr(runner, "RoundGuard", ExplodingGuard)
    runner.run(_make_cfg(ws, script, repo), "测试任务", sink=NullSink())
    # 循环照常完成：agent 跑满 3 轮，状态文件正常演进
    assert (ws / "counter.txt").read_text() == "3"
    assert _read(ws, "IDEA") == "第 3 版想法"


def test_guard_startup_non_oserror_degrades(env, tmp_path):
    """守卫启用失败不止 OSError：rounds.dir 为非法路径（如 YAML 双引号里
    的 "\\0" 转义）时 Path.resolve/mkdir 抛 ValueError，必须同样降级——
    守卫的既定契约是「失败一律降级、绝不阻断研究循环」。"""
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)
    cfg = _make_cfg(ws, script, repo)
    cfg.rounds.dir = "guard\0dir"      # 真实复现：resolve 抛 ValueError
    assert cfg.rounds.enabled
    runner.run(cfg, "测试任务", sink=NullSink())
    # 循环照常完成，且没有半截的守卫目录
    assert (ws / "counter.txt").read_text() == "3"
    assert _read(ws, "IDEA") == "第 3 版想法"
    assert not (ws / "rounds").exists()


def test_bad_workspace_path_friendly_error(env, tmp_path):
    """非法工作区路径（配置错误）应给友好提示，不是 traceback。"""
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)
    cfg = _make_cfg(ws, script, repo)
    cfg.workspace = "bad\0dir"
    with pytest.raises(SystemExit) as ei:
        runner.run(cfg, "测试任务", sink=NullSink())
    assert "工作区不可用" in str(ei.value)


def test_no_rounds_runs_legacy_behavior(env, tmp_path):
    """--no-rounds：完全退回旧行为（无快照、无最佳、每轮直接覆盖）。"""
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)
    cfg = _make_cfg(ws, script, repo)
    cfg.rounds.enabled = False
    runner.run(cfg, "测试任务", sink=NullSink())
    assert (ws / "counter.txt").read_text() == "3"
    assert _read(ws, "IDEA") == "第 3 版想法"
    assert not (ws / "rounds").exists()


def test_late_verdict_adoption_shown_in_finish(env, tmp_path, monkeypatch):
    """循环期间补交的评分在 finish() 兑现后，最终展示不能停在旧内容。"""
    from xuen.rounds import RoundGuard
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)
    cfg = _make_cfg(ws, script, repo)
    cfg.rounds.verify = "user"
    cfg.loop.iterations = 1

    real_on_round_end = RoundGuard.on_round_end

    def on_round_end_with_late_verdict(self, i):
        result = real_on_round_end(self, i)
        # 模拟「用户看到挂起候选后、循环还没结束就补交评分」
        cid = [e for e in self._read_events()
               if e.get("event") == "candidate"][-1]["id"]
        (self.dir / "verdicts.txt").write_text(f"{cid} 9\n", encoding="utf-8")
        return result

    monkeypatch.setattr(RoundGuard, "on_round_end",
                        on_round_end_with_late_verdict)

    class FinishSink(NullSink):
        def __init__(self):
            self.final = None

        def finish(self, idea, artifact):
            self.final = (idea, artifact)

    sink = FinishSink()
    runner.run(cfg, "测试任务", sink=sink)
    # 补分在 finish() 兑现：最佳与 research.md 都翻案为第 1 轮候选
    assert _read(ws, "IDEA") == "第 1 版想法"
    best = json.loads((ws / "rounds" / "best.json").read_text(encoding="utf-8"))
    assert best["round"] == 1 and best["late"] is True
    # 最终展示必须与 research.md 一致（修复前这里停在还原后的「（暂无）」）
    assert sink.final == ("第 1 版想法", "第 1 版产物")


def test_interrupt_after_guard_not_double_counted(env, tmp_path, monkeypatch):
    """Ctrl+C 晚到（守卫已完成本轮判定）时不得重复按失败/未完成记账：
    history 里同一轮不能既有候选又记 skipped，汇总的轮次数/跳过数也
    不能被虚增；已完成的判定（如采纳）不得被中断改写。"""
    from xuen.rounds import RoundGuard
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)
    cfg = _make_cfg(ws, script, repo)
    cfg.loop.iterations = 1

    real_on_round_end = RoundGuard.on_round_end

    def on_round_end_then_interrupt(self, i):
        real_on_round_end(self, i)
        # 模拟中断落在守卫处理完之后（如随后上报区块内容、打印汇总时）
        raise KeyboardInterrupt

    monkeypatch.setattr(RoundGuard, "on_round_end",
                        on_round_end_then_interrupt)

    class InfoSink(NullSink):
        def __init__(self):
            self.infos = []

        def info(self, text):
            self.infos.append(text)

    sink = InfoSink()
    with pytest.raises(KeyboardInterrupt):
        runner.run(cfg, "测试任务", sink=sink)

    # 本轮候选已通过测试并晋升：中断不撤销已完成的守卫结论
    best = json.loads((ws / "rounds" / "best.json").read_text(encoding="utf-8"))
    assert best["verifier"] == "tests" and best["round"] == 1
    assert _read(ws, "IDEA") == "第 1 版想法"
    # 修复前：这里会多出一条「被中断，轮次未完成」的 skipped 事件
    assert not any(e["event"] == "skipped" for e in _events(ws))
    summary = [t for t in sink.infos if "轮次守卫汇总" in t][-1]
    assert "轮次 1（候选 1：采纳 1" in summary


def test_interrupt_mid_guard_restores_without_double_count(
        env, tmp_path, monkeypatch):
    """Ctrl+C 落在守卫验证途中（候选已快照、尚未定论）：仍要还原最佳
    （未验证的半截状态不能流进下一轮起点），但该轮已按完成轮次记账，
    不能再记 skipped、也不能把轮次数重复计一遍。"""
    from xuen.rounds import RoundGuard
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)
    cfg = _make_cfg(ws, script, repo)
    cfg.loop.iterations = 1

    def verify_then_interrupt(self, round_no, cid):
        raise KeyboardInterrupt

    monkeypatch.setattr(RoundGuard, "_verify", verify_then_interrupt)

    with pytest.raises(KeyboardInterrupt):
        runner.run(cfg, "测试任务", sink=NullSink())

    events = _events(ws)
    # 候选已快照（产物不丢）、尚未定论；状态被还原到基线
    assert any(e["event"] == "candidate" for e in events)
    assert not any(e["event"] == "verdict" for e in events)
    assert not any(e["event"] == "skipped" for e in events)
    assert any(e["event"] == "restored" for e in events)
    assert _read(ws, "IDEA") == "（暂无）"
    best = json.loads((ws / "rounds" / "best.json").read_text(encoding="utf-8"))
    assert best["verifier"] == "baseline"


def test_red_repo_pending_via_user_verdicts(env, tmp_path):
    """红测试 + verify=user：候选挂起；verdicts.txt 补高分后前进式翻案。"""
    from xuen import state
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)   # 用绿仓库避免测试干扰，验证走 user
    cfg = _make_cfg(ws, script, repo)
    cfg.rounds.verify = "user"
    runner.run(cfg, "测试任务", sink=NullSink())
    # 3 轮全部挂起：状态停在基线，快照留档
    assert _read(ws, "IDEA") == "（暂无）"
    verdicts = [e for e in _events(ws) if e["event"] == "verdict"]
    assert [v["result"] for v in verdicts] == ["pending"] * 3
    cands = sorted((ws / "rounds").glob("cand-*.md"))
    assert len(cands) == 3
    # 用户给第 2 轮候选补 9 分 → 前进式晋升并写回状态文件
    cid = [e for e in _events(ws) if e["event"] == "candidate"][1]["id"]
    (ws / "rounds" / "verdicts.txt").write_text(f"{cid} 9 想法更有深度\n",
                                                encoding="utf-8")
    # 新一轮 xuen 启动（同一工作区）：start() 时兑现补分
    from xuen.rounds import RoundGuard
    guard = RoundGuard(cfg, "测试任务", ws / "research.md", ws, NullSink())
    guard.start()
    assert guard.best["id"] == cid
    snap_text = (ws / "rounds" / f"cand-{cid}.md").read_text(encoding="utf-8")
    assert state.get_section(snap_text, state.SECTION_IDEA) in (
        "第 2 版想法", "第 1 版想法", "第 3 版想法")
    assert _read(ws, "IDEA") == state.get_section(snap_text, state.SECTION_IDEA)


class _ScriptedAgent:
    """用行为闭包替代 ShellAgent 的假 agent：不启真实进程，行为完全可控。"""

    def __init__(self, behavior):
        self._behavior = behavior
        self.returncode = None
        self.timed_out = False
        self.user_killed = False

    def run(self, prompt):
        return self._behavior(self)

    def kill(self):
        pass


def test_user_killed_round_restores_best(env, tmp_path, monkeypatch):
    """TUI 按 q 终止运行中的 agent：半截区块必须还原最佳——重跑时的起点
    必须是已验证内容，而不是被 kill 时只写了一半的候选。"""
    from xuen import state as st
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)
    cfg = _make_cfg(ws, script, repo)
    cfg.loop.iterations = 1

    class StopAfterKill(NullSink):
        stopped = False

        def should_stop(self):
            return self.stopped

    sink = StopAfterKill()

    def behavior(agent):
        # agent 只来得及写想法区就被用户杀掉（TUI 按 q / Ctrl+C）
        st.update_section_file(ws / "research.md", st.SECTION_IDEA,
                               "被 kill 的半截想法")
        agent.returncode = -9
        agent.user_killed = True
        sink.stopped = True

    monkeypatch.setattr(runner, "ShellAgent",
                        lambda *a, **k: _ScriptedAgent(behavior))
    runner.run(cfg, "测试任务", sink=sink)

    # 半截内容没有留在状态文件里，循环停在基线最佳上；轮次按「跳过」记账
    assert _read(ws, "IDEA") == "（暂无）"
    best = json.loads((ws / "rounds" / "best.json").read_text(encoding="utf-8"))
    assert best["verifier"] == "baseline"
    events = _events(ws)
    assert any(e["event"] == "skipped" and "用户终止" in e.get("reason", "")
               for e in events)
    assert not any(e["event"] == "candidate" for e in events)


def test_interrupted_round_restores_best(env, tmp_path, monkeypatch):
    """非 TUI 下 Ctrl+C 中断 agent：半截区块同样还原最佳，重跑从已验证
    内容继续（此前中断轮次不归还，半截内容会流进下一轮起点）。"""
    from xuen import state as st
    ws, script = env
    repo = _make_repo(tmp_path, ok=True)
    cfg = _make_cfg(ws, script, repo)

    def behavior(agent):
        st.update_section_file(ws / "research.md", st.SECTION_IDEA,
                               "中断时的半截想法")
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "ShellAgent",
                        lambda *a, **k: _ScriptedAgent(behavior))
    with pytest.raises(KeyboardInterrupt):
        runner.run(cfg, "测试任务", sink=NullSink())

    assert _read(ws, "IDEA") == "（暂无）"
    best = json.loads((ws / "rounds" / "best.json").read_text(encoding="utf-8"))
    assert best["verifier"] == "baseline"
