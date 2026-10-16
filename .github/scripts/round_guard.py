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
       - 无法自动验证       -> 交给 AI 评分（见 4），AI 不可用才等用户
  4. AI 评分        —— 代替人类给"测试无法裁决"的候选打分（1-10 分，
     >= 阈值采纳；渠道：OpenAI 兼容 API（AIJUDGE_API_KEY）或本机 opencode
     免费模型，CI 里零配置可用）：
       - 无法自动验证的候选   -> AI 打分决定采纳/拒绝
       - 测试通过但改动了测试文件的候选 -> AI 复核，防止"删/弱化测试凑通过"
       - review_promoted 开启时，所有测试通过的候选也做一次 AI 复核
       - AI 不可用/出错 -> 退回"等待用户评分"，绝不卡住循环
  5. 用户评分       —— 在 .rounds/verdicts.txt 写 `snap/<id>: 8`（>=7 采纳）
     或 accept / reject；采纳旧快照即回滚到该方案。用户裁决优先级最高，
     随时可翻测试或 AI 的案。

子命令：
  init                       job 开始：同步远端、处理用户评分、AI 补评分、建基线
  after-round --iter N       每轮结束：快照 -> 验证 -> （必要时）AI 评分 -> 晋升/保留
  ai-judge [--snap S]        手动触发 AI 评分（默认处理全部待评分轮次）
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
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
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

# ---- AI 评分（AI Judge）默认参数；可用 state.json 的 ai_judge 或环境变量覆盖
AI_OC_DEFAULT_MODEL = "opencode/deepseek-v4.1-flash-free"   # opencode 渠道默认模型
AI_OC_FALLBACK_MODEL = "opencode/big-pickle"                # 默认模型不可用时的兜底模型
AI_API_DEFAULT_MODEL = "gpt-4o-mini"                        # API 渠道默认模型
AI_API_DEFAULT_BASE = "https://api.openai.com/v1"           # OpenAI 兼容端点
AI_DEFAULT_TIMEOUT = 180                                    # 单次 AI 调用超时（秒）
AI_MAX_DIFF_CHARS = 100_000                                 # 评审材料里 diff 的字符上限
AI_MAX_BACKLOG = 3                                          # init 时最多补评分的轮数

def _model_tag() -> str:
    """提交信息附带本轮使用的模型（workflow 通过 ROUND_MODEL 环境变量传入）。"""
    m = os.environ.get("ROUND_MODEL", "").strip()
    return f" [model: {m}]" if m else ""


