#!/usr/bin/env python3
"""Round 56 analysis of the *real* UniBot-V1 leaderboard payload.

Source: https://unibot.unitree.com/leaderboard_data.json (retrieved 2026-11-11)
Local copy: round56_leaderboard_data.json

This script is descriptive analysis of published organizer data — no toy
simulation and no robot data. It answers four questions that drive the
round-56 innovation list:

  Q1  How tight is success rate -> step score? (Is partial credit a second,
      independent lever, or a monotone copy of success rate?)
  Q2  Which tasks are universally hard vs. tasks with model-dependent headroom
      (the latter are where a targeted mechanism can still move the needle)?
  Q3  How does scoring granularity (number of discrete scoring points) relate
      to achieved success rate? (Proxy for "multi-instance" burden.)
  Q4  Which leaderboard tasks actually require instance-level referring
      ("fruit 1", "left earphone", "letter b", "without grabbing any block")?

Outputs round56_lb_analysis.json.
"""
import json
import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "round56_leaderboard_data.json")
OUT = os.path.join(HERE, "round56_lb_analysis.json")

# Scoring-point structure per task, taken from the organizer's own
# tasks_v2/<slug>/info.json files (retrieved 2026-11-11). The leaderboard
# payload does not carry it, so it is hard-coded here with the source slug.
TASK_META = {
    "Hang the Cup":                ("hang_the_cup", 2, ["grab handle", "hang on marked spot"]),
    "Fruit Basket Collection":     ("fruit_basket_collection", 2, ["fruit 1 into basket", "fruit 2 into basket"]),
    "Pack the Doll":               ("pack_the_doll", 2, ["pack all dolls", "place bag upright"]),
    "Fruit Sorting":               ("sort_fruit", 3, ["fruit 1 -> matching-color plate", "fruit 2 -> matching-color plate", "fruit 3 -> matching-color plate"]),
    "Disconnect Ethernet":         ("disconnect_ethernet", 2, ["hold port + grip cable", "unplug"]),
    "Color Arrangement":           ("color_arrangement", 3, ["red block rightmost", "green block middle", "yellow block leftmost"]),
    "Place Photo Frames":          ("place_photo_frames", 3, ["grab frame", "open stand", "straighten"]),
    "Organize Bookshelf":          ("organize_bookshelf", 2, ["grab book + lift", "place on shelf"]),
    "Toolbox Storage":             ("toolbox_storage", 4, ["2 tools stored", "all tools stored", "close lid", "lock"]),
    "Plug Charger":                ("plug_charger", 3, ["grab power strip", "grab plug", "plug into strip"]),
    "Pick Out Battery":            ("pick_out_battery", 3, ["battery 1 (no block)", "battery 2 (no block)", "battery 3 (no block)"]),
    "Unlock":                      ("unlock", 3, ["pick up lock", "turn key", "flip metal ring"]),
    "Arrange Test Tubes":          ("organize_test_cube", 3, ["tube 1 to its slot", "tube 2 to its slot", "tube 3 to its slot"]),
    "Open Pill Bottle":            ("open_pill_bottle", 2, ["unscrew cap", "pour medicine"]),
    "Organize Tools":              ("organize_tools", 4, ["tool 1 -> rack", "tool 2 -> rack", "tool 3 -> rack", "tool 4 -> rack"]),
    "Fold Towel":                  ("fold_towel", 5, ["straighten", "fold top-bottom", "fold left", "fold right", "set aside"]),
    "Organize Stationery":         ("organize_stationery", 5, ["straighten case", "item 1", "item 2", "item 3", "close case"]),
    "Pack Bag":                    ("pack_bag", 4, ["grab pencil case", "grab bag + pull", "put case in bag", "zip"]),
    "Zip Up":                      ("zip_up", 2, ["straighten pouch", "zip"]),
    "Paper Cup Stacking":          ("paper_cup_stacking", 3, ["cup 1 middle", "cup 2 beside", "cup 3 on top"]),
    "Clear Plates":                ("clear_plates", 3, ["plate 1 -> rack", "plate 2 -> rack", "plate 3 -> rack"]),
    "Spell robot":                 ("spell_robot", 4, ["grab board", "letter b", "letter o", "letter t"]),
    "Store Racket":                ("store_racket", 2, ["paddle into case", "zip case"]),
    "Conveyor Food Sorting":       ("sort_food_conveyor", 2, ["grab moving food", "place by category"]),
    "Stack Cups":                  ("stack_cups", 3, ["cup 1 -> rack", "cup 2 -> rack", "cup 3 -> rack"]),
    "Plug In Ethernet":            ("plug_in_ethernet", 3, ["grab cable", "hold port", "plug in"]),
    "Stack Bowls":                 ("stack_bowls_three", 3, ["bowl 1 middle", "bowl 2 on bowl 1", "bowl 3 on bowl 2"]),
    "Store Earphones":             ("store_earphones", 4, ["grab case", "left earphone", "right earphone", "close lid + case into box"]),
    "Pack Phone":                  ("pack_iphone", 3, ["tray into box", "phone onto tray", "close box"]),
    "Remove Pinned Note":          ("remove_pinned_note", 2, ["pull all pins into box", "note into box"]),
    "Organize Pencil Case":        ("pencil_case", 3, ["open zipper", "all stationery in", "close zipper"]),
    "Syringe Water Transfer":      ("syring_water", 2, ["draw water", "inject into small cup"]),
}

