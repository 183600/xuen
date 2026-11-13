#!/usr/bin/env python3
"""SALT toy mechanism check.

This is NOT a robot experiment. It only checks the causal-attribution logic:
can a sense-of-agency (SoA) residual that uses the commanded action distinguish
self-failure from external undo, while a static predicate verifier cannot?

Causes:
  self   : robot commanded motion, object did not move (grasp slip)
  undo   : robot held still, human moved object back to start
  disp   : robot held still, human moved object sideways (predicate still true)
  remove : robot held still, human removed object

The static verifier sees only (dx, dy, present). SALT also sees |a|.
"""
import json
import math
import random
from collections import Counter

CAUSES = ["self", "undo", "disp", "remove"]
PRIOR = {"self": 0.35, "undo": 0.30, "disp": 0.20, "remove": 0.15}

# recovery success probability by (cause, action)
SUCCESS = {
    "self":   {"regrasp": 0.85, "redo": 0.45, "realign": 0.30, "search": 0.20, "abort": 0.0},
    "undo":   {"regrasp": 0.55, "redo": 0.90, "realign": 0.40, "search": 0.20, "abort": 0.0},
    "disp":   {"regrasp": 0.35, "redo": 0.40, "realign": 0.85, "search": 0.20, "abort": 0.0},
    "remove": {"regrasp": 0.10, "redo": 0.00, "realign": 0.10, "search": 0.50, "abort": 0.0},
}

# step score if recovery succeeds: step1 (50) + step2 (50) with 0.8 conditional success
SCORE_IF_RECOVERED = 50 + 50 * 0.8


def sample(cause, rng, sigma):
    if cause == "self":
        a = rng.uniform(0.10, 0.30)
        dx = rng.gauss(0.0, sigma)
        dy = rng.gauss(0.0, sigma)
        present = 1
    elif cause == "undo":
        a = rng.uniform(0.0, 0.05)
        dx = rng.gauss(-1.0, sigma)
        dy = rng.gauss(0.0, sigma)
        present = 1
    elif cause == "disp":
        a = rng.uniform(0.0, 0.05)
        dx = rng.gauss(0.0, sigma)
        dy = rng.gauss(0.5, sigma)
        present = 1
    else:  # remove
        a = rng.uniform(0.0, 0.05)
        dx = rng.gauss(0.0, sigma)
        dy = rng.gauss(0.0, sigma)
        present = 0
    return a, dx, dy, present


def static_verifier(dx, dy, present):
    # v2-style: object missing => abort; otherwise always redo the failed step
    if present == 0:
        return "abort"
    return "redo"


def salt_verifier(a, dx, dy, present):
    # SoA-based causal attribution (simple, interpretable rule)
    if present == 0:
        return "remove"
    if abs(dy) > 0.20:
        return "disp"
    if a > 0.08 and abs(dx) < 0.20:
        return "self"
    return "undo"


def recovery_action(cause):
    return {
        "self": "regrasp",
        "undo": "redo",
        "disp": "realign",
        "remove": "search",
    }[cause]


def main():
    rng = random.Random(7)
    n = 100_000
    out = {}
    for sigma in (0.01, 0.03, 0.05, 0.10):
        conf = {c: Counter() for c in CAUSES}
        salt_score = 0.0
        static_score = 0.0
        for _ in range(n):
            cause = rng.choices(CAUSES, weights=[PRIOR[c] for c in CAUSES])[0]
            a, dx, dy, present = sample(cause, rng, sigma)
            # static
            sa = static_verifier(dx, dy, present)
            static_score += SUCCESS[cause][sa] * SCORE_IF_RECOVERED
            # SALT
            pred = salt_verifier(a, dx, dy, present)
            conf[cause][pred] += 1
            salt_score += SUCCESS[cause][recovery_action(pred)] * SCORE_IF_RECOVERED
        acc = sum(conf[c][c] for c in CAUSES) / n
        out[str(sigma)] = {
            "attribution_accuracy": acc,
            "static_expected_score": static_score / n,
            "salt_expected_score": salt_score / n,
            "confusion": {c: dict(conf[c]) for c in CAUSES},
        }
    # print compact table
    print("sigma  acc    static  SALT")
    for sigma in (0.01, 0.03, 0.05, 0.10):
        r = out[str(sigma)]
        print(f"{sigma:<6} {r['attribution_accuracy']:.3f}  {r['static_expected_score']:.1f}    {r['salt_expected_score']:.1f}")
    with open("/home/runner/work/xuen/xuen/workspace/exp/salt_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