VERDICTS_HEADER = """\
# 候选评分表（用户填写；round_guard 只读取、从不改写此文件）
#
# 每行一条，格式：  snap/<快照ID>: accept | reject | 1-10 的整数
#   - 分数 >= 7 ：自动采纳为最佳（promote_score 可在 state.json 调整）
#   - accept / reject ：直接裁决
#   - 采纳一个旧快照 = 把仓库回滚到该方案（保留全部历史与其它快照）
#
# 说明：无法自动验证的候选默认会先由 AI 评审打分（代替人工，可在
# state.json 的 ai_judge 里停用）；你的裁决优先级最高，随时可以给任意
# 快照重新打分翻案——包括推翻 AI 或测试已经做出的结论。
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
        "ai_judge": {},                    # AI 评分配置（空 = 全用默认值）
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
    st.setdefault("ai_judge", {})
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
        # .github 是循环自身的代码，不作为"产品可验证性"的依据；
        # 排除后，纯文档/数据仓库才会真正进入"无法自动验证 -> AI 评分"路径
        return not any(s in p.parts for s in (".git", ".rounds", ".github"))

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
      pending_user 无法自动验证 -> 先交给 AI 评分（run_ai_judge），
                   AI 不可用才落到"等待用户评分"
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


# ---------------------------------------------------------------- AI 评分（AI Judge）
# 代替人类给候选打分。渠道按优先级：
#   1. OpenAI 兼容 API —— 配置了环境变量 AIJUDGE_API_KEY 时启用
#      （AIJUDGE_BASE_URL / AIJUDGE_API_MODEL 可选）
#   2. 本机 opencode CLI —— CI 循环本身就装了它，免费模型零配置可用
#      （AIJUDGE_OC_MODEL 可选，默认 deepseek-v4.1-flash-free）
# 评审在临时目录里进行（材料写成 judge_task.md），评审模型即使想改文件
# 也碰不到仓库；解析只认 SCORE/VERDICT/REASON 三个字段，拿不到就当失败，
# 绝不影响循环继续。

def ai_judge_config(st: dict | None) -> dict:
    """AI 评审配置：代码默认 <- state.json['ai_judge'] <- 环境变量（优先级最高）。"""
    st = st or {}
    cfg = {
        "enabled": True,            # 总开关（False = 完全回到纯人工评分）
        "min_score": None,          # 采纳阈值；None = 跟随 promote_score
        "review_promoted": False,   # True = 测试通过的候选也要过一遍 AI 复核
        "timeout": AI_DEFAULT_TIMEOUT,
        "max_diff_chars": AI_MAX_DIFF_CHARS,
        "max_backlog": AI_MAX_BACKLOG,
    }
    over = st.get("ai_judge") or {}
    for k in cfg:
        if over.get(k) is not None:
            cfg[k] = over[k]
    env = os.environ
    flag = env.get("AIJUDGE_ENABLED", "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        cfg["enabled"] = False
    elif flag in ("1", "true", "yes", "on"):
        cfg["enabled"] = True
    rp = env.get("AIJUDGE_REVIEW_PROMOTED", "").strip().lower()
    if rp in ("0", "false", "no", "off"):
        cfg["review_promoted"] = False
    elif rp in ("1", "true", "yes", "on"):
        cfg["review_promoted"] = True
    for k, envk in (("min_score", "AIJUDGE_MIN_SCORE"),
                    ("timeout", "AIJUDGE_TIMEOUT"),
                    ("max_diff_chars", "AIJUDGE_MAX_DIFF_CHARS"),
                    ("max_backlog", "AIJUDGE_MAX_BACKLOG")):
        v = env.get(envk, "").strip()
        if re.fullmatch(r"\d+", v):
            cfg[k] = int(v)
    return cfg


def ai_judge_threshold(cfg: dict, st: dict) -> int:
    return cfg.get("min_score") or st.get("promote_score", PROMOTE_SCORE_DEFAULT)


def ai_judge_available() -> bool:
    """是否有任何可用的 AI 评分渠道（API key 或本机 opencode）。"""
    if os.environ.get("AIJUDGE_API_KEY", "").strip():
        return True
    return shutil.which("opencode") is not None


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


# 各字段允许多种写法（中英文冒号、markdown 加粗、中文裁决词）；
# 同一字段出现多次时取最后一次（模型先复读格式说明再作答时，答案在后）
_AI_SCORE_RE = re.compile(r"(?im)^\s*[\*\s]*SCORE\s*[\*\s]*[:：]\s*(\d{1,3})")
_AI_VERDICT_RE = re.compile(
    r"(?im)^\s*[\*\s]*VERDICT\s*[\*\s]*[:：]\s*\**\s*(accept|reject|采纳|拒绝)")
_AI_REASON_RE = re.compile(r"(?im)^\s*[\*\s]*REASON\s*[\*\s]*[:：]\s*(.+)$")


def parse_ai_reply(text) -> dict | None:
    """解析 AI 评审输出 -> {score, verdict('accept'/'reject'), reason}。

    score 与 verdict 拿到任意一个即算有效；都没有返回 None。
    分数钳制到 1-10；显式 VERDICT 的决策优先级高于分数。
    """
    if not text:
        return None
    t = strip_ansi(text)
    score, verdict, reason = None, None, None
    ms = _AI_SCORE_RE.findall(t)
    if ms:
        try:
            score = max(1, min(10, int(ms[-1])))
        except ValueError:
            score = None
    mv = _AI_VERDICT_RE.findall(t)
    if mv:
        v = mv[-1].strip().strip("*").lower()
        verdict = "reject" if v in ("reject", "拒绝") else "accept"
    mr = _AI_REASON_RE.findall(t)
    if mr:
        reason = mr[-1].strip().strip("*").strip()[:200]
    if score is None and verdict is None:
        return None
    return {"score": score, "verdict": verdict, "reason": reason or ""}


JUDGE_PROMPT_TEMPLATE = """你是一名严格的代码评审员（AI Judge），负责代替人类给自动化循环产出的改动打分。

