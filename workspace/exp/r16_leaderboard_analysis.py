#!/usr/bin/env python3
"""Round-16 leaderboard analysis for the UniBot-V1 Challenge (generalist track).

Inputs (both fetched 2026-11-04):
  * r16_leaderboard_data.json : https://unibot.unitree.com/leaderboard_data.json
  * r16_task_profile.json      : per-task official rubric (scoring_points), difficulty,
                                 generalization notes, dataset episode counts
                                 (https://unibot.unitree.com/tasks_v2/<slug>/info.json,
                                  https://huggingface.co/api/collections/unitreerobotics/unibot-v1-challenge-dataset)

Outputs r16_leaderboard_stats.json and prints the numbers quoted in the report.
All statements here are arithmetic on public data; no modelling assumptions.
"""
import json
import math
import os
import statistics as st
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
lb = json.load(open(os.path.join(HERE, "r16_leaderboard_data.json")))
prof = json.load(open(os.path.join(HERE, "r16_task_profile.json")))

tasks = lb["tasks"]
models = lb["models"]
name2id = {
    "Hang the Cup": "T01", "Fruit Basket Collection": "T02", "Pack the Doll": "T03",
    "Fruit Sorting": "T04", "Disconnect Ethernet": "T05", "Color Arrangement": "T06",
    "Place Photo Frames": "T07", "Organize Bookshelf": "T08", "Toolbox Storage": "T09",
    "Plug Charger": "T10", "Pick Out Battery": "T11", "Unlock": "T12",
    "Arrange Test Tubes": "T13", "Open Pill Bottle": "T14", "Organize Tools": "T15",
    "Fold Towel": "T16", "Organize Stationery": "T17", "Pack Bag": "T18", "Zip Up": "T19",
    "Paper Cup Stacking": "T20", "Clear Plates": "T21", "Spell robot": "T22",
    "Store Racket": "T23", "Conveyor Food Sorting": "T24", "Stack Cups": "T25",
    "Plug In Ethernet": "T26", "Stack Bowls": "T27", "Store Earphones": "T28",
    "Pack Phone": "T29", "Remove Pinned Note": "T30", "Organize Pencil Case": "T31",
    "Syringe Water Transfer": "T32",
}

succ = {m["model_name"]: {t["task"]: t["success_rate"] for t in m["task_metrics"]} for m in models}
step = {m["model_name"]: {t["task"]: t["step_score"] for t in m["task_metrics"]} for m in models}

out = {"retrieved": "2026-11-04", "n_models": len(models), "n_tasks": len(tasks)}

# ---- M1 model-level summary -------------------------------------------------
msum = []
for m in models:
    msum.append({
        "model": m["model_name"], "user": m["user_name"],
        "avg_success_rate": m["avg_success_rate"], "avg_step_score": m["avg_step_score"],
        "avg_duration_sec": m["avg_duration_sec"],
        "step_per_success": round(m["avg_step_score"] / m["avg_success_rate"], 3),
    })
out["models"] = msum

xs = [m["avg_success_rate"] for m in models]
ys = [m["avg_step_score"] for m in models]
mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
b1 = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
b0 = my - b1 * mx
r2 = 1 - sum((y - (b0 + b1 * x)) ** 2 for x, y in zip(xs, ys)) / sum((y - my) ** 2 for y in ys)
out["model_level_fit"] = {"formula": f"step = {b0:.3f} + {b1:.3f} * success",
                           "intercept": round(b0, 3),
                           "slope": round(b1, 3), "r2": round(r2, 4)}

# ---- M2 per-task affine fit + oracle routing bound --------------------------
per_task = []
viol = 0
for t in tasks:
    tid = name2id[t]
    sx = [succ[m["model_name"]][t] for m in models]
    sy = [step[m["model_name"]][t] for m in models]
    for a, b in zip(sx, sy):
        if b + 1e-9 < a:
            viol += 1
    ax, ay = sum(sx) / len(sx), sum(sy) / len(sy)
    den = sum((x - ax) ** 2 for x in sx)
    bb = sum((x - ax) * (y - ay) for x, y in zip(sx, sy)) / den if den > 1e-9 else 0.0
    aa = ay - bb * ax
    resid = sum((y - (aa + bb * x)) ** 2 for x, y in zip(sx, sy))
    sst = sum((y - ay) ** 2 for y in sy)
    best = max(sx)
    best_model = [m["model_name"] for m in models if succ[m["model_name"]][t] == best][0]
    per_task.append({
        "id": tid, "task": t, "slug": prof["tasks"][tid]["slug"], "difficulty": prof["tasks"][tid]["diff"],
        "rubric_steps": len(prof["tasks"][tid]["w"]), "rubric_weights": prof["tasks"][tid]["w"],
        "a": round(aa, 3), "b": round(bb, 3), "r2": round(1 - resid / sst, 4),
        "min": min(sx), "mean": round(sum(sx) / len(sx), 2), "max": max(sx), "best_model": best_model,
        "spread": round(max(sx) - min(sx), 2),
    })
