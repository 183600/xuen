#!/usr/bin/env python3
"""SCORE-VLA round-16 synthetic mechanism check (B-level evidence).

Question it answers: given the real challenge structure —
  * per-task OFFICIAL rubric = weighted subgoal sequence (100 pts),
  * 5 documented generalization axes including REGRESSIVE human interference
    that UNDOES already-completed subgoals,
  * a fixed deployment compute/latency budget shared over N ports —
does a rubric-aligned, scenario-conditioned deployment layer beat
(a) a monotone progress policy and (b) uniform compute allocation?

It does NOT prove real-robot gains. It is a declared generative toy model.
Run: PYTHONPATH=.pylibs python3 score_sim.py
"""
import json
import os
import numpy as np

RNG = np.random.default_rng(20261103)
HERE = os.path.dirname(os.path.abspath(__file__))
LB = os.path.join(HERE, "lb_20261102.json")

# ---------------------------------------------------------------------------
# 0. Real grounding: task order + per-task mean success from the leaderboard.
# ---------------------------------------------------------------------------
lb = json.load(open(LB))
models = lb["models"]
tasks = [t["task"] for t in models[0]["task_metrics"]]


def task_mean_success(name):
    vals = []
    for m in models:
        for t in m["task_metrics"]:
            if t["task"] == name:
                vals.append(t["success_rate"])
    return float(np.mean(vals)) / 100.0


# Rubric length per task. Observed from retrieved info.json (12 tasks);
# unobserved tasks assigned a plausible pattern deterministically.
RUBRIC_LEN = {
    "Hang the Cup": 2, "Fruit Basket Collection": 2, "Pack the Doll": 2,
    "Fruit Sorting": 3, "Disconnect Ethernet": 2, "Color Arrangement": 3,
    "Place Photo Frames": 2, "Organize Bookshelf": 2, "Toolbox Storage": 4,
    "Plug Charger": 2, "Pick Out Battery": 2, "Unlock": 3,
    "Arrange Test Tubes": 3, "Open Pill Bottle": 3, "Organize Tools": 4,
    "Fold Towel": 5, "Organize Stationery": 3, "Pack Bag": 4, "Zip Up": 2,
    "Paper Cup Stacking": 3, "Clear Plates": 3, "Spell robot": 4,
    "Store Racket": 2, "Conveyor Food Sorting": 3, "Stack Cups": 3,
    "Plug In Ethernet": 3, "Stack Bowls": 3, "Store Earphones": 2,
    "Pack Phone": 3, "Remove Pinned Note": 2, "Organize Pencil Case": 3,
    "Syringe Water Transfer": 2,
}
RUBRIC_TEMPLATES = {
    2: [50, 50],
    3: [30, 30, 40],
    4: [25, 25, 25, 25],
    5: [20, 20, 20, 20, 20],
}


# ---------------------------------------------------------------------------
# 1. Per-task subgoal success probability.
#    If subgoals were independent, ID task success = prod(p_j). Invert to get
#    a per-task base p so that the toy ID success matches the real field mean.
# ---------------------------------------------------------------------------
def base_p_for(task, n):
    s = task_mean_success(task)
    s = float(np.clip(s, 0.03, 0.9))
    return float(np.clip(s ** (1.0 / n), 0.05, 0.98))


TASKINFO = []
for i, name in enumerate(tasks):
    n = RUBRIC_LEN[name]
    w = np.array(RUBRIC_TEMPLATES[n], dtype=float)
    p0 = base_p_for(name, n)
    TASKINFO.append(dict(name=name, n=n, w=w, p0=p0, idx=i))

# Documented scenario axes. Facts observed in info.json:
#   * `unseen_object_3` present on many tasks (object-identity shift),
#   * `human_1_note` (soft: relocate object) and `human_4_note`
#     (hard/regressive: knock over / undo progress) on nearly all tasks.
# Every task gets a soft human variant; ~60% get unseen_object; ~40% get a
# regressive human variant; a background/distractor axis on ~50%.
for t in TASKINFO:
    axes = {"human_soft": True}
    axes["unseen_object"] = RNG.random() < 0.60
    axes["human_regress"] = RNG.random() < 0.40
    axes["background"] = RNG.random() < 0.50
    axes["distractor"] = RNG.random() < 0.50
    t["axes"] = axes

# Success multipliers per active axis (declared, not fitted).
AXIS_MULT = {
    "human_soft": 0.90,   # relocation: recoverable, mild
    "unseen_object": 0.70,
    "human_regress": 0.80,
    "background": 0.92,
    "distractor": 0.82,
}
# Probability an already-completed subgoal is UNDONE by regressive human axes.
REGRESS_Q = {"human_regress": 0.50}
REGRESS_TRIGGER = 0.60   # P(human attempts an undo after a completed subgoal)


