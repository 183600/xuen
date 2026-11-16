#!/usr/bin/env python3
"""OpenCode deepseek 把关：审查全部待推送改动（相对远程已批准基准），决定是否允许推送。

用法: deepseek_gate.py [标签] [分支,默认 main]
输出(stdout 单行):
  APPROVE          —— 通过（或相对远程基准没有任何待审改动）
  REJECT:<理由>    —— 拦截本次推送
  UNAVAILABLE      —— 无法确定基准或把关模型不可用（由调用方跳过推送）

⭐ 把关模型 = opencode 自带的免费 deepseek（deepseek-v4.1-flash-free）。
   免费模型只能在 opencode 客户端内使用（直连 Zen 网关 HTTP 会得到
   FreeUsageLimitError），因此本脚本通过 `opencode run -m opencode/<model>`
   调用，需要 runner 预装 opencode 并设置 OPENCODE_API_KEY。

把关范围 = git diff origin/<分支>（覆盖暂存区、工作区、以及 agent 本地已
commit 但尚未推送的全部改动，防止通过本地提交绕过审查）。
.github/.loop-phase（阶段轮换状态文件）不属于审查内容，自动排除。
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

FALLBACK_GATE_MODELS = ["deepseek-v4.1-flash-free"]
MAX_DIFF_CHARS = 60000
GATE_CALL_TIMEOUT = 240  # 单次把关调用的秒数上限
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
STATE_FILE = ".github/.loop-phase"


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout


def free_deepseek_models():
    """线上目录里免费的 deepseek 模型（查询失败回退内置清单）。"""
    ids = []
    key = os.environ.get("OPENCODE_API_KEY", "").strip()
    try:
        req = urllib.request.Request(
            "https://opencode.ai/zen/v1/models",
            headers={"Authorization": "Bearer " + key} if key else {})
        req.add_header("User-Agent", "opencode-ci-gate/1.0")  # 默认 python UA 会被 403
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        for m in d.get("data", []):
            if m.get("type") != "chat":
                continue
            mid = m.get("id", "")
            if "deepseek" not in mid.lower():
                continue
            if mid.endswith("-free"):
                ids.append(mid)
                continue
            cost = m.get("cost", {}).get("text", {})
            prices = [v.get("price", 1) for v in cost.values() if isinstance(v, dict)]
            if prices and all(p == 0 for p in prices):
                ids.append(mid)
    except Exception:
        pass
    for f in FALLBACK_GATE_MODELS:
        if f not in ids:
            ids.append(f)
    return ids


def call_opencode_deepseek(model_id, prompt):
    """通过 opencode CLI 调用免费 deepseek 模型。

    cwd 用 /tmp：避免仓库内的 opencode 配置（opencode.json 等）干扰把关调用。
    """
    r = subprocess.run(
        ["opencode", "run", "-m", f"opencode/{model_id}", prompt],
        capture_output=True, text=True, timeout=GATE_CALL_TIMEOUT,
        stdin=subprocess.DEVNULL, cwd="/tmp")
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0:
        raise RuntimeError(f"opencode exit {r.returncode}: {out[-300:]}")
    return out


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "auto commit"
    branch = sys.argv[2] if len(sys.argv) > 2 else "main"
    base = f"origin/{branch}"

    # 基准引用必须存在；无法确定基准时宁可不放行
    chk = subprocess.run(["git", "rev-parse", "--verify", "--quiet", base],
                         capture_output=True)
    if chk.returncode != 0:
        print("UNAVAILABLE")
        return

    # 待审改动 = 相对远程已批准基准的全部改动（排除阶段轮换状态文件）
    diff = sh("git", "diff", base, "--", ".", f":(exclude){STATE_FILE}")
    if not diff.strip():
        print("APPROVE")
        return
    stat = sh("git", "diff", base, "--stat", "--", ".", f":(exclude){STATE_FILE}")
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + (
            f"\n... [diff 已截断，完整长度 {len(diff)} 字符，请结合 --stat 概览判断]")

    if not os.environ.get("OPENCODE_API_KEY", "").strip():
        print("UNAVAILABLE")
        return

    prompt = f"""你是代码把关人。一个自主 AI 循环即将把以下改动推送到 {branch} 分支（提交标签: {label}）。

改动概览 (git diff {base} --stat):
{stat}

改动内容 (diff):
{diff}

审查标准（只在满足拦截条件时才 REJECT）：
1. 明显破坏性：删除大量关键文件/清空核心代码/破坏入口或功能语义/注入恶意或完全无关内容；
2. 明显作弊行为：实现变空壳、无脑 return、篡改或削弱测试断言；
3. 对 .github/ 目录（CI 工作流与脚本）的任何改动一律 REJECT——自主循环不允许改动 CI 配置（.github/.loop-phase 阶段状态文件已排除，不在改动中）。
普通的性能优化、重构、小幅修改、文档/注释变化 → 一律 APPROVE。

只输出一行 JSON，不要任何其他文字：
{{"verdict":"APPROVE","reason":"一句话说明"}}
或
{{"verdict":"REJECT","reason":"一句话拦截理由"}}"""

    content = ""
    for model_id in free_deepseek_models()[:2]:  # 最多尝试 2 个免费 deepseek
        try:
            content = call_opencode_deepseek(model_id, prompt)
            if "verdict" in content:
                break
        except Exception:
            continue

    if not content.strip():
        print("UNAVAILABLE")
        return
    content = ANSI_RE.sub("", content)
    m = re.search(r'\{[^{}]*"verdict"\s*:\s*"(APPROVE|REJECT)"[^{}]*\}', content, re.S)
    if m:
        try:
            j = json.loads(m.group(0))
            reason = str(j.get("reason", ""))[:300].replace("\n", " ")
            print(f"{j['verdict']}:{reason}" if j["verdict"] == "REJECT" else "APPROVE")
            return
        except Exception:
            pass
    if "REJECT" in content:
        print("REJECT:" + content[:200].replace("\n", " "))
    else:
        print("APPROVE")


if __name__ == "__main__":
    main()
