#!/usr/bin/env python3
"""STATEKEEPER rubric-contract audit (P0, pure Python, no external deps).

Inputs (produced 2026-10-31 from the official site / HF):
  /tmp/all_task_info.json : {slug: <tasks_v2/<slug>/info.json>} (32 tasks)
  /tmp/all_tasks.json     : {dataset_slug: [{"task": "p1@p2@...", ...}]} (32x5)

Checks:
  1. exactly 32 tasks, scoring points parse, each task sums to 100
  2. total scoring steps == 94
  3. exactly 5 paraphrases per task == 160
  4. feature tags R (repeated/count), U (undoable human disturbance),
     L (final close/zip/lock), H (final step >= 40)
  5. difficulty distribution 12/12/8
Outputs JSON summary + markdown table.
"""
import collections
import json
import re
import sys


REPEAT = set("T02 T03 T04 T09 T11 T13 T15 T17 T20 T21 T25 T27 T28 T30 T31".split())
UNDO = set("T10 T14 T16 T17 T19 T24 T26 T27 T29".split())
LOCK = set("T09 T17 T18 T19 T23 T28 T29 T31".split())


def parse_points(text):
    pts = [int(x) for x in re.findall(r"(\d+)\s*pts", text or "")]
    if not pts:
        pts = [int(x) for x in re.findall(r"(\d+)\s*分", text or "")]
    return pts


def main(info_path, tasks_path):
    info = json.load(open(info_path))
    tasks = json.load(open(tasks_path))
    rows = []
    for slug, t in info.items():
        pts = parse_points(t.get("scoring_points_en") or t.get("scoring_points"))
        tags = []
        if t["task_id"] in REPEAT:
            tags.append("R")
        if t["task_id"] in UNDO:
            tags.append("U")
        if t["task_id"] in LOCK:
            tags.append("L")
        if pts and pts[-1] >= 40:
            tags.append("H")
        rows.append({
            "id": t["task_id"], "slug": slug, "name": t["en_name"],
            "difficulty": t["difficulty_en"], "steps": len(pts),
            "points": pts, "sum": sum(pts), "final": pts[-1] if pts else None,
            "tags": tags,
        })
    rows.sort(key=lambda r: r["id"])
    n_tasks = len(rows)
    n_steps = sum(r["steps"] for r in rows)
    paraphrase_counts = {k: sum(len(row["task"].split("@")) for row in v)
                         for k, v in tasks.items()}
    checks = {
        "tasks_32": n_tasks == 32,
        "steps_94": n_steps == 94,
        "all_sum_100": all(r["sum"] == 100 for r in rows),
        "paraphrases_160": sum(paraphrase_counts.values()) == 160,
        "paraphrases_5_per_task": all(v == 5 for v in paraphrase_counts.values()),
        "difficulty_12_12_8": collections.Counter(r["difficulty"] for r in rows) ==
                              {"Easy": 12, "Medium": 12, "Hard": 8},
        "stepdist_11_14_5_2": collections.Counter(r["steps"] for r in rows) ==
                              {2: 11, 3: 14, 4: 5, 5: 2},
    }
    summary = {
        "n_tasks": n_tasks,
        "n_steps": n_steps,
        "n_paraphrases": sum(paraphrase_counts.values()),
        "difficulty": dict(collections.Counter(r["difficulty"] for r in rows)),
        "step_distribution": dict(collections.Counter(r["steps"] for r in rows)),
        "final_ge_40": sum(1 for r in rows if r["final"] and r["final"] >= 40),
        "final_ge_45": sum(1 for r in rows if r["final"] and r["final"] >= 45),
        "repeat_R": sum("R" in r["tags"] for r in rows),
        "undo_U": sum("U" in r["tags"] for r in rows),
        "lock_L": sum("L" in r["tags"] for r in rows),
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "tasks": rows,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/all_task_info.json",
         sys.argv[2] if len(sys.argv) > 2 else "/tmp/all_tasks.json")