def episode_success_prob(t, scenario):
    mult = 1.0
    for ax in scenario:
        mult *= AXIS_MULT[ax]
    return float(np.clip(t["p0"] * mult, 0.02, 0.99))


# ---------------------------------------------------------------------------
# 2. Deployment simulation with a fixed attempt budget.
# ---------------------------------------------------------------------------
def run_policy(t, scenario, alloc, policy, rng, detect=0.9):
    """alloc: attempts per subgoal (len n). policy in {'monotone','recover'}.
    Returns (step_score, success_bool, attempts_used)."""
    n = t["n"]
    p = episode_success_prob(t, scenario)
    done = np.zeros(n, dtype=bool)
    used = 0
    regressive = "human_regress" in scenario
    for j in range(n):
        # attempts allocated to subgoal j (extra attempts reserved for recovery)
        m = max(1, int(alloc[j]))
        for _ in range(m):
            if used >= alloc.sum():
                break
            used += 1
            if rng.random() < p:
                done[j] = True
                break
        if not done[j]:
            break  # cannot proceed past an unachieved ordered subgoal
        # regressive interference after completing subgoal j
        if regressive and rng.random() < REGRESS_TRIGGER:
            if policy == "recover" and rng.random() < detect:
                # detect + redo: spend attempts until re-done
                redone = False
                for _ in range(m):
                    if used >= alloc.sum():
                        break
                    used += 1
                    if rng.random() < p:
                        redone = True
                        break
                done[j] = redone
                if not redone:
                    break
            else:
                done[j] = False
                break  # monotone policy does not redo -> credit lost
    score = float((t["w"] * done).sum())
    success = bool(done.all())
    return score, success, used


def alloc_uniform(t, scenario):
    return np.full(t["n"], 2.0)   # flat 2 attempts/subgoal (spare for recovery)


def alloc_value(t, scenario):
    """VoI: more attempts to high-weight, low-success subgoals."""
    p = episode_success_prob(t, scenario)
    fails = 1.0 - p
    a = t["w"] * fails
    a = a / a.sum() * (2.0 * t["n"])       # ~2 attempts/subgoal average
    return np.clip(a, 1.0, None)


def alloc_scenario_conditioned(t, scenario):
    a = alloc_value(t, scenario)
    n_ood = sum(1 for ax in scenario if ax != "human_soft")
    a = a * (1.0 + 0.5 * n_ood)             # invest where documented OOD
    return np.clip(a, 1.0, None)


def evaluate(scenario_of, policy, allocator, n_eps=20000, seed=1):
    rng = np.random.default_rng(seed)
    scores, succ, used = [], [], []
    for _ in range(n_eps):
        t = TASKINFO[rng.integers(len(TASKINFO))]
        scenario = scenario_of(t, rng)
        alloc = allocator(t, scenario)
        s, ok, u = run_policy(t, scenario, alloc, policy, rng)
        scores.append(s); succ.append(ok); used.append(u)
    return dict(step=float(np.mean(scores)), succ=float(np.mean(succ)),
                attempts=float(np.mean(used)))


def id_scenario(t, rng):
    return []


def mild_ood(t, rng):
    ax = [a for a in t["axes"] if t["axes"][a] and a != "human_regress"]
    return ax


def full_ood(t, rng):
    return [a for a in t["axes"] if t["axes"][a]]


# ---------------------------------------------------------------------------
# 3. Experiment 1: value alignment under non-monotone interference.
# ---------------------------------------------------------------------------
results = {"meta": {
    "date": "2026-11-03",
    "seed": 20261103, "n_eps": 20000,
    "note": "declared generative toy; not a benchmark result",
}}

exp1 = []
for name, scen in [("ID", id_scenario), ("MILD_OOD", mild_ood),
                   ("FULL_OOD", full_ood)]:
    row = {"scenario": name}
    row["monotone_uniform"] = evaluate(scen, "monotone", alloc_uniform, seed=11)
    row["recover_uniform"] = evaluate(scen, "recover", alloc_uniform, seed=11)
    row["recover_value"] = evaluate(scen, "recover", alloc_value, seed=11)
    row["recover_cond"] = evaluate(scen, "recover",
                                   alloc_scenario_conditioned, seed=11)
    exp1.append(row)
results["exp1_value_alignment"] = exp1