# Does a scoring point force the policy to single out ONE object among
# several (indexed instance, side, attribute, or a negative constraint)?
INSTANCE_BOUND = {
    "Fruit Basket Collection", "Fruit Sorting", "Color Arrangement", "Pick Out Battery",
    "Arrange Test Tubes", "Organize Tools", "Organize Stationery", "Paper Cup Stacking",
    "Clear Plates", "Spell robot", "Stack Cups", "Stack Bowls", "Store Earphones",
    "Pack Phone", "Plug Charger", "Plug In Ethernet", "Conveyor Food Sorting",
    "Toolbox Storage", "Pack Bag",
}

# Tasks whose organizer note documents an in-episode HUMAN disturbance
# (the "human interference" generalization axis).
HUMAN_NOTE = {
    "Hang the Cup", "Fruit Basket Collection", "Pack the Doll", "Fruit Sorting",
    "Disconnect Ethernet", "Color Arrangement", "Place Photo Frames", "Organize Bookshelf",
    "Toolbox Storage", "Plug Charger", "Pick Out Battery", "Unlock",
    "Arrange Test Tubes", "Open Pill Bottle", "Organize Tools", "Fold Towel",
    "Organize Stationery", "Pack Bag", "Zip Up", "Paper Cup Stacking", "Clear Plates",
    "Spell robot", "Store Racket", "Conveyor Food Sorting", "Stack Cups",
    "Plug In Ethernet", "Stack Bowls", "Store Earphones", "Pack Phone",
    "Remove Pinned Note", "Organize Pencil Case", "Syringe Water Transfer",
}


