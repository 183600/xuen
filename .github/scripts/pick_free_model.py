#!/usr/bin/env python3
"""随机挑选一个 opencode Zen 免费模型。

标准: type=chat、支持工具调用、文本价格全为 0（或 id 以 -free 结尾）。
用法: pick_free_model.py [排除列表,逗号分隔]
输出: stdout 一行模型 id（不含 opencode/ 前缀）；无可用模型时退出码 1。
目录 API 不可用时回退到内置免费清单。
环境: OPENCODE_API_KEY（可选，用于查询目录）
"""
import json
import os
import random
import sys
import urllib.request

FALLBACK_FREE_MODELS = [
    "big-pickle",
    "mimo-v2.6-flash-free",
    "deepseek-v4.1-flash-free",
    "glm-5.3-flash-free",
    "longcat-2.5-free",
    "iceman-free",
    "inkling-2-small-free",
    "beam-free",
    "flint-40b-free",
    "nemotron-3.5-super-vl-free",
    "nemotron-3.5-lightning-free",
    "minimax-m3.1-flash-free",
]


def is_free(m):
    if m.get("id", "").endswith("-free"):
        return True
    cost = m.get("cost", {}).get("text", {})
    prices = [v.get("price", 1) for v in cost.values() if isinstance(v, dict)]
    return bool(prices) and all(p == 0 for p in prices)


def main():
    exclude = {x.strip() for x in (sys.argv[1] if len(sys.argv) > 1 else "").split(",") if x.strip()}
    models = []
    key = os.environ.get("OPENCODE_API_KEY", "").strip()
    try:
        req = urllib.request.Request(
            "https://opencode.ai/zen/v1/models",
            headers={"Authorization": "Bearer " + key} if key else {})
        req.add_header("User-Agent", "opencode-ci-picker/1.0")  # 默认 python UA 会被 403
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        for m in d.get("data", []):
            if m.get("type") != "chat":
                continue
            if not m.get("capabilities", {}).get("tools", {}).get("supported"):
                continue
            if is_free(m):
                models.append(m["id"])
        print(f"[pick] 线上目录命中 {len(models)} 个免费模型", file=sys.stderr)
    except Exception as e:
        print(f"[pick] 目录查询失败({e})，使用内置免费清单", file=sys.stderr)
    if not models:
        models = list(FALLBACK_FREE_MODELS)
        print("[pick] 使用内置免费清单", file=sys.stderr)
    ok = [m for m in models if m not in exclude]
    print(f"[pick] 去除已失效后可选({len(ok)}): {','.join(ok)}", file=sys.stderr)
    if not ok:
        print("[pick] 全部模型被排除，无模型可选", file=sys.stderr)
        sys.exit(1)
    print(random.choice(ok))


if __name__ == "__main__":
    main()
