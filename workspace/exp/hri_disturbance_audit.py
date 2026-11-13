#!/usr/bin/env python3
"""Audit the two documented human-interference notes per UniBot task.

Source fixture: exp/r16_task_profile.json (retrieved from the official
tasks_v2/<slug>/info.json on 2026-11-04).  The fixture stores `h1` and `h4`
as the two human-interference variants, plus the official rubric weights.

This script does *bookkeeping*, not new data collection.  It separates
  - relocate : the human moves an object before the robot acts (initial-state
               perturbation, recoverable by re-localising the object);
  - undo     : the human reverses progress that the robot already made
               ("after X", "midway", "just as it arrives");
  - obstruct : the human makes the next action physically harder without
               reversing an already-completed subgoal;
  - unknown  : the fixture has no note (T31/T32).
The labels below are hand-assigned from the fixture text; the raw text is
kept in the output so the classification can be audited.

Run: PYTHONPATH=.pylibs python3 exp/hri_disturbance_audit.py
"""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILE = HERE / "r16_task_profile.json"
OUT = HERE / "hri_disturbance_audit.json"

LABELS = {
    "T01": ("relocate", "relocate"),
    "T02": ("relocate", "relocate"),
    "T03": ("relocate", "relocate"),
    "T04": ("relocate", "relocate"),
    "T05": ("obstruct", "obstruct"),
    "T06": ("relocate", "relocate"),
    "T07": ("relocate", "relocate"),
    "T08": ("undo", "relocate"),
    "T09": ("relocate", "relocate"),
    "T10": ("relocate", "undo"),
    "T11": ("relocate", "undo"),
    "T12": ("relocate", "undo"),
    "T13": ("relocate", "relocate"),
    "T14": ("undo", "relocate"),
    "T15": ("relocate", "relocate"),
    "T16": ("undo", "undo"),
    "T17": ("relocate", "undo"),
    "T18": ("relocate", "relocate"),
    "T19": ("relocate", "undo"),
    "T20": ("relocate", "relocate"),
    "T21": ("relocate", "relocate"),
    "T22": ("relocate", "relocate"),
    "T23": ("relocate", "relocate"),
    "T24": ("undo", "undo"),
    "T25": ("relocate", "undo"),
    "T26": ("relocate", "undo"),
    "T27": ("relocate", "undo"),
    "T28": ("relocate", "relocate"),
    "T29": ("relocate", "undo"),
    "T30": ("relocate", "relocate"),
    "T31": ("unknown", "unknown"),
    "T32": ("unknown", "unknown"),
}


def main():
    profile = json.loads(PROFILE.read_text())["tasks"]
    rows = []
    for tid in sorted(profile):
        t = profile[tid]
        for which, note in (("h1", t.get("h1")), ("h4", t.get("h4"))):
            kind = LABELS[tid][0 if which == "h1" else 1]
            rows.append({
                "id": tid,
                "slug": t["slug"],
                "task": t["name"],
                "weights": t["w"],
                "variant": which,
                "note": note,
                "kind": kind,
            })

    by_kind = Counter(r["kind"] for r in rows)
    tasks_with_undo = [tid for tid in sorted(profile)
                       if any(r["kind"] == "undo" for r in rows if r["id"] == tid)]
    tasks_with_progress_target = [
        tid for tid in sorted(profile)
        if any(r["kind"] in ("undo", "obstruct") for r in rows if r["id"] == tid)
    ]
    tasks_with_notes = [tid for tid in sorted(profile)
                        if any(r["note"] for r in rows if r["id"] == tid)]
    unknown = [tid for tid in sorted(profile)
               if LABELS[tid] == ("unknown", "unknown")]

    undo_rows = []
    for tid in tasks_with_undo:
        t = profile[tid]
        undo_notes = [r["note"] for r in rows
                      if r["id"] == tid and r["kind"] == "undo"]
        undo_rows.append({
            "id": tid,
            "task": t["name"],
            "weights": t["w"],
            "n_steps": len(t["w"]),
            "last_step_weight": t["w"][-1],
            "undo_notes": undo_notes,
        })

    last_weights = [r["last_step_weight"] for r in undo_rows]
    dist = Counter(r["n_steps"] for r in undo_rows)
    weights_nondecreasing_all = all(
        all(t["w"][i] <= t["w"][i + 1] for i in range(len(t["w"]) - 1))
        for t in profile.values())
    out = {
        "source": "exp/r16_task_profile.json (official info.json fixture, 2026-11-04)",
        "note": "labels are hand-assigned; raw notes retained for audit",
        "n_tasks": len(profile),
        "rubric_weights_nondecreasing_all": weights_nondecreasing_all,
        "n_tasks_with_notes": len(tasks_with_notes),
        "n_notes": len([r for r in rows if r["note"]]),
        "note_kind_counts": dict(by_kind),
        "n_tasks_with_undo": len(tasks_with_undo),
        "n_tasks_with_progress_target": len(tasks_with_progress_target),
        "n_undo_notes": sum(1 for r in rows if r["kind"] == "undo"),
        "undo_share_of_notes": round(
            sum(1 for r in rows if r["kind"] == "undo")
            / max(1, len([r for r in rows if r["note"]])), 4),
        "undo_share_of_tasks_with_notes": round(
            len(tasks_with_undo) / max(1, len(tasks_with_notes)), 4),
        "progress_target_share_of_tasks_with_notes": round(
            len(tasks_with_progress_target) / max(1, len(tasks_with_notes)), 4),
        "undo_last_step_weight_mean": round(sum(last_weights) / len(last_weights), 3),
        "undo_last_step_weight_min": min(last_weights),
        "undo_last_step_weight_max": max(last_weights),
        "undo_last_step_weight_sum": sum(last_weights),
        "undo_n_steps_hist": dict(sorted(dist.items())),
        "unknown_tasks": unknown,
        "undo_tasks": undo_rows,
        "rows": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print("| id | task | steps | weights | last | undo note |")
    print("|---|---|---:|---|---:|---|")
    for r in undo_rows:
        print("| {id} | {task} | {n} | {w} | {l} | {note} |".format(
            id=r["id"], task=r["task"], n=r["n_steps"], w=r["weights"],
            l=r["last_step_weight"], note=" / ".join(r["undo_notes"])))
    print()
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("rows", "undo_tasks")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