def pearson(xs, ys):
    n = len(xs)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)

    models = data["models"]
    names = [m["model_name"] for m in models]

    # ---- Q1: success -> step score coupling -------------------------------
    succ = [m["avg_success_rate"] for m in models]
    step = [m["avg_step_score"] for m in models]
    dur = [m["avg_duration_sec"] for m in models]
    ratios = [s / ss for s, ss in zip(step, succ)]
    q1 = {
        "pearson_success_vs_step": round(pearson(succ, step), 4),
        "pearson_success_vs_duration": round(pearson(succ, dur), 4),
        "step_over_success_ratio_min": round(min(ratios), 4),
        "step_over_success_ratio_max": round(max(ratios), 4),
        "step_over_success_ratio_mean": round(statistics.mean(ratios), 4),
        "step_over_success_ratio_sd": round(statistics.pstdev(ratios), 4),
        "reading": ("step score is close to a monotone affine copy of success rate "
                    "(r=%.3f); the ratio is stable at ~%.2f, so extra step points are "
                    "earned in the SAME episodes that succeed, not traded off against "
                    "them -> optimize success first, step score follows"
                    % (pearson(succ, step), statistics.mean(ratios))),
    }

    # ---- per-task table ---------------------------------------------------
    rows = []
    for tname in data["tasks"]:
        per_model = []
        for m in models:
            tm = next(x for x in m["task_metrics"] if x["task"] == tname)
            per_model.append((tm["success_rate"], tm["step_score"], tm["avg_duration_sec"]))
        s = [p[0] for p in per_model]
        st = [p[1] for p in per_model]
        slug, nsteps, _ = TASK_META[tname]
        best = max(s)
        mean_s = statistics.mean(s)
        rows.append({
            "task": tname,
            "slug": slug,
            "n_scoring_points": nsteps,
            "instance_bound": tname in INSTANCE_BOUND,
            "human_interference_documented": tname in HUMAN_NOTE,
            "mean_success": round(mean_s, 2),
            "median_success": round(statistics.median(s), 2),
            "min_success": round(min(s), 2),
            "max_success": round(best, 2),
            "sd_success": round(statistics.pstdev(s), 2),
            "headroom_max_minus_mean": round(best - mean_s, 2),
            "mean_step_score": round(statistics.mean(st), 2),
            "best_model": names[s.index(best)],
            "best_model_success": round(best, 2),
            "per_model_success": {n: round(v[0], 2) for n, v in zip(names, per_model)},
        })
    rows.sort(key=lambda r: -r["mean_success"])

    # ---- Q2: hard-everywhere vs headroom ----------------------------------
    universally_hard = [r["task"] for r in rows if r["max_success"] < 30]
    headroom = sorted(rows, key=lambda r: -r["headroom_max_minus_mean"])[:10]

    # ---- Q3: granularity vs success --------------------------------------
    by_n = {}
    for r in rows:
        by_n.setdefault(r["n_scoring_points"], []).append(r["mean_success"])
    q3 = {
        "mean_success_by_n_scoring_points": {
            str(k): round(statistics.mean(v), 2) for k, v in sorted(by_n.items())},
        "n_tasks_by_n_scoring_points": {str(k): len(v) for k, v in sorted(by_n.items())},
        "pearson_n_points_vs_task_mean_success": round(
            pearson([r["n_scoring_points"] for r in rows],
                    [r["mean_success"] for r in rows]), 4),
        "pearson_n_points_vs_model_pooled_success": round(
            pearson([r["n_scoring_points"] for r in rows for _ in names],
                    [v for r in rows for v in r["per_model_success"].values()]), 4),
        "instance_bound_mean_success": round(
            statistics.mean(r["mean_success"] for r in rows if r["instance_bound"]), 2),
        "non_instance_bound_mean_success": round(
            statistics.mean(r["mean_success"] for r in rows if not r["instance_bound"]), 2),
    }

    # ---- Q4: instance-bound task share and their headroom -----------------
    inst_rows = [r for r in rows if r["instance_bound"]]
    q4 = {
        "n_tasks": len(rows),
        "n_instance_bound_tasks": len(inst_rows),
        "instance_bound_share": round(len(inst_rows) / len(rows), 4),
        "instance_bound_mean_headroom": round(
            statistics.mean(r["headroom_max_minus_mean"] for r in inst_rows), 2),
        "non_instance_bound_mean_headroom": round(
            statistics.mean(r["headroom_max_minus_mean"] for r in rows
                            if not r["instance_bound"]), 2),
        "n_tasks_human_interference_documented": sum(
            1 for r in rows if r["human_interference_documented"]),
    }

    # ---- leaderboard ordering (success desc, step score as tiebreak) ------
    ranked = sorted(models, key=lambda m: (-m["avg_success_rate"], -m["avg_step_score"]))
    order = [{"rank": i + 1, "model": m["model_name"], "user": m["user_name"],
              "avg_success_rate": m["avg_success_rate"],
              "avg_step_score": m["avg_step_score"],
              "avg_duration_sec": m["avg_duration_sec"],
              "is_multitask": m["is_multitask"]}
             for i, m in enumerate(ranked)]

    out = {
        "source": "https://unibot.unitree.com/leaderboard_data.json",
        "retrieved": "2026-11-11",
        "n_models": len(models),
        "models": names,
        "q1_success_step_coupling": q1,
        "q2_task_difficulty": {
            "universally_hard_tasks_max_success_below_30": universally_hard,
            "n_universally_hard": len(universally_hard),
            "top_headroom_tasks": headroom,
        },
        "q3_granularity": q3,
        "q4_instance_burden": q4,
        "ranking": order,
        "per_task": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "per_task"},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
