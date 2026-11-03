#!/usr/bin/env python3
"""Round-A roadmap analysis of the real UniBot-V1 leaderboard.

Reads /tmp/opencode/lb.json (leaderboard_data.json) and builds a
skill-composition matrix for the 32 tasks, then correlates task difficulty
with skill content.  This is B-level evidence: it reads real published data
but the skill rubric is a hand-coded design assumption.
"""
import json, os, statistics, math

HERE = os.path.dirname(os.path.abspath(__file__))
LB = os.path.join(HERE, "lb.json")
if not os.path.exists(LB):
    LB = "/tmp/opencode/lb.json"
d = json.load(open(LB))
models = d["models"]

# canonical task name -> (leaderboard name)
LB_TASKS = [t["task"] for t in models[0]["task_metrics"]]

# skill vocabulary (hand-coded rubric). weights in {1,2,3} = peripheral/core/heavy
SKILLS = ["reach_grasp", "place_stack", "insert_align", "articulate",
          "press_toggle", "deform", "fluid", "sort_select", "bimanual_carry"]

# task -> {skill: weight}
MATRIX = {
 "Hang the Cup":            {"reach_grasp":3, "place_stack":2, "bimanual_carry":1},
 "Fruit Basket Collection": {"reach_grasp":3, "place_stack":2, "sort_select":1},
 "Pack the Doll":           {"reach_grasp":2, "place_stack":2, "deform":1},
 "Fruit Sorting":           {"reach_grasp":3, "sort_select":3, "place_stack":1},
 "Disconnect Ethernet":     {"reach_grasp":3, "insert_align":2, "articulate":1},
 "Color Arrangement":       {"reach_grasp":3, "sort_select":2, "place_stack":2},
 "Place Photo Frames":      {"reach_grasp":3, "place_stack":2},
 "Organize Bookshelf":      {"reach_grasp":3, "place_stack":2, "sort_select":1},
 "Toolbox Storage":         {"reach_grasp":3, "place_stack":2, "sort_select":1},
 "Plug Charger":            {"reach_grasp":2, "insert_align":3, "press_toggle":1},
 "Pick Out Battery":        {"reach_grasp":2, "insert_align":1, "sort_select":2},
 "Unlock":                  {"reach_grasp":2, "articulate":3, "press_toggle":1},
 "Arrange Test Tubes":      {"reach_grasp":3, "insert_align":2, "place_stack":2},
 "Open Pill Bottle":        {"reach_grasp":2, "articulate":2, "press_toggle":2},
 "Organize Tools":          {"reach_grasp":3, "place_stack":2, "sort_select":1},
 "Fold Towel":              {"deform":3, "bimanual_carry":2, "reach_grasp":1},
 "Organize Stationery":     {"reach_grasp":3, "sort_select":2, "place_stack":2},
 "Pack Bag":                {"reach_grasp":2, "place_stack":2, "bimanual_carry":2, "deform":1},
 "Zip Up":                  {"deform":3, "bimanual_carry":2, "press_toggle":1},
 "Paper Cup Stacking":      {"reach_grasp":3, "place_stack":3},
 "Clear Plates":            {"reach_grasp":3, "place_stack":2, "bimanual_carry":1},
 "Spell robot":             {"reach_grasp":3, "place_stack":2, "sort_select":2},
 "Store Racket":            {"reach_grasp":2, "place_stack":2, "insert_align":1},
 "Conveyor Food Sorting":   {"reach_grasp":3, "sort_select":3, "bimanual_carry":1},
 "Stack Cups":              {"reach_grasp":3, "place_stack":3},
 "Plug In Ethernet":        {"reach_grasp":2, "insert_align":3, "press_toggle":1},
 "Stack Bowls":             {"reach_grasp":3, "place_stack":3},
 "Store Earphones":         {"reach_grasp":2, "place_stack":2, "deform":1},
 "Pack Phone":              {"reach_grasp":2, "place_stack":2, "insert_align":1},
 "Remove Pinned Note":      {"reach_grasp":2, "articulate":2, "press_toggle":1},
 "Organize Pencil Case":    {"reach_grasp":3, "place_stack":2, "insert_align":1},
 "Syringe Water Transfer":  {"reach_grasp":2, "fluid":3, "bimanual_carry":1},
}

# per-task mean success across models
succ = {}
for m in models:
    for t in m["task_metrics"]:
        succ.setdefault(t["task"], []).append(t["success_rate"])
task_mean = {t: statistics.mean(v) for t, v in succ.items()}

# skill co-occurrence: how many tasks each skill appears in, weighted
skill_tasks = {s: [] for s in SKILLS}
for t, row in MATRIX.items():
    for s, w in row.items():
        skill_tasks[s].append(t)
print("== skill coverage (tasks) ==")
for s in SKILLS:
    ts = skill_tasks[s]
    mean_succ = statistics.mean(task_mean[t] for t in ts) if ts else float("nan")
    print(f"{s:15s} n={len(ts):2d}  mean_task_succ={mean_succ:5.2f}")

# correlate: presence of each skill (weight>=2) with task difficulty
print("\n== skill vs task difficulty (mean success; lower=difficult) ==")
for s in SKILLS:
    with_s = [task_mean[t] for t, r in MATRIX.items() if r.get(s, 0) >= 2]
    without = [task_mean[t] for t, r in MATRIX.items() if r.get(s, 0) < 2]
    if with_s and without:
        print(f"{s:15s} with={statistics.mean(with_s):5.2f} (n={len(with_s):2d})  "
              f"without={statistics.mean(without):5.2f} (n={len(without):2d})  "
              f"delta={statistics.mean(with_s)-statistics.mean(without):+.2f}")

# number of skills vs difficulty
print("\n== task breadth vs difficulty ==")
for k in (2, 3, 4):
    ts = [task_mean[t] for t, r in MATRIX.items() if len(r) == k]
    if ts:
        print(f"#skills={k}: mean={statistics.mean(ts):5.2f} n={len(ts)}")

# leaderboard flatness
allmeans = list(task_mean.values())
print(f"\nper-task mean success: min={min(allmeans):.1f} max={max(allmeans):.1f} "
      f"median={statistics.median(allmeans):.1f} sd={statistics.pstdev(allmeans):.2f}")
ratios = [m["avg_step_score"] / m["avg_success_rate"] for m in models]
print(f"step/success ratio: mean={statistics.mean(ratios):.3f} sd={statistics.pstdev(ratios):.3f}")

# save compact json
out = {
    "task_mean": task_mean,
    "skill_tasks": {s: skill_tasks[s] for s in SKILLS},
    "flatness": {
        "min": min(allmeans), "max": max(allmeans),
        "median": statistics.median(allmeans),
        "sd": statistics.pstdev(allmeans),
    },
    "step_over_success_mean": statistics.mean(ratios),
}
json.dump(out, open(os.path.join(HERE, "roadmap_lb.json"), "w"), indent=1)
print("\nwrote roadmap_lb.json")
