"""Round-v3 audit: what the official leaderboard actually says.

Inspiration words: 「视觉伺服」 (visual servoing) × 「意图识别」 (intent recognition).

This script only reads the snapshot fetched on 2026-11-12 and reports:
  A1. per-model mean success / step score over the 32 tasks;
  A2. the per-task best model and the absolute success headroom;
  A3. the empirical relation step_score ~ a * success + b (the key surprise);
  A4. a short "last-mile" ranking used to pick servo targets.

NOT a benchmark result: A1-A3 are descriptive statistics of the public
leaderboard snapshot; A4 is a heuristic ranking of the same snapshot.
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
SRC = EXP / "official" / "unibot_official_20261112.json"
OUT = EXP / "visc_audit_results.json"


def affine(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    a = sxy / sxx if sxx else 0.0
    b = my - a * mx
    syy = sum((y - my) ** 2 for y in ys)
    ssr = sum((y - (a * x + b)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ssr / syy if syy else 1.0
    return a, b, r2


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    tasks = data["tasks"]

    models = sorted({m for t in tasks.values() for m in t["success"]})
    model_stats = {}
    for m in models:
        succ = [t["success"][m] for t in tasks.values() if m in t["success"]]
        step = [t["step_score"][m] for t in tasks.values()
                if m in t["step_score"]]
        model_stats[m] = {
            "n_tasks": len(succ),
            "success_mean": round(st.mean(succ), 2),
            "success_median": round(st.median(succ), 2),
            "success_min": round(min(succ), 2),
            "success_max": round(max(succ), 2),
            "step_mean": round(st.mean(step), 2),
            "step_median": round(st.median(step), 2),
        }

    task_rows = []
    for slug, t in tasks.items():
        succ = t["success"]
        step = t["step_score"]
        best_m = max(succ, key=succ.get)
        best_step_m = max(step, key=step.get)
        task_rows.append({
            "slug": slug,
            "name": t["en_name"],
            "difficulty": t["difficulty"],
            "n_steps": t["n_steps"],
            "step_scores": t["step_scores"],
            "success_best": round(succ[best_m], 2),
            "success_best_model": best_m,
            "step_best": round(step[best_step_m], 2),
            "step_best_model": best_step_m,
            "success_mean": round(st.mean(succ.values()), 2),
            "step_mean": round(st.mean(step.values()), 2),
            "success_headroom_pp": round(100.0 - succ[best_m], 2),
            "step_minus_success": round(step[best_step_m] - succ[best_m], 2),
        })
    task_rows.sort(key=lambda r: r["success_best"])

    all_s, all_t = [], []
    per_task_fit = []
    for t in tasks.values():
        xs = list(t["success"].values())
        ys = list(t["step_score"].values())
        all_s += xs
        all_t += ys
        a, b, r2 = affine(xs, ys)
        per_task_fit.append({"slug": t["en_name"], "a": round(a, 4),
                             "b": round(b, 4), "r2": round(r2, 4)})
    ga, gb, gr2 = affine(all_s, all_t)
    diffs = [y - x for x, y in zip(all_s, all_t)]

    out = {
        "source": data.get("source"),
        "retrieved": data.get("retrieved"),
        "n_tasks": len(tasks),
        "n_models": len(models),
        "models": model_stats,
        "best_success_overall": round(max(r["success_best"] for r in task_rows), 2),
        "best_success_mean_over_tasks": round(st.mean(r["success_best"] for r in task_rows), 2),
        "best_step_mean_over_tasks": round(st.mean(r["step_best"] for r in task_rows), 2),
        "n_tasks_no_model_ge_50_success": sum(1 for r in task_rows if r["success_best"] < 50.0),
        "step_vs_success_global": {
            "step_eq_a_success_plus_b": [round(ga, 4), round(gb, 4)],
            "r2": round(gr2, 6),
            "min_step_minus_success": round(min(diffs), 4),
            "max_step_minus_success": round(max(diffs), 4),
            "mean_step_minus_success": round(st.mean(diffs), 4),
            "n_cells": len(all_s),
        },
        "per_task_fit_r2": {
            "mean": round(st.mean(p["r2"] for p in per_task_fit), 4),
            "min": round(min(p["r2"] for p in per_task_fit), 4),
            "max": round(max(p["r2"] for p in per_task_fit), 4),
        },
        "last_mile_rank_by_success_headroom": task_rows[:12],
        "per_task": task_rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    print(json.dumps({k: out[k] for k in (
        "n_tasks", "n_models", "best_success_mean_over_tasks",
        "best_step_mean_over_tasks", "n_tasks_no_model_ge_50_success",
        "step_vs_success_global", "per_task_fit_r2")}, ensure_ascii=False, indent=2))
    print("hardest by best success:")
    for r in task_rows[:10]:
        print(f"  {r['slug']:22s} best_succ={r['success_best']:5.2f} "
              f"best_step={r['step_best']:5.2f} step-succ={r['step_minus_success']:5.2f}")


if __name__ == "__main__":
    main()
