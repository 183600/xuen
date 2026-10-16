"""round_guard 的单元测试 + 本地 git 全流程集成测试。

集成测试在临时目录里搭一个「工作仓库 + bare origin」，把 round_guard.py
拷进去当真实子进程跑，覆盖：基线化 / 晋升 / 拒绝（保护最佳）/ 无改动心跳 /
用户裁决回滚 / 最佳状态未知时的 worktree 补验证。
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
    })
    return e


def run(cmd, cwd):
    p = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True,
                       text=True, env=git_env(), timeout=120)
    assert p.returncode == 0, f"{cmd} 失败: {p.stderr}\n{p.stdout}"
    return p


def guard_run(repo: Path, *args):
    return subprocess.run(
        [sys.executable, str(repo / ".github" / "scripts" / "round_guard.py"), *args],
        cwd=str(repo), capture_output=True, text=True, env=git_env(), timeout=600,
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