## 背景
- 一个自动化 AI 循环在仓库里持续工作，任务：判断仓库是否有 bug，有就修复。
- 每轮改动保存为候选快照；你的评分决定该候选是否替换"当前最佳"方案。
- 候选不会丢失（永远留档可翻案），但错误的高分会让坏方案覆盖好方案；
  拿不准时请保守打低分。
{touched}
## 评审材料

### 1) 改动文件清单
```
{files}
```

### 2) 改动统计（diff --stat）
```
{stat}
```

### 3) 完整 diff（base -> 候选）
```diff
{diff}
```

### 4) 自动验证情况
- 自动验证结果：{val_status}（none = 没有任何可运行的自动验证手段）
{val_log}
### 5) 仓库简介（README 前 60 行）
```
{readme}
```

## 评分标准（1-10 整数）
- 9-10  明显改进：修复了真实 bug、明显提升质量或健壮性，无风险
- 7-8   整体是改进，小瑕疵可以接受
- 5-6   中性改动：利弊参半、收益不确定
- 3-4   轻微退化、引入风险或收益存疑
- 1-2   明显破坏：引入 bug、删除功能、危险操作、或靠删改测试"凑通过"

## 输出格式（前三个字段必须严格按此格式单行输出，供机器解析；不要复读格式说明）
SCORE: <1-10 的整数>
VERDICT: accept 或 reject
REASON: <一句话理由>

