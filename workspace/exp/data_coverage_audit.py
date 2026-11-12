#!/usr/bin/env python3
"""Metadata-derived data-coverage audit for the 32 UniBot tasks.

Inputs (fixtures already in exp/, not newly fetched):
  - r16_task_profile.json      : per-task rubric weights, difficulty, dataset
                                 "unseen" object gaps, h1/h4 perturbation notes.
  - r16_leaderboard_stats.json : per-task success statistics over 8 models.
  - lb_20261102.json           : per-model per-task success + step score.

Outputs:
  - data_coverage_audit.json
  - a markdown table on stdout.

All leaderboard numbers come from a *generated fixture*; this script only makes
the metadata bookkeeping reproducible. It is not a real-robot result.
"""
import json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
profile = json.loads((HERE / "r16_task_profile.json").read_text())
stats = json.loads((HERE / "r16_leaderboard_stats.json").read_text())
lb = json.loads((HERE / "lb_20261102.json").read_text())


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


# per-task step score from the leaderboard fixture
step_scores, succ_scores = {}, {}
for m in lb["models"]:
    for tm in m["task_metrics"]:
        k = norm(tm["task"])
        succ_scores.setdefault(k, []).append(tm["success_rate"])
        step_scores.setdefault(k, []).append(tm["step_score"])

rows = []
for pt in stats["per_task"]:
    tid = pt["id"]
    prof = profile["tasks"][tid]
    key = norm(pt["task"])
    succ = succ_scores.get(key, [])
    step = step_scores.get(key, [])
    best_succ = max(succ) if succ else None
    best_step = max(step) if step else None
    unseen = prof.get("unseen")
    notes = [x for x in (prof.get("h1"), prof.get("h4")) if x]
    human = any(("手动" in x or "拿走" in x or "手握" in x) for x in notes)
    rows.append({
        "id": tid,
        "task": prof["name"],
        "difficulty": prof["diff"],
        "rubric_steps": len(prof["w"]),
        "rubric_weights": prof["w"],
        "episodes": prof["eps"],
        "unseen_gap": bool(unseen),
        "unseen": unseen,
        "perturbation_notes": notes,
        "human_interference_note": human,
        "best_success": round(best_succ, 2) if best_succ is not None else None,
        "mean_success": round(sum(succ) / len(succ), 2) if succ else None,
        "best_step": round(best_step, 2) if best_step is not None else None,
        "mean_step": round(sum(step) / len(step), 2) if step else None,
        "n_models": len(succ),
    })

# Transparent, deliberately simple acquisition priority:
#   documented object gap raises the multiplier from 1 to 2;
#   headroom is measured separately for success and step score.
# This is a bookkeeping heuristic, NOT a validated utility model.
for r in rows:
    gap_mult = 2.0 if r["unseen_gap"] else 1.0
    if r["best_success"] is not None:
        r["priority_success"] = round((100 - r["best_success"]) * gap_mult, 2)
    if r["best_step"] is not None:
        r["priority_step"] = round((100 - r["best_step"]) * gap_mult, 2)

rows.sort(key=lambda r: (-(r["priority_step"] or 0), -(r["priority_success"] or 0)))
out = {
    "source": "exp/r16_task_profile.json + exp/r16_leaderboard_stats.json + exp/lb_20261102.json",
    "note": "leaderboard values are a generated fixture; priority is a heuristic, not a validated utility",
    "n_tasks": len(rows),
    "n_with_documented_object_gap": sum(r["unseen_gap"] for r in rows),
    "n_with_human_interference_note": sum(r["human_interference_note"] for r in rows),
    "n_by_difficulty": {d: sum(r["difficulty"] == d for r in rows) for d in ("Easy", "Medium", "Hard")},
    "tasks": rows,
}
(HERE / "data_coverage_audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))

print("| id | task | diff | steps | best SR | best step | unseen gap | human note | P_step |")
print("|---|---|---|---:|---:|---:|---|---|---:|")
for r in rows:
    print("| {id} | {task} | {difficulty} | {rubric_steps} | {bs} | {bp} | {ug} | {hn} | {ps} |".format(
        id=r["id"], task=r["task"], difficulty=r["difficulty"], rubric_steps=r["rubric_steps"],
        bs=r["best_success"], bp=r["best_step"],
        ug=("Y" if r["unseen_gap"] else "-"), hn=("Y" if r["human_interference_note"] else "-"),
        ps=r["priority_step"]))
print()
print("tasks:", out["n_tasks"], "| object gaps:", out["n_with_documented_object_gap"],
      "| human notes:", out["n_with_human_interference_note"], "| by difficulty:", out["n_by_difficulty"])
