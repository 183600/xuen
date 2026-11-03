"""Leaderboard structure analysis for UniBot-V1 generalist track (round 16).

Questions:
  Q1  How much of the spread is task difficulty vs model identity?
  Q2  What does a per-task oracle router buy over the best single model?
  Q3  Are the 8 head solutions diverse, or do they fail on the same tasks?
  Q4  Which tasks are hopeless for everybody (need a different capability)
      vs polarized (model-specific, fixable by conditioning)?
  Q5  Does success rate correlate with duration (speed vs competence)?

Outputs: leaderboard_analysis.json
"""
import json
import os

import numpy as np

from lb_data import MODELS, TASKS

HERE = os.path.dirname(os.path.abspath(__file__))
M = np.array([m[5] for m in MODELS], dtype=float)          # (8, 32)
NAMES = [m[0] for m in MODELS]
USERS = [m[1] for m in MODELS]
AVG = np.array([m[2] for m in MODELS], dtype=float)
DUR = np.array([m[3] for m in MODELS], dtype=float)
STEP = np.array([m[4] for m in MODELS], dtype=float)

out = {}

# --- consistency check: does the mean of per-task rates reproduce avg? ---
recomputed = M.mean(axis=1)
out["consistency"] = {
    "reported_avg": AVG.tolist(),
    "recomputed_mean_of_task_rates": np.round(recomputed, 3).tolist(),
    "max_abs_diff": float(np.max(np.abs(recomputed - AVG))),
}

# --- Q1 variance decomposition (two-way ANOVA style, no interaction term) ---
grand = M.mean()
task_means = M.mean(axis=0)                     # task difficulty
model_means = M.mean(axis=1)                    # model quality
ss_task = 8 * np.sum((task_means - grand) ** 2)
ss_model = 32 * np.sum((model_means - grand) ** 2)
ss_resid = np.sum((M - task_means[None, :] - model_means[:, None] + grand) ** 2)
ss_tot = np.sum((M - grand) ** 2)
out["variance_decomposition"] = {
    "task_effect_frac": float(ss_task / ss_tot),
    "model_effect_frac": float(ss_model / ss_tot),
    "interaction_resid_frac": float(ss_resid / ss_tot),
    "comment": "task difficulty explains far more than model identity; "
               "the residual is model x task interaction (polarization)",
}

# --- Q2 oracle routing ---
per_task_max = M.max(axis=0)
per_task_min = M.min(axis=0)
per_task_mean = M.mean(axis=0)
best_single = AVG.max()
out["oracle_routing"] = {
    "best_single_model": NAMES[int(AVG.argmax())],
    "best_single_avg": float(best_single),
    "per_task_oracle_avg": float(per_task_max.mean()),
    "per_task_worst_avg": float(per_task_min.mean()),
    "per_task_mean_avg": float(per_task_mean.mean()),
    "oracle_gain_pp": float(per_task_max.mean() - best_single),
    "mean_across_models_spread_pp": float((per_task_max - per_task_min).mean()),
    "note": "oracle router = per-task best of the 8 submitted models; it is an "
            "upper bound for task-conditioned selection, not an achievable "
            "single-model score (no per-task labels at test time)",
}

# --- Q3 model diversity: correlation of per-task profiles ---
C = np.corrcoef(M)
out["model_diversity"] = {
    "mean_pairwise_corr": float((C.sum() - np.trace(C)) / (len(M) * (len(M) - 1))),
    "min_pairwise_corr": float(C[np.triu_indices(len(M), 1)].min()),
    "max_pairwise_corr": float(C[np.triu_indices(len(M), 1)].max()),
    "corr_matrix": {NAMES[i]: {NAMES[j]: round(float(C[i, j]), 3) for j in range(len(M))}
                    for i in range(len(M))},
}

# --- Q4 task taxonomy ---
rows = []
for i, t in enumerate(TASKS):
    col = M[:, i]
    best_j = int(col.argmax())
    rows.append({
        "task": t,
        "mean": round(float(col.mean()), 2),
        "max": round(float(col.max()), 2),
        "min": round(float(col.min()), 2),
        "spread": round(float(col.max() - col.min()), 2),
        "std": round(float(col.std()), 2),
        "best_model": NAMES[best_j],
        "best_rate": round(float(col.max()), 2),
        "top1_rate": round(float(M[0, i]), 2),
        "top1_rank": int((col > M[0, i]).sum() + 1),
    })