（三个字段之后，你可以自由补充详细分析。）"""


def build_judge_prompt(diff_base, cand_sha, val, changed, touched_tests,
                       cfg) -> str:
    """组装评审提示词：diff + 验证情况 + 仓库简介 + 评分标准。"""
    stat = gout("diff", "--stat", diff_base, cand_sha)
    diff = git("diff", diff_base, cand_sha).stdout or ""
    cap = int(cfg.get("max_diff_chars") or AI_MAX_DIFF_CHARS)
    if len(diff) > cap:
        diff = diff[:cap] + f"\n...（diff 过长已截断：原文 {len(diff)} 字符）"
    readme = ""
    rp = REPO / "README.md"
    if rp.exists():
        readme = "\n".join(
            rp.read_text(encoding="utf-8", errors="replace").splitlines()[:60])
    files = "\n".join((changed or [])[:80]) or "（无法获取）"
    val_status = (val or {}).get("status") or "unknown"
    log_text = ((val or {}).get("log") or "").strip()
    val_log = ""
    if log_text:
        val_log = "- 验证日志（截断）：\n```\n" + log_text[-2500:] + "\n```\n"
    touched = ""
    if touched_tests:
        touched = ("\n- 特别注意：本轮改动包含 tests/ 下的测试文件。请重点评估这是"
                   "合理的新增/修正测试，还是通过删除或弱化测试来\"凑通过\""
                   "（后者请给 1-3 分）。\n")
    return JUDGE_PROMPT_TEMPLATE.format(
        touched=touched, files=files, stat=stat, diff=diff,
        val_status=val_status, val_log=val_log, readme=readme)


def _api_judge(prompt: str, cfg: dict):
    """OpenAI 兼容 /chat/completions。返回 (回复文本, 错误说明)。"""
    key = os.environ.get("AIJUDGE_API_KEY", "").strip()
    if not key:
        return None, "未配置 AIJUDGE_API_KEY"
    base = (os.environ.get("AIJUDGE_BASE_URL") or AI_API_DEFAULT_BASE).rstrip("/")
    model = (os.environ.get("AIJUDGE_API_MODEL") or AI_API_DEFAULT_MODEL).strip()
    body = json.dumps({
        "model": model, "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions", data=body, method="POST",
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return (data["choices"][0]["message"]["content"] or ""), None
    except Exception as e:
        return None, f"API({model}) 调用失败: {str(e)[:200]}"


def _opencode_model_pool() -> list:
    """`opencode models opencode` 的输出 -> 模型 id 列表（失败返回空）。"""
    try:
        p = sh(["opencode", "models", "opencode"], cwd=REPO, timeout=60)
    except Exception:
        return []
    if p.returncode != 0:
        return []
    return re.findall(r"(?m)^(opencode/[A-Za-z0-9][A-Za-z0-9._-]*)\s*$",
                      p.stdout)


def _opencode_judge(prompt: str, cfg: dict, model: str):
    """opencode CLI 评审：在临时目录里执行，评审模型碰不到仓库。"""
    tmpd = Path(tempfile.mkdtemp(prefix="rg_judge_"))
    try:
        (tmpd / "judge_task.md").write_text(prompt, encoding="utf-8")
        instruction = ("请阅读当前目录中的 judge_task.md 文件，严格按照文件里的"
                       "背景、评分标准与输出格式要求完成任务。直接输出要求的"
                       "SCORE/VERDICT/REASON 三个字段，用中文。"
                       "不要创建或修改任何文件。")
        try:
            p = sh(["opencode", "run", "-m", model, instruction],
                   cwd=tmpd, timeout=cfg["timeout"])
        except subprocess.TimeoutExpired:
            return None, f"opencode({model}) 超时(>{cfg['timeout']}s)"
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        if p.returncode != 0 and not parse_ai_reply(out):
            tail = strip_ansi(out).strip()[-300:]
            return None, f"opencode({model}) 退出码 {p.returncode}: {tail}"
        return out, None
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def _ai_result(provider: str, model: str, parsed: dict, threshold: int,
               result: dict) -> dict:
    final = parsed.get("verdict")
    if final not in ("accept", "reject"):
        s = parsed.get("score")
        final = None if s is None else ("accept" if s >= threshold else "reject")
    result.update({
        "ok": True, "provider": provider, "model": model,
        "score": parsed.get("score"), "verdict": parsed.get("verdict"),
        "final": final or "reject", "reason": parsed.get("reason") or "",
    })
    return result


def run_ai_judge(diff_base, cand_sha, val, changed, touched_tests, st) -> dict:
    """尝试用 AI 给候选打分（代替人类评分）。

    返回 {ok, score, verdict, final('accept'/'reject'), reason,
          provider, model, error}；ok=False 表示两个渠道都没给出可解析结论。
    """
    cfg = ai_judge_config(st)
    threshold = ai_judge_threshold(cfg, st)
    result = {"ok": False, "score": None, "verdict": None, "final": None,
              "reason": "", "provider": None, "model": None, "error": None}
    if not cfg["enabled"]:
        result["error"] = "AI 评分已在配置中停用"
        return result
    try:
        prompt = build_judge_prompt(diff_base, cand_sha, val, changed,
                                    touched_tests, cfg)
    except Exception as e:
        result["error"] = f"构造评审材料失败: {e}"
        return result

    errors = []
    # 渠道 1：OpenAI 兼容 API（配置了 AIJUDGE_API_KEY 才启用）
    if os.environ.get("AIJUDGE_API_KEY", "").strip():
        try:
            model = (os.environ.get("AIJUDGE_API_MODEL")
                     or AI_API_DEFAULT_MODEL).strip()
            text, err = _api_judge(prompt, cfg)
            parsed = parse_ai_reply(text) if text else None
            if parsed:
                return _ai_result("api", model, parsed, threshold, result)
            errors.append(err or "API 回复无法解析")
        except Exception as e:
            errors.append(f"API 渠道异常: {str(e)[:200]}")

    # 渠道 2：本机 opencode（CI 里免费模型可用，零配置）
    if shutil.which("opencode") is not None:
        try:
            preferred = (os.environ.get("AIJUDGE_OC_MODEL")
                         or AI_OC_DEFAULT_MODEL).strip()
            candidates = [preferred]
            # ⭐ 默认/指定模型不可用时优先换 big-pickle 兜底（同为 Zen 网关免费模型）
            if AI_OC_FALLBACK_MODEL not in candidates:
                candidates.append(AI_OC_FALLBACK_MODEL)
            for m in _opencode_model_pool():
                if m not in candidates:
                    candidates.append(m)
            for m in candidates[:2]:          # 最多试 2 个模型，控制耗时
                text, err = _opencode_judge(prompt, cfg, m)
                parsed = parse_ai_reply(text) if text else None
                if parsed:
                    return _ai_result("opencode", m, parsed, threshold, result)
                errors.append(err or f"opencode({m}) 回复无法解析")
        except Exception as e:
            errors.append(f"opencode 渠道异常: {str(e)[:200]}")

    result["error"] = "; ".join(e for e in errors if e) or "没有可用的 AI 评分渠道"
    return result


def _ai_record(res: dict) -> dict:
    """AI 评分结果 -> 存进轮次记录的精简形式。"""
    if res.get("ok"):
        return {"provider": res.get("provider"), "model": res.get("model"),
                "score": res.get("score"), "verdict": res.get("verdict"),
                "reason": (res.get("reason") or "")[:200], "at": now_iso()}
    return {"error": (res.get("error") or "")[:200], "at": now_iso()}


def process_pending_ai(st: dict, only_snap: str | None = None) -> None:
    """给积压的 pending_user 轮次补 AI 评分（用户裁决已处理过的不会再动）。

    在 init 与 `ai-judge` 子命令里调用；单次最多处理 max_backlog 条，
    防止一次性占用太多时间。
    """
    cfg = ai_judge_config(st)
    if not cfg.get("enabled"):
        return
    pend = [r for r in st["rounds"]
            if r.get("verdict") == "pending_user" and r.get("snap")]
    if only_snap:
        pend = [r for r in pend if r.get("snap") == only_snap]
    if not pend:
        return
    if not ai_judge_available():
        log(f"有 {len(pend)} 条待评分轮次，但无可用 AI 渠道，继续等待用户")
        return
    threshold = ai_judge_threshold(cfg, st)
    saved_verdicts = None
    if VERDICTS_FILE.exists():
        saved_verdicts = VERDICTS_FILE.read_text(encoding="utf-8")
    did = []
    for r in pend[:cfg["max_backlog"]]:
        snap = r.get("snap")
        sha = r.get("sha")
        if (not sha or not rev_exists(sha)) and not rev_exists(snap or ""):
            add_note(st, f"待评分轮次 {snap} 的提交不存在，跳过")
            continue
        if not sha or not rev_exists(sha):
            sha = gout("rev-parse", f"{snap}^{{commit}}")
            r["sha"] = sha
        diff_base = r.get("diff_base") or (sha + "^")
        try:
            changed = git("diff", "--name-only", diff_base, sha).stdout.split()
        except Exception:
            changed = []
        val = {"status": (r.get("auto") or {}).get("status", "unknown"),
               "log": ""}
        log(f"AI 补评分：{snap} ...")
        res = run_ai_judge(diff_base, sha, val, changed,
                           bool(r.get("touched_tests")), st)
        if not res["ok"]:
            add_note(st, f"AI 补评分失败 {snap}: {res['error']}")
            continue
        r["ai"] = _ai_record(res)
        sc = res["score"]
        sc_txt = f"{sc}分" if sc is not None else res["final"]
        if res["final"] == "accept":
            ok, new_sha = promote_snap(st, snap)
            if ok and new_sha:
                tests = (r.get("auto") or {}).get("status")
                st["best"] = {"snap": snap, "sha": new_sha, "tests": tests,
                              "at": now_iso(), "by": "ai"}
                r["verdict"] = "promoted"
                r["by"] = "ai"
                r["auto"] = r.get("auto") or {}
                r["auto"]["verdict"] = "promoted"
                r["auto"]["reason"] = (f"AI 评分 {sc_txt}："
                                       f"{res['reason'] or '评审通过'}")
                did.append(f"{snap}: promoted(AI {sc_txt})")
            else:
                add_note(st, f"AI 采纳 {snap} 推送失败，保留待评分")
                continue
        else:
            r["verdict"] = "rejected"
            r["by"] = "ai"
            r["auto"] = r.get("auto") or {}
            r["auto"]["verdict"] = "rejected"
            r["auto"]["reason"] = (f"AI 评分 {sc_txt}（阈值 {threshold}）："
                                   f"{res['reason'] or '评审未通过'}")
            did.append(f"{snap}: rejected(AI {sc_txt})")
    if did:
        # promote_snap 可能回滚了 .rounds 里的用户文件，先恢复再落盘
        fetch()
        git("checkout", "-B", "master", "origin/master", check=False)
        if saved_verdicts is not None:
            VERDICTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            VERDICTS_FILE.write_text(saved_verdicts, encoding="utf-8")
        write_state_and_docs(st)
        meta_record(st, "chore(rounds): AI 补评分 " + "; ".join(did))
        log(f"AI 补评分完成: {did}")


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
    git("commit", "-m", message + _model_tag(), check=False)


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
               "-m", f"chore(rounds): 采纳 {snap} 为最佳（用户裁决，内容回滚到该快照）"
                     f"{_model_tag()}")
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
        "- 裁决链：测试能验证的听测试；无法验证的先由 AI 评分（代替人工）；"
        "你的裁决优先级最高，可随时翻案",
        "- 人工/AI 评分：编辑 `.rounds/verdicts.txt`，写 `snap/<id>: 8`（1-10 分，"
        f">={st.get('promote_score', PROMOTE_SCORE_DEFAULT)} 采纳）或 `accept` / `reject`；"
        "AI 评分的阈值与开关可在 state.json 的 `ai_judge` 调整",
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
        elif r.get("by") == "ai":
            ai = r.get("ai") or {}
            s = ai.get("score")
            label += "（AI" + (f" {s}分" if s is not None else "") + "）"
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
                      touched, ai=None, by="auto") -> None:
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
        f"- 验证：{val.get('status', 'unknown')}；裁决：{verdict}（by {by}）",
        f"- 理由：{reason}",
        f"- base `{base_sha[:10]}` -> candidate `{cand_sha[:10]}`",
    ]
    if ai:
        if "error" in ai:
            head.append(f"- AI 评分：不可用（{ai['error']}）")
        else:
            sc = ai.get("score")
            sc_txt = "-" if sc is None else f"{sc} 分"
            head.append(f"- AI 评分：{sc_txt}（{ai.get('provider')}/"
                        f"{ai.get('model')}）：{ai.get('reason', '')}")
    if touched:
        head.append(f"- **注意：本轮改动了测试文件**（{', '.join(touched[:8])}）")
    if verdict == "pending_user":
        head += ["", f"## 如何评分", "",
                 "自动验证与 AI 评分都没能给出结论，等待你的裁决：", "",
                 f"在 `.rounds/verdicts.txt` 增加一行（去掉注释直接生效）：", "",
                 f"    {snap}: 8", "",
                 f"分数 1-10，>= {PROMOTE_SCORE_DEFAULT} 采纳为最佳；也可写 `accept` / `reject`。",
                 "你的裁决优先级最高，也可用来推翻 AI 或测试已经做出的结论。"]
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
    process_verdicts(st)        # 用户裁决优先级最高，先处理
    process_pending_ai(st)      # 剩下的待评分轮次再由 AI 补评分
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
            f"cand({iteration}): 候选快照 {rid}（尚未验证，不代表最佳）"
            f"{_model_tag()}", check=False)
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

    # ---- 4) 裁决：测试优先；测试无法裁决时先 AI 评分（代替人类），再人类 ----
    verdict, reason = decide(cand_val["status"], best_status or "unknown")
    judged_by = "auto"
    ai_result = None
    cfg = ai_judge_config(st)

    # AI 评分介入的三种情形（都可通过 ai_judge 配置/环境变量关闭）：
    #   a. 测试无法自动验证（pending_user）—— AI 代替人类打分；
    #   b. 测试通过但改动了测试文件 —— AI 复核，防止"删/弱化测试凑通过"；
    #   c. review_promoted 开启时，测试通过的候选也做一次 AI 例行复核。
    want_ai = (
        verdict == "pending_user"
        or (verdict == "promote" and (touched_tests or cfg.get("review_promoted")))
    )
    if want_ai and cfg["enabled"] and ai_judge_available():
        channel = ("API + opencode" if os.environ.get("AIJUDGE_API_KEY", "").strip()
                   else "opencode")
        log(f"{rid}：调用 AI 评分（渠道：{channel}）...")
        ai_result = run_ai_judge(diff_base, cand_sha, cand_val, changed,
                                 touched_tests, st)
        if ai_result["ok"]:
            judged_by = "ai"
            thr = ai_judge_threshold(cfg, st)
            sc = ai_result["score"]
            sc_txt = f"{sc}分" if sc is not None else ai_result["final"]
            if ai_result["final"] == "accept":
                if verdict == "pending_user":
                    verdict = "promote"
                    reason = (f"AI 评分 {sc_txt}（阈值 {thr}）："
                              f"{ai_result['reason'] or '评审通过'}；"
                              f"如不认可可在 verdicts.txt 翻案")
                else:  # 测试通过 + AI 复核通过
                    note = ("测试改动经 AI 复核为合理改进" if touched_tests
                            else "AI 例行复核通过")
                    reason += f"；{note}（{sc_txt}）"
            else:
                if verdict == "pending_user":
                    verdict = "reject"
                    reason = (f"AI 评分 {sc_txt}（阈值 {thr}）未达采纳线，保留当前最佳："
                              f"{ai_result['reason'] or '评审未通过'}；"
                              f"如不认可可在 verdicts.txt 翻案")
                else:  # 测试通过但 AI 复核不认可
                    why = ("不认可本轮对测试文件的改动（疑似规避测试）" if touched_tests
                           else "AI 复核未通过")
                    verdict = "reject"
                    reason = (f"测试虽通过，但{why}（{sc_txt}）："
                              f"{ai_result['reason'] or ''}；"
                              f"候选保留为快照，如不认可可在 verdicts.txt 翻案")
        else:
            log(f"{rid}：AI 评分不可用（{ai_result['error']}）")
            if verdict == "pending_user":
                reason += f"；AI 评分不可用（{ai_result['error']}），等待用户裁决"
            else:
                # 测试已给出客观结论，AI 只是复核：不可用就不拦截，按测试结果走
                add_note(st, f"{rid} AI 复核不可用（{ai_result['error']}），按测试结果处理")
    elif want_ai and verdict == "pending_user":
        log(f"{rid}：无可用 AI 评分渠道，等待用户评分")

    past = VERDICT_PAST.get(verdict, verdict)   # 记录用过去时：promoted/rejected
    log(f"{rid}：裁决 = {past}（by {judged_by}）{reason}")

    rec = {
        "id": rid, "snap": snap, "sha": cand_sha, "ts": now_iso(),
        "iter": iteration, "changed": len(changed),
        "touched_tests": bool(touched_tests),
        "diff_base": diff_base,            # 供之后 AI 补评分时重算 diff
        "auto": {"status": cand_val["status"], "verdict": past, "reason": reason},
        "verdict": past, "by": judged_by,
    }
    if ai_result is not None:
        rec["ai"] = _ai_record(ai_result)

    if verdict == "promote":
        _record_round(st, rec)
        st["best"] = {"snap": snap, "sha": cand_sha, "tests": cand_val["status"],
                      "at": now_iso(), "by": judged_by, "iter": iteration}
        write_state_and_docs(st)
        write_pending_doc(rid, snap, diff_base, cand_sha, cand_val, past,
                          reason, touched_tests, ai=rec.get("ai"), by=judged_by)
        commit_rounds_files(f"chore(rounds): {rid} 晋升为最佳"
                            f"（验证: {cand_val['status']}，by {judged_by}）")
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
                          reason, touched_tests, ai=rec.get("ai"), by=judged_by)
        meta_record(st, f"chore(rounds): {rid} {past}（候选验证: {cand_val['status']}，"
                          f"最佳: {best_status}，by {judged_by}）")
        log(f"{rid}：候选保留为快照，master 维持最佳；工作区已回到最佳")

    # ---- 5) 顺带处理用户评分（用户可在任意时刻翻案/回滚，优先级最高） ----
    process_verdicts(st)
    return 0


def cmd_validate(args) -> int:
    val = run_validation(REPO)
    print(json.dumps(val, ensure_ascii=False, indent=2))
    return 0 if val["status"] in ("pass", "none") else 1


def cmd_ai_judge(args) -> int:
    fetch()
    git("checkout", "-B", "master", "origin/master", check=False)
    st = load_or_bootstrap()
    process_pending_ai(st, only_snap=args.snap)
    return 0


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

    sub.add_parser("init", help="job 开始：同步远端、处理用户评分、AI 补评分、建立基线")

    p2 = sub.add_parser("after-round", help="每轮结束：快照/验证/AI 评分/晋升")
    p2.add_argument("--iter", required=True,
                    help="轮次编号（工作流里的 ITER，或 final）")

    p3 = sub.add_parser("ai-judge", help="手动触发 AI 评分（默认处理全部待评分轮次）")
    p3.add_argument("--snap", default=None,
                    help="只评分指定快照，如 snap/20261016-061234-r3")

    sub.add_parser("validate", help="对当前工作树跑自动验证")
    sub.add_parser("show", help="打印当前状态")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "init":
            return cmd_init(args)
        if args.cmd == "after-round":
            return cmd_after_round(args)
        if args.cmd == "ai-judge":
            return cmd_ai_judge(args)
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
