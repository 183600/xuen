"""round_guard 的单元测试 + 本地 git 全流程集成测试。

集成测试在临时目录里搭一个「工作仓库 + bare origin」，把 round_guard.py
拷进去当真实子进程跑，覆盖：基线化 / 晋升 / 拒绝（保护最佳）/ 无改动心跳 /
用户裁决回滚 / 最佳状态未知时的 worktree 补验证 / AI 评分（代替人类：
无法自动验证时的采纳与拒绝、AI 不可用退回人工、防"删测试凑通过"、
用户翻案优先于 AI）。

AI 评分测试用 PATH 里的假 opencode（shell 脚本输出固定 SCORE/VERDICT），
不依赖真实网络；非 AI 用例一律设 AIJUDGE_ENABLED=0，保证确定性。
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_SRC = REPO_ROOT / ".github" / "scripts" / "round_guard.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("round_guard_under_test", GUARD_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git_env():
    e = os.environ.copy()
    e.update({
        "GIT_AUTHOR_NAME": "tester",
        "GIT_AUTHOR_EMAIL": "tester@example.com",
        "GIT_COMMITTER_NAME": "tester",
        "GIT_COMMITTER_EMAIL": "tester@example.com",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        # 非 AI 用例一律关闭 AI 评分（即使宿主机装了 opencode / 配了 key）
        "AIJUDGE_ENABLED": "0",
        "AIJUDGE_API_KEY": "",
    })
    return e


def run(cmd, cwd):
    p = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True,
                       text=True, env=git_env(), timeout=120)
    assert p.returncode == 0, f"{cmd} 失败: {p.stderr}\n{p.stdout}"
    return p


def guard_run(repo: Path, *args, env=None):
    # Python 的 .pyc 只按「源文件 mtime 秒 + 大小」判定是否过期：这些集成
    # 测试在同一个合成仓库里连续多轮改写同大小文件（如 X = 'v1' -> 'v2'），
    # 若都落在同一秒内，guard 自动验证里的 pytest 会命中上一轮留下的
    # __pycache__、导入旧内容，使候选验证结果随机翻转（好候选被拒/坏候选
    # 通过）。测试不应依赖宿主的字节码缓存时序，每次调用 guard 前清一次。
    for d in repo.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    return subprocess.run(
        [sys.executable, str(repo / ".github" / "scripts" / "round_guard.py"), *args],
        cwd=str(repo), capture_output=True, text=True, env=env or git_env(), timeout=600,
    )


def make_repo(tmp_path: Path):
    origin = tmp_path / "origin.git"
    run(["git", "init", "--bare", "-b", "master", str(origin)], cwd=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init", "-b", "master"], cwd=repo)
    run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
    (repo / ".github" / "scripts").mkdir(parents=True)
    shutil.copy2(GUARD_SRC, repo / ".github" / "scripts" / "round_guard.py")
    (repo / ".gitignore").write_text("__pycache__/\n*.py[cod]\n.pytest_cache/\n",
                                     encoding="utf-8")
    (repo / "main.py").write_text("print('v1')\n", encoding="utf-8")
    (repo / "xuen_pkg").mkdir()
    (repo / "xuen_pkg" / "__init__.py").write_text("X = 'v1'\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_mini.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-m", "init"], cwd=repo)
    run(["git", "push", "-u", "origin", "master"], cwd=repo)
    return repo, origin


def origin_refs(origin: Path) -> dict:
    p = run(["git", "show-ref"], cwd=origin)
    refs = {}
    for ln in p.stdout.splitlines():
        sha, ref = ln.split()
        refs[ref] = sha
    return refs


def origin_show(origin: Path, path: str) -> str:
    p = subprocess.run(["git", "show", f"master:{path}"], cwd=str(origin),
                       capture_output=True, text=True, env=git_env(), timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


def read_state(origin: Path) -> dict:
    return json.loads(origin_show(origin, ".rounds/state.json"))


# ---------------------------------------------------------------- 单元测试

def test_parse_verdicts():
    rg = load_guard()
    text = (rg.VERDICTS_HEADER
            + "\nsnap/20261016-061234-r3: 8\n"
            + "snap/aaa: accept\nsnap/bbb: reject\n"
            + "这不是一个合法行\n"
            + "snap/ccc: 10  # 满分\n")
    res = rg.parse_verdicts(text)
    got = [(s, v) for (s, v, _raw) in res if s]
    assert ("snap/20261016-061234-r3", 8) in got
    assert ("snap/aaa", "accept") in got
    assert ("snap/bbb", "reject") in got
    assert ("snap/ccc", 10) in got
    assert sum(1 for (s, _v, _raw) in res if s is None) == 1


def test_decide_matrix():
    rg = load_guard()
    # 候选通过 -> 晋升（无论最佳状态）
    assert rg.decide("pass", "pass")[0] == "promote"
    assert rg.decide("pass", "fail")[0] == "promote"
    assert rg.decide("pass", "unknown")[0] == "promote"
    assert rg.decide("pass", "none")[0] == "promote"
    # 候选失败 -> 不采纳（最佳通过时明确"保护最佳"）
    assert rg.decide("fail", "pass")[0] == "reject"
    assert rg.decide("fail", "fail")[0] == "reject"
    assert rg.decide("fail", "unknown")[0] == "reject"
    # 无法自动验证 -> 用户评分
    assert rg.decide("none", "pass")[0] == "pending_user"
    assert rg.decide("none", "unknown")[0] == "pending_user"


def test_detect_test_commands(tmp_path):
    rg = load_guard()
    assert rg.detect_test_commands(tmp_path) == []
    (tmp_path / "main.py").write_text("print(1)\n")
    (tmp_path / "xuen").mkdir()
    (tmp_path / "xuen" / "__init__.py").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("")
    joined = [" ".join(map(str, c)) for c in rg.detect_test_commands(tmp_path)]
    assert any("pytest" in j for j in joined)
    assert any("compileall" in j for j in joined)
    assert any("main.py --help" in j for j in joined)
    assert any("import xuen" in j for j in joined)


def test_state_roundtrip_and_upsert(tmp_path, monkeypatch):
    rg = load_guard()
    monkeypatch.setattr(rg, "ROUNDS", tmp_path / ".rounds")
    monkeypatch.setattr(rg, "STATE_FILE", tmp_path / ".rounds" / "state.json")
    st = rg.default_state()
    rg.upsert_round(st, {"id": "a", "verdict": "promoted"})
    rg.upsert_round(st, {"id": "a", "verdict": "rejected"})  # upsert 幂等
    assert len(st["rounds"]) == 1
    assert st["rounds"][0]["verdict"] == "rejected"
    rg.save_state(st)
    st2 = rg.load_state()
    assert st2["rounds"][0]["verdict"] == "rejected"


def test_round_id_format():
    rg = load_guard()
    rid = rg.round_id(7)
    assert rid.endswith("-r7")
    snap = f"snap/{rid}"
    assert rg.parse_verdicts(f"{snap}: 5\n")[0][0] == snap


def test_parse_ai_reply():
    rg = load_guard()
    # 标准输出
    r = rg.parse_ai_reply("SCORE: 8\nVERDICT: accept\nREASON: 修好了边界\n\n分析……")
    assert r["score"] == 8 and r["verdict"] == "accept" and r["reason"] == "修好了边界"
    # 只有分数也可以（此时按阈值裁决）
    r = rg.parse_ai_reply("SCORE: 3")
    assert r["score"] == 3 and r["verdict"] is None
    # 中文冒号 / markdown 加粗 / 中文裁决词
    r = rg.parse_ai_reply("**SCORE**：9\n**VERDICT**：采纳\nREASON: 好")
    assert r["score"] == 9 and r["verdict"] == "accept"
    r = rg.parse_ai_reply("VERDICT: 拒绝")
    assert r["verdict"] == "reject"
    # 分数越界 -> 钳制到 1-10
    assert rg.parse_ai_reply("SCORE: 99")["score"] == 10
    assert rg.parse_ai_reply("SCORE: 0")["score"] == 1
    # ANSI 噪声不影响解析
    r = rg.parse_ai_reply("\x1b[32mnoise\x1b[0m\nSCORE: 7\nVERDICT: reject\n")
    assert r["score"] == 7 and r["verdict"] == "reject"
    # 模型先复读格式说明再作答 -> 取最后一次出现
    r = rg.parse_ai_reply(
        "SCORE: <1-10 的整数>\nVERDICT: accept 或 reject\nSCORE: 6\nVERDICT: reject\n")
    assert r["score"] == 6 and r["verdict"] == "reject"
    # 完全无法解析
    assert rg.parse_ai_reply("今天天气不错") is None
    assert rg.parse_ai_reply("") is None


def test_ai_judge_config_and_threshold():
    rg = load_guard()
    # 代码默认
    cfg = rg.ai_judge_config({})
    assert cfg["enabled"] is True
    assert cfg["review_promoted"] is False
    assert cfg["min_score"] is None
    # state.json 覆盖
    st = {"promote_score": 8, "ai_judge": {"enabled": False, "min_score": 6}}
    cfg = rg.ai_judge_config(st)
    assert cfg["enabled"] is False
    assert cfg["min_score"] == 6
    assert rg.ai_judge_threshold(cfg, st) == 6
    # min_score 未设时跟随 promote_score
    assert rg.ai_judge_threshold(rg.ai_judge_config({}), {"promote_score": 8}) == 8
    assert rg.ai_judge_threshold(rg.ai_judge_config({}), {}) == 7


def test_ai_judge_config_env_override(monkeypatch):
    rg = load_guard()
    monkeypatch.setenv("AIJUDGE_ENABLED", "0")
    assert rg.ai_judge_config({})["enabled"] is False
    monkeypatch.setenv("AIJUDGE_ENABLED", "1")
    monkeypatch.setenv("AIJUDGE_MIN_SCORE", "9")
    monkeypatch.setenv("AIJUDGE_REVIEW_PROMOTED", "true")
    cfg = rg.ai_judge_config({"ai_judge": {"enabled": False}})
    assert cfg["enabled"] is True        # 环境变量优先于 state
    assert cfg["min_score"] == 9
    assert cfg["review_promoted"] is True


def test_ai_result_final():
    rg = load_guard()
    base = {"ok": False, "score": None, "verdict": None, "final": None,
            "reason": "", "provider": None, "model": None, "error": None}
    # 分数过阈值
    assert rg._ai_result("oc", "m", {"score": 8, "verdict": None, "reason": "r"},
                         7, dict(base))["final"] == "accept"
    # 分数不过阈值
    assert rg._ai_result("oc", "m", {"score": 6, "verdict": None, "reason": "r"},
                         7, dict(base))["final"] == "reject"
    # 显式 VERDICT 优先于分数
    assert rg._ai_result("api", "m", {"score": 3, "verdict": "accept", "reason": "r"},
                         7, dict(base))["final"] == "accept"


# ---------------------------------------------------------------- 集成测试

def test_full_lifecycle(tmp_path):
    repo, origin = make_repo(tmp_path)

    # 1) init：基线化（打 baseline 快照标签 + 基线验证 + 状态落盘）
    r = guard_run(repo, "init")
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["best"]["snap"].startswith("snap/baseline-")
    assert st["best"]["tests"] == "pass"          # tests/ + main.py + import 都过
    refs = origin_refs(origin)
    assert any(ref.startswith("refs/tags/snap/baseline-") for ref in refs)
    assert "snap/" in origin_show(origin, ".rounds/verdicts.txt")  # 评分模板已上库

    # 2) 好改动 -> 候选通过测试 -> 晋升为最佳
    (repo / "xuen_pkg" / "__init__.py").write_text("X = 'v2'\n", encoding="utf-8")
    r = guard_run(repo, "after-round", "--iter", "1")
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "promoted"
    assert st["best"]["snap"].endswith("-r1")
    assert origin_show(origin, "xuen_pkg/__init__.py") == "X = 'v2'\n"
    assert any(ref.endswith("-r1") for ref in origin_refs(origin))  # 快照已推送

    # 3) 坏改动（语法错误）-> 候选验证失败 -> 拒绝，master 保持最佳
    (repo / "main.py").write_text("print('broken'\n", encoding="utf-8")
    r = guard_run(repo, "after-round", "--iter", "2")
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "rejected"
    assert origin_show(origin, "main.py") == "print('v1')\n"   # master 未被污染
    assert (repo / "main.py").read_text(encoding="utf-8") == "print('v1')\n"  # 工作区回到最佳
    assert any(ref.endswith("-r2") for ref in origin_refs(origin))  # 坏候选也留了快照

    # 4) 无改动 -> 心跳记录
    r = guard_run(repo, "after-round", "--iter", "3")
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "noop"

    # 5) 用户裁决：回滚到基线快照（旧方案翻案）
    baseline_snap = next(r_["snap"] for r_ in st["rounds"]
                         if r_["snap"].startswith("snap/baseline-"))
    vd = repo / ".rounds" / "verdicts.txt"
    vd.write_text(vd.read_text(encoding="utf-8") + f"\n{baseline_snap}: 9\n",
                  encoding="utf-8")
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-m", "user: score baseline 9"], cwd=repo)
    run(["git", "push"], cwd=repo)
    r = guard_run(repo, "init")
    assert r.returncode == 0, r.stdout + r.stderr
    # master 内容回滚到基线，但历史向前、不重写
    assert origin_show(origin, "xuen_pkg/__init__.py") == "X = 'v1'\n"
    st = read_state(origin)
    assert st["best"]["snap"] == baseline_snap
    # 用户的评分行保留在 master 上，且已归档
    assert f"{baseline_snap}: 9" in origin_show(origin, ".rounds/verdicts.txt")
    assert baseline_snap in origin_show(origin, ".rounds/verdicts.processed.txt")

    # 6) 下一轮从（回滚后的）最佳出发：好改动再次晋升
    (repo / "xuen_pkg" / "__init__.py").write_text("X = 'v3'\n", encoding="utf-8")
    r = guard_run(repo, "after-round", "--iter", "4")
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "promoted"
    assert origin_show(origin, "xuen_pkg/__init__.py") == "X = 'v3'\n"


def test_best_unknown_uses_worktree_baseline(tmp_path):
    """state 里最佳测试状态未知时，after-round 会用 worktree 给最佳补基线验证。"""
    repo, origin = make_repo(tmp_path)
    assert guard_run(repo, "init").returncode == 0
    # 人为把本地 state 的最佳状态抹成未知（模拟历史状态丢失）
    local_state = repo / ".rounds" / "state.json"
    st = json.loads(local_state.read_text(encoding="utf-8"))
    st["best"]["tests"] = None
    local_state.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    # 一个能通过全部测试的改动
    (repo / "xuen_pkg" / "__init__.py").write_text("X = 'v2'\n", encoding="utf-8")
    r = guard_run(repo, "after-round", "--iter", "1")
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "promoted"
    # 最佳基线已被补验并缓存
    assert any(r_["snap"] and r_["snap"].startswith("snap/baseline-")
               and r_.get("verdict") == "promoted" for r_ in st["rounds"])


def test_ai_protected_dirs_tamper_is_reverted(tmp_path):
    """AI 改了 .github/.rounds 也会被回滚，不进候选。

    注意调用顺序与工作流一致：bash 先恢复 .github/.rounds 再调用 guard
    （否则被篡改的 guard 文件本身就会"替自己放行"）。
    """
    repo, origin = make_repo(tmp_path)
    assert guard_run(repo, "init").returncode == 0
    # 模拟 AI：篡改受保护目录 + 正常代码改动
    (repo / ".github" / "scripts" / "round_guard.py").write_text("print('hacked')\n",
                                                                 encoding="utf-8")
    (repo / ".rounds" / "state.json").write_text('{"hacked": true}\n', encoding="utf-8")
    (repo / "xuen_pkg" / "__init__.py").write_text("X = 'v2'\n", encoding="utf-8")
    # 工作流在调用 guard 前先回滚受保护目录
    run(["git", "checkout", "HEAD", "--", ".github", ".rounds"], cwd=repo)
    run(["git", "clean", "-fdq", ".github", ".rounds"], cwd=repo)
    r = guard_run(repo, "after-round", "--iter", "1")
    assert r.returncode == 0, r.stdout + r.stderr
    # master 上的 guard 与 state 都未被篡改
    assert "hacked" not in origin_show(origin, ".github/scripts/round_guard.py")
    assert "hacked" not in origin_show(origin, ".rounds/state.json")
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "promoted"
    # 候选 diff 不包含受保护目录
    rid = st["rounds"][-1]["id"]
    doc = origin_show(origin, f".rounds/pending/{rid}.md")
    assert ".github/scripts/round_guard.py" not in doc
    assert "xuen_pkg/__init__.py" in doc


# ---------------------------------------------------------------- AI 评分集成测试
# 用 PATH 里的假 opencode（输出固定 SCORE/VERDICT 的 shell 脚本）代替真实
# AI 渠道，完整覆盖「快照 -> 验证 -> AI 评分 -> 晋升/拒绝 -> 用户翻案」链路。

SHIM_OK8 = "#!/bin/sh\nprintf 'SCORE: 8\\nVERDICT: accept\\nREASON: 合理改进\\n'\n"
SHIM_LOW3 = "#!/bin/sh\nprintf 'SCORE: 3\\nVERDICT: reject\\nREASON: 引入风险\\n'\n"
SHIM_FAIL = "#!/bin/sh\necho 'opencode: network error' >&2\nexit 3\n"


def make_shim(shim_dir: Path, body: str) -> Path:
    shim_dir.mkdir(parents=True, exist_ok=True)
    f = shim_dir / "opencode"
    f.write_text(body, encoding="utf-8")
    f.chmod(0o755)
    return shim_dir


def ai_env(shim_dir: Path | None = None) -> dict:
    """开启 AI 评分的 guard 运行环境；shim_dir 放在 PATH 最前（遮蔽真 opencode）。"""
    e = git_env()
    e["AIJUDGE_ENABLED"] = "1"
    e["AIJUDGE_API_KEY"] = ""            # 强制走 opencode 渠道
    if shim_dir is not None:
        e["PATH"] = f"{shim_dir}:{e['PATH']}"
    return e


def make_repo_no_tests(tmp_path: Path):
    """没有任何可自动验证手段的仓库（无测试 / 无 .py / 无 main.py）。

    这是 AI 评分的主场：候选验证恒为 none -> 交给 AI 代替人类裁决。
    """
    origin = tmp_path / "origin.git"
    run(["git", "init", "--bare", "-b", "master", str(origin)], cwd=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init", "-b", "master"], cwd=repo)
    run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
    (repo / ".github" / "scripts").mkdir(parents=True)
    shutil.copy2(GUARD_SRC, repo / ".github" / "scripts" / "round_guard.py")
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (repo / "README.md").write_text("# demo\n\n示例仓库，无测试。\n", encoding="utf-8")
    (repo / "data.txt").write_text("v1\n", encoding="utf-8")
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-m", "init"], cwd=repo)
    run(["git", "push", "-u", "origin", "master"], cwd=repo)
    return repo, origin


def make_repo_strict(tmp_path: Path):
    """测试有真实断言的仓库：改产品必须同步改测试才能通过。"""
    repo, origin = make_repo(tmp_path)
    (repo / "tests" / "test_mini.py").write_text(
        "from xuen_pkg import X\n\n\ndef test_value():\n    assert X == 'v1'\n",
        encoding="utf-8")
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-m", "strict tests"], cwd=repo)
    run(["git", "push"], cwd=repo)
    return repo, origin


def test_ai_judge_full_lifecycle(tmp_path):
    repo, origin = make_repo_no_tests(tmp_path)

    # 1) AI 渠道坏掉 -> 无法自动验证的候选进入"等待用户评分"，master 保持最佳
    bad = make_shim(tmp_path / "shim_bad", SHIM_FAIL)
    (repo / "data.txt").write_text("v2\n", encoding="utf-8")
    r = guard_run(repo, "after-round", "--iter", "1", env=ai_env(bad))
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "pending_user"
    assert st["rounds"][-1]["ai"]["error"]            # 记录了 AI 失败原因
    assert origin_show(origin, "data.txt") == "v1\n"  # master 未被污染

    # 2) AI 恢复（8 分）-> init 时补评分 -> 采纳为最佳（by=ai）
    good = make_shim(tmp_path / "shim_good", SHIM_OK8)
    r = guard_run(repo, "init", env=ai_env(good))
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    r1 = next(r_ for r_ in st["rounds"] if r_["id"].endswith("-r1"))
    assert r1["verdict"] == "promoted" and r1["by"] == "ai"
    assert r1["ai"]["score"] == 8
    assert st["best"]["by"] == "ai"
    assert origin_show(origin, "data.txt") == "v2\n"
    # review.md 里能看到 AI 裁决标注
    assert "AI" in origin_show(origin, ".rounds/review.md")

    # 3) AI 打 3 分 -> 拒绝，更好的方案（当前最佳）不被覆盖
    low = make_shim(tmp_path / "shim_low", SHIM_LOW3)
    (repo / "data.txt").write_text("v3\n", encoding="utf-8")
    r = guard_run(repo, "after-round", "--iter", "2", env=ai_env(low))
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "rejected"
    assert st["rounds"][-1]["by"] == "ai"
    assert origin_show(origin, "data.txt") == "v2\n"  # v2 没被 v3 覆盖

    # 4) 用户翻案优先于 AI：采纳被 AI 拒绝的 r2 快照
    snap2 = next(r_["snap"] for r_ in st["rounds"] if r_["id"].endswith("-r2"))
    vd = repo / ".rounds" / "verdicts.txt"
    vd.write_text(vd.read_text(encoding="utf-8") + f"\n{snap2}: 9\n",
                  encoding="utf-8")
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-m", "user: accept r2"], cwd=repo)
    run(["git", "push"], cwd=repo)
    r = guard_run(repo, "init", env=ai_env(good))
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["best"]["snap"] == snap2 and st["best"]["by"] == "user"
    assert origin_show(origin, "data.txt") == "v3\n"


def test_ai_judge_blocks_test_gaming(tmp_path):
    """测试通过但改动过测试文件的候选，会被 AI 复核拦截（防"删测试凑通过"）。"""
    repo, origin = make_repo_strict(tmp_path)
    assert guard_run(repo, "init").returncode == 0

    # 候选：把测试弱化成永真 + 改产品代码 -> 测试通过但 AI 复核给 3 分 -> 拒绝
    (repo / "tests" / "test_mini.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    (repo / "xuen_pkg" / "__init__.py").write_text("X = 'v2'\n", encoding="utf-8")
    low = make_shim(tmp_path / "shim_low", SHIM_LOW3)
    r = guard_run(repo, "after-round", "--iter", "1", env=ai_env(low))
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "rejected"
    assert st["rounds"][-1]["by"] == "ai"
    assert origin_show(origin, "xuen_pkg/__init__.py") == "X = 'v1'\n"

    # 合理地同步更新测试 + AI 认可（8 分）-> 正常晋升
    (repo / "tests" / "test_mini.py").write_text(
        "from xuen_pkg import X\n\n\ndef test_value():\n    assert X == 'v2'\n",
        encoding="utf-8")
    (repo / "xuen_pkg" / "__init__.py").write_text("X = 'v2'\n", encoding="utf-8")
    good = make_shim(tmp_path / "shim_good", SHIM_OK8)
    r = guard_run(repo, "after-round", "--iter", "2", env=ai_env(good))
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "promoted"
    assert st["rounds"][-1]["by"] == "ai"
    assert origin_show(origin, "xuen_pkg/__init__.py") == "X = 'v2'\n"


def test_ai_judge_review_promoted_option(tmp_path):
    """review_promoted 开启后，即使测试全过的普通候选也要过 AI 这一关。"""
    repo, origin = make_repo(tmp_path)
    assert guard_run(repo, "init").returncode == 0

    # 通过 state.json 打开 review_promoted（提交到 master 使其生效）
    local = repo / ".rounds" / "state.json"
    st = json.loads(local.read_text(encoding="utf-8"))
    st["ai_judge"] = {"enabled": True, "review_promoted": True}
    local.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-m", "cfg: review_promoted on"], cwd=repo)
    run(["git", "push"], cwd=repo)

    # 测试通过的普通产品改动，AI 只给 3 分 -> 拒绝，最佳不被覆盖
    (repo / "xuen_pkg" / "__init__.py").write_text("X = 'v2'\n", encoding="utf-8")
    low = make_shim(tmp_path / "shim_low", SHIM_LOW3)
    r = guard_run(repo, "after-round", "--iter", "1", env=ai_env(low))
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "rejected"
    assert st["rounds"][-1]["by"] == "ai"
    assert origin_show(origin, "xuen_pkg/__init__.py") == "X = 'v1'\n"

    # AI 给 8 分 -> 晋升
    (repo / "xuen_pkg" / "__init__.py").write_text("X = 'v3'\n", encoding="utf-8")
    good = make_shim(tmp_path / "shim_good", SHIM_OK8)
    r = guard_run(repo, "after-round", "--iter", "2", env=ai_env(good))
    assert r.returncode == 0, r.stdout + r.stderr
    st = read_state(origin)
    assert st["rounds"][-1]["verdict"] == "promoted"
    assert st["rounds"][-1]["by"] == "ai"
    assert origin_show(origin, "xuen_pkg/__init__.py") == "X = 'v3'\n"
