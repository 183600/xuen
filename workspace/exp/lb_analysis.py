"""Leaderboard structure analysis for UniBot-V1 generalist track.

Question: is the <30% plateau caused by (a) a few structurally hard tasks,
(b) task-specific incompetence that a router could fix, or (c) a broad plateau
that only broad robustness improvements can move?

Input : exp/lb_2026_11_04.json   (transcribed from the official leaderboard JSON)
Output: exp/lb_analysis_results.json
"""
from __future__ import annotations

import json
import itertools
from pathlib import Path

import numpy as np

EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
LB = json.loads((EXP / "lb_2026_11_04.json").read_text())


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    return float((ra @ rb) / (np.linalg.norm(ra) * np.linalg.norm(rb)))


def main() -> None:
    tasks = LB["tasks"]
    models = LB["models"]
    M = np.array([m["per_task"] for m in models], dtype=float)   # (8, 32)
    names = [m["model_name"] for m in models]
    published = np.array([m["avg_success_rate"] for m in models], dtype=float)

    checksum = []
    for i, m in enumerate(models):
        checksum.append({"model": m["model_name"], "published": float(published[i]),
                         "recomputed_mean": float(M[i].mean()),
                         "abs_err": float(abs(M[i].mean() - published[i]))})
    max_err = max(c["abs_err"] for c in checksum)

    per_task_mean = M.mean(axis=0)
    per_task_max = M.max(axis=0)
    per_task_min = M.min(axis=0)
    per_task_std = M.std(axis=0, ddof=1)

    best_single = float(published.max())
    oracle_router = float(per_task_max.mean())          # per-task best model (upper bound of routing)
    random_single = float(published.mean())

    # pairwise agreement of task difficulty across models
    cors = []
    for i, j in itertools.combinations(range(len(models)), 2):
        cors.append(spearman(M[i], M[j]))
    cors = np.array(cors)

    # who wins each task
    winners = [names[int(np.argmax(M[:, t]))] for t in range(len(tasks))]
    win_count = {n: winners.count(n) for n in names}

    # top-1 model competence profile
    top = int(np.argmax(published))
    top_rate = M[top]
    rank_by_max = np.argsort(-per_task_max)
    rank_by_mean = np.argsort(per_task_mean)

    out = {
        "source": LB["_source"],
        "transcription_checksum": {"max_abs_err": max_err, "per_model": checksum,
                                   "verified": bool(max_err < 0.06)},
        "headline": {
            "best_single_model": best_single,
            "mean_single_model": round(random_single, 2),
            "per_task_oracle_router": round(oracle_router, 2),
            "routing_headroom_pp": round(oracle_router - best_single, 2),
            "best_model": names[top],
        },
        "task_difficulty": [
            {"task": tasks[t], "mean": round(float(per_task_mean[t]), 2),
             "best": round(float(per_task_max[t]), 2),
             "worst": round(float(per_task_min[t]), 2),
             "std": round(float(per_task_std[t]), 2),
             "winner": winners[t],
             "top1_model_rate": round(float(top_rate[t]), 2)}
            for t in range(len(tasks))
        ],
        "difficulty_ranking_by_best_known": [
            {"task": tasks[int(t)], "best_known": round(float(per_task_max[t]), 2),
             "mean": round(float(per_task_mean[t]), 2)}
            for t in rank_by_max
        ],
        "difficulty_ranking_by_mean": [
            {"task": tasks[int(t)], "mean": round(float(per_task_mean[t]), 2)}
            for t in rank_by_mean
        ],
        "agreement": {
            "pairwise_spearman_mean": round(float(cors.mean()), 3),
            "pairwise_spearman_min": round(float(cors.min()), 3),
            "pairwise_spearman_max": round(float(cors.max()), 3),
            "interpretation": "high correlation => task difficulty is a property of the task/scene, not of the model",
        },
        "winner_histogram": win_count,
        "counts": {
            "tasks_best_known_below_25": int((per_task_max < 25).sum()),
            "tasks_best_known_below_20": int((per_task_max < 20).sum()),
            "tasks_best_known_above_35": int((per_task_max > 35).sum()),
            "tasks_top1_below_25": int((top_rate < 25).sum()),
            "tasks_top1_below_20": int((top_rate < 20).sum()),
            "tasks_spread_gt_15pp": int((per_task_max - per_task_min > 15).sum()),
            "tasks_spread_gt_20pp": int((per_task_max - per_task_min > 20).sum()),
        },
        "top1_model_profile": [
            {"task": tasks[t], "rate": round(float(top_rate[t]), 2),
             "best_known": round(float(per_task_max[t]), 2),
             "deficit_pp": round(float(per_task_max[t] - top_rate[t]), 2)}
            for t in range(len(tasks))
        ],
    }
    (EXP / "lb_analysis_results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print("checksum max err:", max_err)
    print("best single", best_single, "oracle router", round(oracle_router, 2),
          "headroom", round(oracle_router - best_single, 2))
    print("spearman mean", round(float(cors.mean()), 3))
    print("counts", out["counts"])
    print("winner histogram", win_count)
    print("hardest (by best-known):", [(d["task"], d["best_known"]) for d in out["difficulty_ranking_by_best_known"][:6]])
    print("easiest (by best-known):", [(d["task"], d["best_known"]) for d in out["difficulty_ranking_by_best_known"][-6:]])


if __name__ == "__main__":
    main()