# ---------------------------------------------------------------------------
# 4. Experiment 2: recover detection quality sweep on regressive-only.
# ---------------------------------------------------------------------------
def regress_scenario(t, rng):
    return ["human_regress"] if t["axes"]["human_regress"] else []

exp2 = []
for d in [0.0, 0.3, 0.6, 0.9, 1.0]:
    r = evaluate(regress_scenario, "recover", alloc_value, seed=7)
    # note: detect is a global in run_policy; emulate via wrapper
    scores, succ = [], []
    rng = np.random.default_rng(7)
    for _ in range(20000):
        t = TASKINFO[rng.integers(len(TASKINFO))]
        scen = regress_scenario(t, rng)
        alloc = alloc_value(t, scen)
        s, ok, u = run_policy(t, scen, alloc, "recover", rng, detect=d)
        scores.append(s); succ.append(ok)
    exp2.append({"detect": d, "step": float(np.mean(scores)),
                 "succ": float(np.mean(succ))})
results["exp2_detection_sweep"] = exp2

# ---------------------------------------------------------------------------
# 5. Experiment 3: fixed global budget, allocation comparison.
#    Cap total attempts per episode at the uniform allocator's mean usage so
#    the comparison is budget-matched; then re-scale allocations to that cap.
# ---------------------------------------------------------------------------
def evaluate_capped(scenario_of, allocator, cap, n_eps=20000, seed=3):
    rng = np.random.default_rng(seed)
    scores, succ, used = [], [], []
    for _ in range(n_eps):
        t = TASKINFO[rng.integers(len(TASKINFO))]
        scen = scenario_of(t, rng)
        a = allocator(t, scen)
        a = np.maximum(a, 1.0)
        a = a / a.sum() * cap                    # budget-matched scaling
        a = np.maximum(a, 1.0)
        s, ok, u = run_policy(t, scen, a, "recover", rng)
        scores.append(s); succ.append(ok); used.append(u)
    return dict(step=float(np.mean(scores)), succ=float(np.mean(succ)),
                attempts=float(np.mean(used)))


cap = 2.0 * np.mean([t["n"] for t in TASKINFO])
exp3 = {
    "cap_attempts_per_episode": float(cap),
    "uniform": evaluate_capped(full_ood, alloc_uniform, cap, seed=5),
    "value": evaluate_capped(full_ood, alloc_value, cap, seed=5),
    "scenario_conditioned": evaluate_capped(
        full_ood, alloc_scenario_conditioned, cap, seed=5),
}
results["exp3_budget_matched"] = exp3

# ---------------------------------------------------------------------------
# 6. Data fact: leaderboard step-score vs success collinearity.
# ---------------------------------------------------------------------------
SR, SS = [], []
for m in models:
    for t in m["task_metrics"]:
        SR.append(t["success_rate"]); SS.append(t["step_score"])
SR = np.array(SR); SS = np.array(SS)
slope = float(np.polyfit(SR, SS, 1)[0])
results["data_fact_step_vs_success"] = {
    "pearson_r": float(np.corrcoef(SR, SS)[0, 1]),
    "slope": slope, "intercept": float(np.polyfit(SR, SS, 1)[1]),
    "mean_step_over_success": float(np.mean(SS / SR)),
}

with open(os.path.join(HERE, "score_sim_results.json"), "w") as f:
    json.dump(results, f, indent=1, ensure_ascii=False)

# ---- pretty print ----
df = results["data_fact_step_vs_success"]
print(f"[data] leaderboard step~=success: r={df['pearson_r']:.4f} "
      f"slope={df['slope']:.3f} mean(step/succ)={df['mean_step_over_success']:.3f}")
print("\n[exp1] scenario x policy  (step score / success / attempts)")
for row in exp1:
    print(f"  {row['scenario']:9s}", end="")
    for k in ["monotone_uniform", "recover_uniform", "recover_value",
              "recover_cond"]:
        v = row[k]
        print(f" | {k.split('_')[0][:4]}:{v['step']:5.1f}/{v['succ']:.2f}",
              end="")
    print()
print("\n[exp2] recovery detection sweep (regressive scenarios)")
for r in exp2:
    print(f"  detect={r['detect']:.1f}  step={r['step']:5.1f}  succ={r['succ']:.3f}")
print(f"\n[exp3] budget-matched (cap={exp3['cap_attempts_per_episode']:.1f} attempts/ep)")
for k in ["uniform", "value", "scenario_conditioned"]:
    v = exp3[k]
    print(f"  {k:20s} step={v['step']:5.1f} succ={v['succ']:.3f} "
          f"used={v['attempts']:.2f}")
