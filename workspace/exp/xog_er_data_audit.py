"""Audit the 32 UniBot tasks for cross-object generalisation and risk classes.

Reads the per-task profile already retrieved in exp/r16_task_profile.json and
the 8-model leaderboard statistics in exp/r16_leaderboard_stats.json, then
writes exp/xog_er_data_audit.json.

Run:  python exp/xog_er_data_audit.py
"""
import json

PROFILE = "exp/r16_task_profile.json"
STATS = "exp/r16_leaderboard_stats.json"
OUT = "exp/xog_er_data_audit.json"

# Tasks whose objects can hurt a person or damage property if handled wrongly
# (mains/connector, battery, medicine, syringe, glass tubes, sharps).
RISK = {
    "T05": "mains ethernet",
    "T09": "sharp tools in toolbox",
    "T10": "mains charger/socket",
    "T11": "batteries",
    "T13": "glass test tubes",
    "T14": "medicine bottle",
    "T15": "sharp hand tools",
    "T26": "mains ethernet/port",
    "T32": "syringe + liquid",
}


def main():
    prof = json.load(open(PROFILE, encoding="utf-8"))["tasks"]
    stats = json.load(open(STATS, encoding="utf-8"))
    per_task = {t["id"]: t for t in stats["per_task"]}

    rows = []
    for tid, t in prof.items():
        p = per_task[tid]
        rows.append(dict(
            id=tid, name=t["name"], diff=t["diff"],
            rubric_weights=t["w"],
            unseen_note=t.get("unseen"),
            has_unseen=t.get("unseen") is not None,
            risk=RISK.get(tid),
            mean_success=round(p["mean"], 2),
            min_success=round(p["min"], 2),
            max_success=round(p["max"], 2),
            mean_step_score=None,
        ))

    # attach mean step score from model-level fit only at model level; the
    # per-task file stores the fit a,b so step = a + b*success
    for r in rows:
        p = per_task[r["id"]]
        r["step_fit"] = round(p["a"] + p["b"] * p["mean"], 2)

    unseen = [r for r in rows if r["has_unseen"]]
    risk = [r for r in rows if r["risk"]]
    safe = [r for r in rows if not r["risk"]]
    both = [r for r in rows if r["has_unseen"] and r["risk"]]

    def mean(xs, key):
        return round(sum(x[key] for x in xs) / len(xs), 2) if xs else None

    audit = dict(
        source="exp/r16_task_profile.json + exp/r16_leaderboard_stats.json "
               "(retrieved 2026-11-04)",
        n_tasks=len(rows),
        n_with_unseen_note=len(unseen),
        n_risk=len(risk),
        n_risk_and_unseen=len(both),
        risk_tasks=[dict(id=r["id"], name=r["name"], risk=r["risk"],
                         mean_success=r["mean_success"])
                    for r in risk],
        risk_and_unseen=[dict(id=r["id"], name=r["name"], risk=r["risk"],
                              unseen=r["unseen_note"],
                              mean_success=r["mean_success"])
                         for r in both],
        mean_success_risk=mean(risk, "mean_success"),
        mean_success_safe=mean(safe, "mean_success"),
        mean_success_unseen=mean(unseen, "mean_success"),
        mean_success_seen=mean([r for r in rows if not r["has_unseen"]],
                               "mean_success"),
        hardest_tasks=sorted(
            [dict(id=r["id"], name=r["name"], mean_success=r["mean_success"],
                  risk=r["risk"], has_unseen=r["has_unseen"])
             for r in rows], key=lambda r: r["mean_success"])[:8],
        model_level_fit=stats["model_level_fit"],
        tasks=rows,
    )
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in audit.items() if k != "tasks"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
