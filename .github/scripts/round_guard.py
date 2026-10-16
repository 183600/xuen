#!/usr/bin/env python3
"""round_guard.py —— Continuous Loop 的"轮次守卫"。

解决的问题：opencode 循环每轮把改动直接提交到 master，下一轮无条件在上一轮的
结果上继续。如果某轮把东西改坏，坏状态会成为后续所有轮次的起点，更好的方案
就被直接覆盖了。

机制（详见 .rounds/README.md）：
  1. 每轮保存快照   —— 改动提交为 snap/<时间>-r<轮次> 标签并立即推送，永不丢失；
  2. 候选 ≠ 最佳    —— master 只放"当前最佳"；候选只活在快照标签与 .rounds 记录里；
  3. 自动验证       —— 有测试就跑（pytest / make test / npm test / go test，
     再加 Python 编译检查 + CLI 冒烟 + 包导入冒烟）：
       - 候选通过           -> 晋升为新的最佳（master 前进）
       - 候选失败、最佳通过 -> 拒绝候选、保留最佳，下一轮从最佳重新出发
       - 无法自动验证       -> 记为"等待评分"，由用户裁决
  4. 用户评分       —— 在 .rounds/verdicts.txt 写 `snap/<id>: 8`（>=7 采纳）
     或 accept / reject；采纳旧快照即回滚到该方案。

子命令：
  init                       job 开始：同步远端、处理用户评分、必要时建立基线
  after-round --iter N       每轮结束：快照 -> 验证 -> 裁决 -> 晋升/保留最佳
  validate                   对当前工作树跑一遍自动验证（调试用）
  show                       打印当前状态（调试用）

设计原则：
  - guard 的任何失败都不能打断循环：工作流里全部以 `|| warning` 方式调用；
    最坏情况退化为旧行为（改动留在工作区，下一轮合并成更大的候选再验证）。
  - 只用 Python 标准库；所有输出 UTF-8；不打印 ANSI 颜色。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # .github/scripts/round_guard.py
ROUNDS = REPO / ".rounds"
STATE_FILE = ROUNDS / "state.json"
VERDICTS_FILE = ROUNDS / "verdicts.txt"
PROCESSED_FILE = ROUNDS / "verdicts.processed.txt"
REVIEW_FILE = ROUNDS / "review.md"
PENDING_DIR = ROUNDS / "pending"

PROTECTED_DIRS = (".github", ".rounds")             # AI 不许改、每轮回滚
PROMOTE_SCORE_DEFAULT = 7                           # 用户评分 >= 此值采纳
KEEP_ROUNDS = 120                                   # state.json 里保留的轮次记录数
KEEP_PENDING_DOCS = 30                              # pending/ 下保留的评审文档数
TEST_TIMEOUT = 900                                  # 单条验证命令超时（秒）
GIT_RETRY_SLEEP = 20

VERDICTS_HEADER = """\
# 候选评分表（用户填写；round_guard 只读取、从不改写此文件）
#
# 每行一条，格式：  snap/<快照ID>: accept | reject | 1-10 的整数
#   - 分数 >= 7 ：自动采纳为最佳（promote_score 可在 state.json 调整）
#   - accept / reject ：直接裁决
#   - 采纳一个旧快照 = 把仓库回滚到该方案（保留全部历史与其它快照）
#
# 快照清单与裁决进度见 .rounds/review.md；每条候选的改动详情见 .rounds/pending/。
# 已处理的条目会归档到 .rounds/verdicts.processed.txt，此文件里可以删掉已处理行。
#
# 示例（去掉行首 # 号即生效）：
#   snap/20261016-061234-r3: 8
#   snap/20261016-070001-r4: reject
"""


# ---------------------------------------------------------------- 基础工具

def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def round_id(iteration) -> str:
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-r{iteration}"


def log(msg: str) -> None:
    print(f"[guard] {msg}", flush=True)


def sh(cmd, cwd=REPO, timeout=None, env=None):
    """运行子进程，返回 CompletedProcess（不抛异常，调用方查 returncode）。"""
    return subprocess.run(
        [str(c) for c in cmd], cwd=str(cwd), capture_output=True, text=True,
        errors="replace", timeout=timeout, env=env,
    )


def git(*args, check=True, retry=0, timeout=300, cwd=REPO):
    """运行 git 命令；retry>0 时失败重试（用于网络命令）。"""
    p = None
    for attempt in range(max(retry, 0) + 1):
        try:
            p = sh(["git", *args], cwd=cwd, timeout=timeout)
        except subprocess.TimeoutExpired:
            p = None
        if p is not None and p.returncode == 0:
            return p
        if check is False:
            return p
        if attempt < retry:
            time.sleep(GIT_RETRY_SLEEP)
    if p is None:
        raise RuntimeError(f"git {' '.join(args)} 执行超时")
    raise RuntimeError(
        f"git {' '.join(args)} 失败(码 {p.returncode}): "
        f"{(p.stderr or p.stdout).strip()[:400]}"
    )


def gout(*args, **kw) -> str:
    return git(*args, **kw).stdout.strip()


def fetch(check=False) -> None:
    git("fetch", "origin", "--tags", check=check, retry=2, timeout=180)


def is_ancestor(a: str, b: str) -> bool:
    return git("merge-base", "--is-ancestor", a, b, check=False).returncode == 0


def rev_exists(rev: str) -> bool:
    return git("rev-parse", "-q", "--verify", rev + "^{commit}",
               check=False).returncode == 0


def origin_master_sha() -> str:
    return gout("rev-parse", "origin/master")


# ---------------------------------------------------------------- 状态文件

def default_state() -> dict:
    return {
        "version": 1,
        "best": None,
        "promote_score": PROMOTE_SCORE_DEFAULT,
        "unsynced_tags": [],
        "notes": [],
        "rounds": [],
    }


def load_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:  # 状态损坏不致命：当作没有状态，走基线化
        log(f"state.json 解析失败，将重建基线：{e}")
        return None
    st.setdefault("promote_score", PROMOTE_SCORE_DEFAULT)
    st.setdefault("unsynced_tags", [])
    st.setdefault("notes", [])
    st.setdefault("rounds", [])
    st.setdefault("best", None)
    return st


def save_state(st: dict) -> None:
    ROUNDS.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def upsert_round(st: dict, rec: dict) -> None:
    for i, r in enumerate(st["rounds"]):
        if r.get("id") == rec.get("id"):
            st["rounds"][i] = rec
            break
    else:
        st["rounds"].append(rec)
    if len(st["rounds"]) > KEEP_ROUNDS:
        st["rounds"] = st["rounds"][-KEEP_ROUNDS:]


def add_note(st: dict, msg: str) -> None:
    st["notes"].append({"at": now_iso(), "msg": msg[:300]})
    if len(st["notes"]) > 30:
        st["notes"] = st["notes"][-30:]


def ensure_verdicts_file() -> None:
    if not VERDICTS_FILE.exists():
        ROUNDS.mkdir(parents=True, exist_ok=True)
        VERDICTS_FILE.write_text(VERDICTS_HEADER, encoding="utf-8")
        log("已创建 .rounds/verdicts.txt 评分模板")


# ---------------------------------------------------------------- 用户裁决

_VERDICT_RE = re.compile(
    r"^\s*(snap/[A-Za-z0-9._/-]+)\s*:\s*(accept|reject|\d{1,2})\s*(?:#.*)?$"
)


def parse_verdicts(text: str):
    """解析 verdicts.txt -> [(snap, verdict, 原始行)]；verdict 为 'accept'/'reject'/整数。"""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        m = _VERDICT_RE.match(ln)
        if not m:
            out.append((None, None, ln))
            continue
        v = m.group(2)
        out.append((m.group(1), int(v) if v.isdigit() else v, ln))
    return out


def load_processed() -> set:
    done = set()
    if PROCESSED_FILE.exists():
        for ln in PROCESSED_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\S+\s+(snap/\S+)\s+\S+", ln)
            if m:
                done.add(m.group(1))
    return done


def append_processed(entries) -> None:
    lines = []
    for snap, result in entries:
        lines.append(f"{now_iso()}  {snap}  {result}")
    if lines:
        with PROCESSED_FILE.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- 自动验证

def detect_packages(root: Path):
    names = []
    pp = Path(root) / "pyproject.toml"
    if pp.exists():
        m = re.search(r"packages\s*=\s*\[(.*?)\]", pp.read_text(errors="replace"), re.S)
        if m:
            names = re.findall(r"[\"']([^\"']+)[\"']", m.group(1))
    if not names:
        root = Path(root)
        names = [
            d.name for d in root.iterdir()
            if d.is_dir() and (d / "__init__.py").exists()
            and not d.name.startswith(".")
        ]
    return [n for n in names if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", n or "")]


def detect_test_commands(root) -> list:
    """按优先级探测可用的自动验证命令（适用于本仓库，也尽量兼顾通用项目）。"""
    root = Path(root)
    cmds = []

    def _py(p: Path) -> bool:
        return not any(s in p.parts for s in (".git", ".rounds"))

    test_files = [p for p in root.rglob("test_*.py") if _py(p)]
    test_files += [p for p in root.rglob("*_test.py") if _py(p)]
    if test_files:
        cmds.append(["python3", "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"])

    mk = root / "Makefile"
    if mk.exists() and re.search(r"(?m)^test[^\n]*:", mk.read_text(errors="replace")):
        cmds.append(["make", "test"])

    pj = root / "package.json"
    if pj.exists():
        try:
            if "test" in json.loads(pj.read_text(errors="replace")).get("scripts", {}):
                cmds.append(["npm", "test", "--silent"])
        except Exception:
            pass

    if (root / "go.mod").exists():
        cmds.append(["go", "test", "./..."])

    if any(_py(p) for p in root.rglob("*.py")):
        cmds.append(["python3", "-m", "compileall", "-q", "."])

    if (root / "main.py").exists():
        cmds.append(["python3", "main.py", "--help"])

    pkgs = detect_packages(root)
    if pkgs:
        cmds.append(["python3", "-c", "import " + ", ".join(pkgs)])

    return cmds


def run_validation(root) -> dict:
    """在 root 上运行全部探测到的验证命令。

    返回 {status: pass|fail|none, commands: [...], log: str}
    - pass：至少一条命令运行且全部成功
    - fail：任一命令运行失败（含超时）
    - none：一条命令都没能运行（无法自动验证）
    """
    root = Path(root)
    cmds = detect_test_commands(root)
    ran, status, logs = [], "none", []
    for c in cmds:
        label = " ".join(str(x) for x in c)
        try:
            p = sh(c, cwd=root, timeout=TEST_TIMEOUT)
        except subprocess.TimeoutExpired:
            ran.append(label)
            status = "fail"
            logs.append(f"$ {label}\n[超时 {TEST_TIMEOUT}s]")
            continue
        except Exception as e:
            logs.append(f"$ {label}\n[无法执行: {e}]")
            continue
        ran.append(label)
        tail = ((p.stdout or "") + (p.stderr or ""))[-1500:]
        logs.append(f"$ {label} (退出码 {p.returncode})\n{tail.strip()}")
        if p.returncode != 0:
            status = "fail"
        elif status == "none":
            status = "pass"
    return {"status": status, "commands": ran, "log": "\n\n".join(logs)}


def validate_ref(ref: str) -> dict:
    """在临时 worktree 里验证某个提交（用于给"当前最佳"补基线）。"""
    tmp = Path(tempfile.mkdtemp(prefix="rg_val_"))
    wt = tmp / "wt"
    try:
        git("worktree", "add", "--detach", str(wt), ref, check=True)
        return run_validation(wt)
    finally:
        git("worktree", "remove", "--force", str(wt), check=False)
        git("worktree", "prune", check=False)
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 裁决矩阵

def decide(cand: str, best: str):
    """cand/best 属于 {pass, fail, none, unknown} -> (verdict, reason)。

    verdict（决策动作）：
      promote      晋升候选为新的最佳
      reject       拒绝候选、保留最佳（候选仍以快照保留，用户可翻案）
      pending_user 无法自动验证，等待用户评分
    """
    if cand == "none":
        return "pending_user", "没有可运行的自动验证手段，等待用户评分"
    if cand == "pass":
        if best == "pass":
            return ("promote",
                    "候选通过全部测试（最佳也通过）：按轮次推进为新的最佳；"
                    "如认为不如旧方案，可在 verdicts.txt 采纳旧快照回滚")
        if best == "fail":
            return "promote", "候选通过全部测试，而当前最佳未通过：采纳候选为最佳"
        return "promote", "候选通过全部测试：采纳为最佳（原最佳状态未知/无测试）"
    # cand == "fail"
    if best == "pass":
        return ("reject",
                "候选测试失败而当前最佳通过：保留最佳，候选仅存为快照；"
                "如认可候选可在 verdicts.txt 评分翻案")
    return ("reject",
            "候选测试失败（最佳未通过或状态未知）：不采纳候选，保留最佳；"
            "如认可候选可在 verdicts.txt 评分翻案")


# ---------------------------------------------------------------- git 轮次操作

def restore_protected() -> None:
    """回滚 AI 对受保护目录的改动（.github 保护循环自身，.rounds 保护轮次状态）。"""
    for d in PROTECTED_DIRS:
        if (REPO / d).exists():
            git("checkout", "HEAD", "--", d, check=False)
    git("clean", "-fdq", *PROTECTED_DIRS, check=False)


def candidate_exists() -> bool:
    if git("status", "--porcelain").stdout.strip():
        return True
    p = git("rev-list", "origin/master..HEAD", check=False)
    return bool(p.stdout.strip())


def push_tags(tags, st: dict):
    ok, failed = [], []
    for t in tags:
        p = git("push", "origin", f"refs/tags/{t}", check=False, retry=2, timeout=180)
        (ok if p.returncode == 0 else failed).append(t)
    if failed:
        log(f"::warning::快照标签推送失败，稍后自动补推: {failed}")
    known = set(st.get("unsynced_tags", []))
    known.difference_update(ok)
    known.update(failed)
    st["unsynced_tags"] = sorted(known)
    return ok, failed


def push_unsynced_tags(st: dict) -> None:
    todo = list(st.get("unsynced_tags", []))
    if todo:
        log(f"补推之前未同步的快照标签: {todo}")
        push_tags(todo, st)


def write_state_and_docs(st: dict) -> None:
    """把内存态写入 .rounds/（state.json、review.md）。调用方负责随后提交。"""
    ROUNDS.mkdir(parents=True, exist_ok=True)
    save_state(st)
    write_review(st)


def commit_rounds_files(message: str) -> None:
    git("add", "-A", ".rounds", check=False)
    git("commit", "-m", message, check=False)


def push_master_with_recovery() -> bool:
    """把当前 HEAD 推到 master；远端有新提交时先合并（.rounds 冲突取本地）。"""
    fetch()
    om = origin_master_sha()
    if is_ancestor(om, "HEAD"):
        return git("push", "origin", "HEAD:refs/heads/master",
                   check=False, retry=3, timeout=180).returncode == 0
    p = git("merge", "origin/master",
            "-m", "chore(rounds): 晋升前合并远端 master", check=False)
    if p.returncode != 0:
        conflicts = git("diff", "--name-only", "--diff-filter=U").stdout.split()
        non_rounds = [c for c in conflicts if not c.startswith(".rounds/")]
        if non_rounds:
            git("merge", "--abort", check=False)
            log(f"::warning::与远端 master 的代码冲突无法自动合并: {non_rounds}")
            return False
        for c in conflicts:
            git("checkout", "--ours", c, check=False)
            git("add", c, check=False)
        git("commit", "--no-edit", check=False)
    return git("push", "origin", "HEAD:refs/heads/master",
               check=False, retry=3, timeout=180).returncode == 0


def meta_record(st: dict, message: str) -> bool:
    """把 .rounds 状态更新提交到远端 master 顶端（不动代码内容），并把本地切回最佳。

    适用于：拒绝/待评分/无改动轮次的记录，以及处理完用户评分后的落盘。
    """
    fetch()
    if git("checkout", "-B", "rounds-meta", "origin/master", check=False).returncode != 0:
        git("checkout", "master", check=False)
        git("reset", "--hard", "origin/master", check=False)
        git("checkout", "-B", "rounds-meta", "master", check=False)

    def _attempt(msg: str) -> bool:
        write_state_and_docs(st)
        commit_rounds_files(msg)
        return git("push", "origin", "rounds-meta:refs/heads/master",
                   check=False, retry=3, timeout=180).returncode == 0

    ok = _attempt(message)
    if not ok:  # 远端又动了：以最新 origin/master 为底重放一次
        fetch()
        git("checkout", "-B", "rounds-meta", "origin/master", check=False)
        ok = _attempt(message)
        if not ok:
            log(f"::warning::状态记录暂时推不上去（{message}），下轮自动补")
    fetch()
    git("checkout", "-B", "master", "origin/master", check=False)
    git("branch", "-D", "rounds-meta", check=False)
    return ok


def promote_snap(st: dict, snap: str) -> tuple:
    """把某个快照设为最佳内容。

    - 快照在 master 前方：快进推送；
    - 快照落后/分叉（回滚场景）：用 commit-tree 造一个"内容=快照、父亲=当前 master"
      的新提交再推送——历史永远向前，不重写、不强推。
    返回 (ok, new_best_sha)。
    """
    if not rev_exists(snap):
        return False, None
    sha = gout("rev-parse", f"{snap}^{{commit}}")
    fetch()
    om = origin_master_sha()
    if is_ancestor(om, sha) and om != sha:
        p = git("push", "origin", f"{sha}:refs/heads/master",
                check=False, retry=3, timeout=180)
        if p.returncode == 0:
            return True, sha
        return False, None
    if om == sha:  # 已经是最佳内容
        return True, sha
    # 回滚 / 分叉：内容取快照，父提交取当前 master
    new = gout("commit-tree", f"{sha}^{{tree}}", "-p", om,
               "-m", f"chore(rounds): 采纳 {snap} 为最佳（用户裁决，内容回滚到该快照）")
    p = git("push", "origin", f"{new}:refs/heads/master",
            check=False, retry=3, timeout=180)
    return (p.returncode == 0, new if p.returncode == 0 else None)


def process_verdicts(st: dict) -> None:
    """处理 verdicts.txt 里尚未处理过的用户裁决。"""
    if not VERDICTS_FILE.exists():
        return
    saved_verdicts_text = VERDICTS_FILE.read_text(encoding="utf-8")
    processed = load_processed()
    entries = [(s, v) for (s, v, _raw) in parse_verdicts(saved_verdicts_text) if s]
    todo = [(s, v) for (s, v) in entries if s not in processed]
    bad = [raw for (s, _v, raw) in parse_verdicts(saved_verdicts_text) if s is None]
    if bad:
        add_note(st, "verdicts.txt 中有无法解析的行：" + " | ".join(bad[:3]))
    if not todo:
        return
    threshold = st.get("promote_score", PROMOTE_SCORE_DEFAULT)
    results = []
    for snap, v in todo:
        if not rev_exists(snap):
            add_note(st, f"verdicts.txt 引用了不存在的快照: {snap}")
            continue
        accept = (v == "accept") or (isinstance(v, int) and v >= threshold)
        if not accept:
            _mark_user_rejected(st, snap)
            results.append((snap, f"reject(v={v})"))
            continue
        ok, new_sha = promote_snap(st, snap)
        if ok and new_sha:
            tests = None
            for r in st["rounds"]:
                if r.get("snap") == snap:
                    tests = r.get("auto", {}).get("status")
                    break
            st["best"] = {"snap": snap, "sha": new_sha, "tests": tests,
                          "at": now_iso(), "by": "user"}
            _record_round(st, {
                "id": snap[len("snap/"):], "snap": snap, "sha": new_sha,
                "ts": now_iso(), "iter": None, "changed": None,
                "auto": {"status": tests or "unknown", "verdict": "promoted",
                         "reason": f"用户裁决采纳（v={v}）"},
                "verdict": "promoted", "by": "user",
            })
            results.append((snap, f"accept(v={v})"))
        else:
            add_note(st, f"采纳 {snap} 推送失败（冲突或网络），未生效")
            results.append((snap, f"FAILED(v={v})"))
    if results:
        append_processed(results)
        # 推送 master 内容可能回滚了 .rounds 里的用户文件，先恢复再落盘
        fetch()
        git("checkout", "-B", "master", "origin/master", check=False)
        VERDICTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        VERDICTS_FILE.write_text(saved_verdicts_text, encoding="utf-8")
        write_state_and_docs(st)
        meta_record(st, f"chore(rounds): 处理用户裁决 "
                        + ", ".join(f"{s}->{r}" for s, r in results))
        log(f"用户裁决已处理: {results}")


def _mark_user_rejected(st: dict, snap: str) -> None:
    for r in st["rounds"]:
        if r.get("snap") == snap:
            r["verdict"] = "rejected"
            r["by"] = "user"
            r["auto"] = r.get("auto") or {}
            r["auto"]["verdict"] = "rejected"
            return
    _record_round(st, {
        "id": snap[len("snap/"):], "snap": snap, "sha": None, "ts": now_iso(),
        "iter": None, "changed": None,
        "auto": {"status": "unknown", "verdict": "rejected",
                 "reason": "用户裁决拒绝"},
        "verdict": "rejected", "by": "user",
    })


def _record_round(st: dict, rec: dict) -> None:
    upsert_round(st, rec)


# ---------------------------------------------------------------- 报告

def _best_line(st: dict) -> str:
    b = st.get("best")
    if not b:
        return "（尚未建立基线）"
    tests = b.get("tests") or "unknown"
    return (f"`{b.get('snap')}`（测试: {tests}，{b.get('at', '?')} 由 "
            f"{b.get('by', '?')} 确立）")


VERDICT_LABEL = {
    "promoted": "已采纳为最佳",
    "rejected": "已拒绝（保留最佳）",
    "pending_user": "等待用户评分",
    "noop": "无改动",
}

# decide() 的动作 -> 轮次记录里的过去时裁决
VERDICT_PAST = {"promote": "promoted", "reject": "rejected"}


def write_review(st: dict) -> None:
    lines = [
        "# 轮次结果总览（round_guard 自动维护）",
        "",
        f"- 当前最佳：{_best_line(st)}",
        "- 候选快照：`snap/<时间>-r<轮次>` 标签，`git ls-remote --tags origin 'snap/*'` 查看全部",
        "- 评分方法：编辑 `.rounds/verdicts.txt`，写 `snap/<id>: 8`（1-10 分，"
        f">={st.get('promote_score', PROMOTE_SCORE_DEFAULT)} 采纳）或 `accept` / `reject`",
        "- 各候选改动详情：`.rounds/pending/<id>.md`",
        "",
        "| 快照 | 时间(UTC) | 轮次 | 改动文件 | 自动验证 | 裁决 | 说明 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in reversed(st["rounds"][-40:]):
        snap = r.get("snap") or "-"
        when = (r.get("ts") or "?").replace("T", " ").replace("Z", "")
        it = r.get("iter") if r.get("iter") is not None else "-"
        changed = r.get("changed")
        changed = "-" if changed is None else str(changed)
        status = (r.get("auto") or {}).get("status", "unknown")
        verdict = r.get("verdict", "?")
        label = VERDICT_LABEL.get(verdict, verdict)
        if r.get("by") == "user":
            label += "（用户）"
        reason = ((r.get("auto") or {}).get("reason") or "").replace("|", "\\|")
        if r.get("touched_tests"):
            reason = "[本轮改动了测试文件] " + reason
        lines.append(f"| `{snap}` | {when} | {it} | {changed} | {status} "
                     f"| {label} | {reason} |")
    if st.get("notes"):
        lines += ["", "## 备注", ""]
        for n in st["notes"][-10:]:
            lines.append(f"- {n.get('at', '')} {n.get('msg', '')}")
    lines.append("")
    REVIEW_FILE.write_text("\n".join(lines), encoding="utf-8")


def write_pending_doc(rid, snap, base_sha, cand_sha, val, verdict, reason,
                      touched) -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    stat = gout("diff", "--stat", base_sha, cand_sha)
    diff = git("diff", base_sha, cand_sha).stdout or ""
    diff_lines = diff.splitlines()
    if len(diff_lines) > 4000:
        diff = "\n".join(diff_lines[:4000]) + f"\n\n...（共 {len(diff_lines)} 行，已截断）"
    head = [
        f"# 候选快照 `{snap}`",
        "",
        f"- 轮次：{rid}",
        f"- 验证：{val.get('status', 'unknown')}；裁决：{verdict}",
        f"- 理由：{reason}",
        f"- base `{base_sha[:10]}` -> candidate `{cand_sha[:10]}`",
    ]
    if touched:
        head.append(f"- **注意：本轮改动了测试文件**（{', '.join(touched[:8])}）")
    if verdict == "pending_user":
        head += ["", f"## 如何评分", "",
                 f"在 `.rounds/verdicts.txt` 增加一行（去掉注释直接生效）：", "",
                 f"    {snap}: 8", "",
                 f"分数 1-10，>= 7 采纳为最佳；也可写 `accept` / `reject`。"]
    head += ["", "## 验证日志", "", "```", (val.get("log") or "").strip()[-4000:], "```",
             "", "## diff --stat", "", "```", stat, "```",
             "", "## diff", "", "```diff", diff, "```", ""]
    (PENDING_DIR / f"{rid}.md").write_text("\n".join(head), encoding="utf-8")
    docs = sorted(PENDING_DIR.glob("*.md"))
    for old in docs[:-KEEP_PENDING_DOCS] if len(docs) > KEEP_PENDING_DOCS else []:
        old.unlink()


# ---------------------------------------------------------------- 基线化

def bootstrap_state() -> dict:
    """首次运行：把当前 master 固化为基线最佳（打快照标签 + 跑基线验证）。"""
    st = default_state()
    sha = gout("rev-parse", "HEAD")
    snap = "snap/baseline-" + _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    git("tag", snap, sha)
    push_tags([snap], st)
    log(f"建立基线：{snap}，开始基线验证（可能需要几分钟）...")
    val = run_validation(REPO)
    st["best"] = {"snap": snap, "sha": sha, "tests": val["status"],
                  "at": now_iso(), "by": "baseline"}
    _record_round(st, {
        "id": snap[len("snap/"):], "snap": snap, "sha": sha, "ts": now_iso(),
        "iter": 0, "changed": 0,
        "auto": {"status": val["status"], "verdict": "promoted",
                 "reason": "基线化：迁移到轮次守卫时的初始最佳"},
        "verdict": "promoted", "by": "baseline",
    })
    log(f"基线验证结果：{val['status']}")
    write_state_and_docs(st)
    commit_rounds_files(f"chore(rounds): 建立基线最佳 {snap}（测试: {val['status']}）")
    if not push_master_with_recovery():
        log("::warning::基线状态推送失败，下一轮自动补推")
    return st


def load_or_bootstrap() -> dict:
    st = load_state()
    if st is None:
        st = bootstrap_state()
    return st


# ---------------------------------------------------------------- 子命令

def cmd_init(args) -> int:
    fetch()
    git("checkout", "-B", "master", "origin/master", check=False)
    ensure_verdicts_file()
    st = load_or_bootstrap()
    push_unsynced_tags(st)
    process_verdicts(st)
    log(f"init 完成：最佳={_best_line(st)}；待评分轮数="
        f"{sum(1 for r in st['rounds'] if r.get('verdict') == 'pending_user')}")
    return 0


def cmd_after_round(args) -> int:
    iteration = args.iter
    st = load_or_bootstrap()

    fetch()
    push_unsynced_tags(st)

    base_sha = gout("rev-parse", "HEAD")
    restore_protected()

    rid = round_id(iteration)
    snap = f"snap/{rid}"

    # ---- 无改动：只记心跳 ----
    if not candidate_exists():
        _record_round(st, {
            "id": rid, "snap": None, "sha": base_sha, "ts": now_iso(),
            "iter": iteration, "changed": 0,
            "auto": {"status": "none", "verdict": "noop", "reason": "本轮无改动"},
            "verdict": "noop", "by": "auto",
        })
        meta_record(st, f"chore(rounds): {rid} 无改动（心跳）")
        log(f"{rid}：无改动")
        process_verdicts(st)
        return 0

    # ---- 1) 候选快照：提交 + 打标签 + 立即推送（先保住这轮的产物） ----
    if git("status", "--porcelain").stdout.strip():
        git("add", "-A")
        git("commit", "-m",
            f"cand({iteration}): 候选快照 {rid}（尚未验证，不代表最佳）", check=False)
    cand_sha = gout("rev-parse", "HEAD")
    git("tag", snap, cand_sha)
    push_tags([snap], st)
    # diff 基准取候选线与 origin/master 的分叉点：
    # 既覆盖「AI 自己 commit 的多跳改动」，也排除「轮次期间用户推到 master 的新提交」
    try:
        diff_base = gout("merge-base", "origin/master", cand_sha) or base_sha
    except Exception:
        diff_base = base_sha
    changed = [f for f in git("diff", "--name-only", diff_base, cand_sha).stdout.split()
               if f.strip()]
    touched_tests = [f for f in changed if f.startswith("tests/")]
    log(f"{rid}：候选 {snap} 已保存（{len(changed)} 个文件改动）")

    # ---- 2) 自动验证候选 ----
    log(f"{rid}：开始自动验证（{len(detect_test_commands(REPO))} 组命令）...")
    cand_val = run_validation(REPO)
    log(f"{rid}：候选验证 = {cand_val['status']}")

    # ---- 3) 需要时给"当前最佳"补一次基线验证（只补一次，结果缓存在 state） ----
    best = st.get("best")
    best_status = (best or {}).get("tests")
    if cand_val["status"] != "none" and best_status not in ("pass", "fail", "none"):
        bsha = (best or {}).get("sha")
        if not bsha or not rev_exists(bsha):
            bsha = origin_master_sha()
        try:
            log(f"{rid}：当前最佳状态未知，在 {bsha[:10]} 上补基线验证...")
            bval = validate_ref(bsha)
            best_status = bval["status"]
            st["best"] = {**(best or {}), "sha": bsha, "tests": best_status,
                          "validated_at": now_iso()}
            log(f"{rid}：最佳基线验证 = {best_status}")
        except Exception as e:
            best_status = "unknown"
            add_note(st, f"最佳基线验证失败：{e}")

    # ---- 4) 裁决 ----
    verdict, reason = decide(cand_val["status"], best_status or "unknown")
    past = VERDICT_PAST.get(verdict, verdict)   # 记录用过去时：promoted/rejected
    log(f"{rid}：裁决 = {past}（{reason}）")

    rec = {
        "id": rid, "snap": snap, "sha": cand_sha, "ts": now_iso(),
        "iter": iteration, "changed": len(changed),
        "touched_tests": bool(touched_tests),
        "auto": {"status": cand_val["status"], "verdict": past, "reason": reason},
        "verdict": past, "by": "auto",
    }

    if verdict == "promote":
        _record_round(st, rec)
        st["best"] = {"snap": snap, "sha": cand_sha, "tests": cand_val["status"],
                      "at": now_iso(), "by": "auto", "iter": iteration}
        write_state_and_docs(st)
        write_pending_doc(rid, snap, diff_base, cand_sha, cand_val, past,
                          reason, touched_tests)
        commit_rounds_files(f"chore(rounds): {rid} 通过验证（{cand_val['status']}），"
                            f"晋升为最佳")
        if push_master_with_recovery():
            log(f"{rid}：已晋升为最佳并推送")
        else:
            # 与远端代码冲突：降级为待人工处理，本地回到远端最佳
            rec["verdict"] = "pending_user"
            rec["auto"]["verdict"] = "pending_user"
            rec["auto"]["reason"] = "晋升推送与远端 master 冲突，等待人工处理"
            upsert_round(st, rec)
            add_note(st, f"{rid} 晋升推送与远端冲突，已降级为待评分")
            meta_record(st, f"chore(rounds): {rid} 晋升冲突，转为待评分")
    else:
        _record_round(st, rec)
        write_review(st)
        write_pending_doc(rid, snap, diff_base, cand_sha, cand_val, past,
                          reason, touched_tests)
        meta_record(st, f"chore(rounds): {rid} {past}"
                          f"（候选验证: {cand_val['status']}，最佳: {best_status}）")
        log(f"{rid}：候选保留为快照，master 维持最佳；工作区已回到最佳")

    # ---- 5) 顺带处理用户评分（用户可在任意时刻翻案/回滚） ----
    process_verdicts(st)
    return 0


def cmd_validate(args) -> int:
    val = run_validation(REPO)
    print(json.dumps(val, ensure_ascii=False, indent=2))
    return 0 if val["status"] in ("pass", "none") else 1


def cmd_show(args) -> int:
    st = load_state()
    if st is None:
        print("（无 state.json——尚未基线化）")
        return 0
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="round_guard.py",
                                 description="Continuous Loop 轮次守卫")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="job 开始：同步远端、处理用户评分、建立基线")

    p2 = sub.add_parser("after-round", help="每轮结束：快照/验证/裁决/晋升")
    p2.add_argument("--iter", required=True,
                    help="轮次编号（工作流里的 ITER，或 final）")

    sub.add_parser("validate", help="对当前工作树跑自动验证")
    sub.add_parser("show", help="打印当前状态")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "init":
            return cmd_init(args)
        if args.cmd == "after-round":
            return cmd_after_round(args)
        if args.cmd == "validate":
            return cmd_validate(args)
        if args.cmd == "show":
            return cmd_show(args)
    except Exception as e:
        log(f"::warning::round_guard 异常退出（不影响循环继续）：{e}")
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