out["tasks"] = rows
out["task_groups"] = {
    "hopeless_max_below_20": [r["task"] for r in rows if r["max"] < 20],
    "hard_max_below_25": [r["task"] for r in rows if 20 <= r["max"] < 25],
    "reachable_max_25_35": [r["task"] for r in rows if 25 <= r["max"] < 35],
    "best_below_35": [r["task"] for r in rows if r["max"] < 35],
    "best_above_35": [r["task"] for r in rows if r["max"] >= 35],
    "polarized_spread_above_15": [r["task"] for r in rows if r["spread"] > 15],
    "consistent_spread_below_8": [r["task"] for r in rows if r["spread"] < 8],
}

# --- Q5 duration vs success ---
out["duration_vs_success"] = {
    "corr_avg": float(np.corrcoef(AVG, DUR)[0, 1]),
    "per_task_corr_mean": float(np.mean([
        np.corrcoef(M[:, i], DUR)[0, 1] for i in range(M.shape[1])])),
    "step_score_over_success": np.round(STEP / AVG, 4).tolist(),
    "comment": "shorter episodes do not imply lower success; step score is a "
               "near-constant multiple of success rate (~1.31), i.e. partial "
               "credit dominates the secondary metric",
}

# --- where does the leader actually stand per task? ---
out["leader_weak_tasks"] = {
    "leader_avg": float(AVG[0]),
    "tasks_where_leader_below_25": [r["task"] for r in rows if r["top1_rate"] < 25],
    "tasks_where_leader_is_best": [r["task"] for r in rows if r["best_model"] == NAMES[0]],
    "leader_rank1_count": int(sum(1 for r in rows if r["top1_rank"] == 1)),
    "leader_rank_worst": int(max(r["top1_rank"] for r in rows)),
}

with open(os.path.join(HERE, "leaderboard_analysis.json"), "w") as f:
    json.dump(out, f, indent=2)

# --- console report ---
print("== consistency: max |reported - recomputed| =",
      round(out["consistency"]["max_abs_diff"], 3))
v = out["variance_decomposition"]
print(f"== variance: task {v['task_effect_frac']:.1%} | model "
      f"{v['model_effect_frac']:.1%} | interaction {v['interaction_resid_frac']:.1%}")
o = out["oracle_routing"]
print(f"== best single {o['best_single_model']} {o['best_single_avg']:.1f} | "
      f"per-task oracle {o['per_task_oracle_avg']:.2f} (+{o['oracle_gain_pp']:.2f} pp) | "
      f"mean spread {o['mean_across_models_spread_pp']:.1f} pp")
d = out["model_diversity"]
print(f"== pairwise per-task corr: mean {d['mean_pairwise_corr']:.3f} "
      f"[{d['min_pairwise_corr']:.3f}, {d['max_pairwise_corr']:.3f}]")
print(f"== duration~success corr {out['duration_vs_success']['corr_avg']:.3f}; "
      f"step/success {np.mean(STEP / AVG):.3f}")
print("\n== per-task table (mean / max / best model / spread) ==")
for r in sorted(rows, key=lambda r: -r["spread"]):
    print(f"  {r['task']:<24} mean {r['mean']:>5.2f}  max {r['max']:>5.2f} "
          f"({r['best_model']:<14}) spread {r['spread']:>5.2f} "
          f"top1 {r['top1_rate']:>5.2f} rank {r['top1_rank']}")
g = out["task_groups"]
print("\n== hopeless (max<20):", g["hopeless_max_below_20"])
print("== best<35:", len(g["best_below_35"]), "tasks; best>=35:", g["best_above_35"])
print("== polarized (spread>15):", g["polarized_spread_above_15"])
print("== consistent (spread<8):", g["consistent_spread_below_8"])
print("== leader rank1 on", out["leader_weak_tasks"]["leader_rank1_count"],
      "tasks; worst rank", out["leader_weak_tasks"]["leader_rank_worst"])