out["per_task"] = per_task
out["violations_step_ge_success"] = viol
out["per_task_fit_summary"] = {
    "mean_b": round(sum(p["b"] for p in per_task) / len(per_task), 3),
    "min_b": min(p["b"] for p in per_task), "max_b": max(p["b"] for p in per_task),
    "mean_r2": round(sum(p["r2"] for p in per_task) / len(per_task), 4),
    "min_r2": min(p["r2"] for p in per_task),
    "mean_a": round(sum(p["a"] for p in per_task) / len(per_task), 3),
    "oracle_per_task_routing_avg": round(sum(p["max"] for p in per_task) / len(per_task), 2),
    "per_task_mean_avg": round(sum(p["mean"] for p in per_task) / len(per_task), 2),
    "mean_spread": round(sum(p["spread"] for p in per_task) / len(per_task), 2),
}
out["best_model_task_counts"] = dict(Counter(p["best_model"] for p in per_task))

# ---- M3 rubric / difficulty structure --------------------------------------
out["rubric_step_histogram"] = dict(Counter(len(prof["tasks"][t]["w"]) for t in prof["tasks"]))
by_diff = defaultdict(list)
for p in per_task:
    by_diff[p["difficulty"]].append(p["mean"])
out["difficulty_groups"] = {k: {"n": len(v), "mean_success": round(sum(v) / len(v), 2)}
                            for k, v in by_diff.items()}


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return round(num / den, 3) if den > 1e-12 else 0.0


out["corr_steps_vs_success"] = corr([p["rubric_steps"] for p in per_task], [p["mean"] for p in per_task])
out["corr_difficulty_vs_success"] = corr(
    [{"Easy": 0, "Medium": 0.5, "Hard": 1}[p["difficulty"]] for p in per_task],
    [p["mean"] for p in per_task])

# ---- M4 dataset geometry ----------------------------------------------------
out["dataset"] = {
    "episodes_total": sum(v["eps"] for v in prof["tasks"].values()),
    "episodes_min": min(v["eps"] for v in prof["tasks"].values()),
    "episodes_max": max(v["eps"] for v in prof["tasks"].values()),
    "tasks_with_unseen_object_note": sum(1 for v in prof["tasks"].values() if v.get("unseen")),
    "tasks_with_human_notes": sum(1 for v in prof["tasks"].values() if v.get("h1") or v.get("h4")),
}

json.dump(out, open(os.path.join(HERE, "r16_leaderboard_stats.json"), "w"), indent=1)

print("== models ==")
for m in msum:
    print(f"  {m['model']:16s} succ {m['avg_success_rate']:5.1f}  step {m['avg_step_score']:5.1f} "
          f" ratio {m['step_per_success']:.3f}  dur {m['avg_duration_sec']:5.2f}s")
print(f"\nmodel-level fit: step = {out['model_level_fit']['intercept']} + "
      f"{out['model_level_fit']['slope']}*success  (R2={out['model_level_fit']['r2']})")
s = out["per_task_fit_summary"]
print(f"per-task fit: mean b={s['mean_b']} (min {s['min_b']}, max {s['max_b']}), "
      f"mean R2={s['mean_r2']} (min {s['min_r2']}), mean a={s['mean_a']}")
print(f"violations of step>=success over 256 cells: {viol}")
print(f"oracle per-task routing {s['oracle_per_task_routing_avg']}% vs best single model "
      f"{max(m['avg_success_rate'] for m in msum)}% vs per-task mean {s['per_task_mean_avg']}%")
print(f"mean per-task spread {s['mean_spread']}pp; best-model counts {out['best_model_task_counts']}")
print(f"rubric step histogram {out['rubric_step_histogram']}; difficulty {out['difficulty_groups']}")
print(f"corr(rubric_steps, success)={out['corr_steps_vs_success']}  "
      f"corr(difficulty, success)={out['corr_difficulty_vs_success']}")
print(f"dataset {out['dataset']}")
