#!/usr/bin/env python3
"""Round-55 STEPNORM toy simulation v2 (declared generative model, B-level).

Grounding: real 32-task UniBot-V1 list, per-task mean success from the public
leaderboard snapshot (workspace/exp/lb_20261102.json), and the organizer rubric
lengths/weights.  Per-step success probabilities, norm-breach hazards and the
human-undo response are DECLARED, not fitted to robot data.

Models (per step, two controls):
  effort e_k in {0,1}  : scarce time/compute, sum e = max(1, n-1)
  caution c_k in {0,1} : free but costs success probability; reduces norm risk
  p_k = p0 * (1 + 0.30 e_k) * (1 - 0.25 c_k)
  h_k = h0 * (1 - 0.60 c_k)     hard-norm breach
  s_k = s0 * (1 - 0.50 c_k)     soft-norm breach

Step score is prefix-closed: S = sum_k w_k * prod_{j<=k} done_j.
OOD human interference: after each completed step, undo hazard
  q = 1 - (1 - (q0 + kappa_h * hard_breach_so_far + kappa_s * soft_so_far))
          * (1 - p_hard_undo * h_k)
with one recovery attempt.  A hard breach can therefore erase a completed step.
"""
import itertools
import json
import math
import os
import random
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = HERE
LB_CANDIDATES = [os.path.join(HERE, f) for f in
                 ("lb_20261102.json", "unibot_leaderboard_20261102.json")]

RUBRIC_LEN = {
    "Hang the Cup": 2, "Fruit Basket Collection": 2, "Pack the Doll": 2,
    "Fruit Sorting": 3, "Disconnect Ethernet": 2, "Color Arrangement": 3,
    "Place Photo Frames": 3, "Organize Bookshelf": 2, "Toolbox Storage": 4,
    "Plug Charger": 3, "Pick Out Battery": 3, "Unlock": 3,
    "Arrange Test Tubes": 3, "Open Pill Bottle": 2, "Organize Tools": 4,
    "Fold Towel": 5, "Organize Stationery": 5, "Pack Bag": 4, "Zip Up": 2,
    "Paper Cup Stacking": 3, "Clear Plates": 3, "Spell robot": 4,
    "Store Racket": 2, "Conveyor Food Sorting": 2, "Stack Cups": 3,
    "Plug In Ethernet": 3, "Stack Bowls": 3, "Store Earphones": 4,
    "Pack Phone": 3, "Remove Pinned Note": 2, "Organize Pencil Case": 3,
    "Syringe Water Transfer": 2,
}
WEIGHTS = {2: [50.0, 50.0], 3: [30.0, 30.0, 40.0],
           4: [25.0] * 4, 5: [20.0] * 5}

H_CRIT, H_NON = 0.150, 0.010
S_CRIT, S_NON = 0.200, 0.020
Q0, KAPPA_H, KAPPA_S = 0.15, 0.45, 0.05
RECOVERY = 0.50
EPS_HARD = 0.25
P_HARD_NOMINAL = 0.80
N_EP = 2500
N_EP_SWEEP = 1200
SEED = 20261111


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def load_lb():
    for p in LB_CANDIDATES:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("leaderboard snapshot not found")


LB = load_lb()
MODELS = LB["models"]
TASKS = [t["task"] for t in MODELS[0]["task_metrics"]]


def mean_success(name):
    vals = [t["success_rate"] for m in MODELS for t in m["task_metrics"]
            if t["task"] == name]
    return statistics.mean(vals) / 100.0


TASKINFO = []
for name in TASKS:
    n = RUBRIC_LEN[name]
    p0 = clip(clip(mean_success(name), 0.03, 0.90) ** (1.0 / n), 0.05, 0.98)
    TASKINFO.append(dict(name=name, n=n, w=WEIGHTS[n], p0=p0))


def plans(n):
    budget = max(1, n - 1)
    for e in itertools.product((0, 1), repeat=n):
        if sum(e) != budget:
            continue
        for c in itertools.product((0, 1), repeat=n):
            yield (e, c)


def critical(t, k):
    """Norm-critical steps: final placement/handover always; the first step of
    a long task also touches the shared workspace."""
    return k == t["n"] - 1 or (t["n"] >= 4 and k == 0)


def params(t, ec):
    e, c = ec
    p, h, s = [], [], []
    for k, (ek, ck) in enumerate(zip(e, c)):
        p.append(clip(t["p0"] * (1 + 0.30 * ek) * (1 - 0.12 * ck), 0.02, 0.99))
        h0 = H_CRIT if critical(t, k) else H_NON
        s0 = S_CRIT if critical(t, k) else S_NON
        h.append(clip(h0 * (1 - 0.85 * ck), 0.0, 0.50))
        s.append(clip(s0 * (1 - 0.80 * ck), 0.0, 0.50))
    return p, h, s


def predicted(t, ec, q0=0.0, kappa_h=0.0, kappa_s=0.0, p_hard_undo=0.0):
    p, h, s = params(t, ec)
    prod, val = 1.0, 0.0
    hard_seen, soft_seen = 0.0, 0.0
    for k in range(t["n"]):
        prod *= p[k]
        q_int = q0 + kappa_h * hard_seen + kappa_s * soft_seen
        q = 1.0 - (1.0 - min(1.0, q_int)) * (1.0 - p_hard_undo * h[k])
        prod *= (1.0 - min(1.0, q))
        val += t["w"][k] * prod
        hard_seen = 1.0 - (1.0 - hard_seen) * (1.0 - h[k])
        soft_seen += s[k]
    return val, hard_seen


def choose(t, policy):
    best, best_key = None, None
    for ec in plans(t["n"]):
        p, h, s = params(t, ec)
        if policy == "success":
            key = (math.prod(p), -sum(h))
        elif policy == "step":
            key = (predicted(t, ec)[0], -sum(h))
        elif policy == "stepnorm":
            val, H = predicted(t, ec, Q0, KAPPA_H, KAPPA_S, P_HARD_NOMINAL)
            if H > EPS_HARD:
                continue
            key = (val, -H)
        else:
            raise ValueError(policy)
        if best_key is None or key > best_key:
            best, best_key = ec, key
    if best is None:   # relax the budget only if no plan is feasible
        for ec in plans(t["n"]):
            val, H = predicted(t, ec, Q0, KAPPA_H, KAPPA_S, P_HARD_NOMINAL)
            key = (val, -H)
            if best_key is None or key > best_key:
                best, best_key = ec, key
    return best


def evaluate(t, ec, scenario, rng, p_hard_undo, episodes):
    p, h, s = params(t, ec)
    n, w = t["n"], t["w"]
    scores, succ, hard_eps, hard_steps, soft_steps, steps = [], [], [], [], [], []
    for _ in range(episodes):
        done = [False] * n
        hard_any = False
        hard_n = soft_n = executed = 0
        k = 0
        while k < n:
            if rng.random() >= p[k]:
                break
            executed += 1
            done[k] = True
            hard_hit = rng.random() < h[k]
            if hard_hit:
                hard_any, hard_n = True, hard_n + 1
            if rng.random() < s[k]:
                soft_n += 1
            if scenario == "ood":
                q_int = Q0 + KAPPA_H * (1.0 if hard_any else 0.0) + KAPPA_S * soft_n
                q = 1.0 - (1.0 - min(1.0, q_int)) * (1.0 - p_hard_undo * h[k])
                if rng.random() < min(1.0, q):
                    done[k] = False
                    if rng.random() < RECOVERY and rng.random() < p[k]:
                        done[k] = True
                    else:
                        break
            k += 1
        scores.append(sum(wj if dj else 0.0 for wj, dj in zip(w, done)))
        succ.append(all(done))
        hard_eps.append(1.0 if hard_any else 0.0)
        hard_steps.append(hard_n)
        soft_steps.append(soft_n)
        steps.append(executed)
    mean_steps = statistics.mean(steps)
    return dict(
        step_score=round(statistics.mean(scores), 3),
        success=round(statistics.mean(succ), 4),
        hard_violation_episode=round(statistics.mean(hard_eps), 4),
        hard_per_100_steps=round(100 * statistics.mean(hard_steps) / mean_steps, 3)
        if mean_steps else 0.0,
        soft_per_100_steps=round(100 * statistics.mean(soft_steps) / mean_steps, 3)
        if mean_steps else 0.0,
        mean_steps=round(mean_steps, 3),
    )


def main():
    rng = random.Random(SEED)
    policies = ["success", "step", "stepnorm"]
    chosen = {pol: {t["name"]: choose(t, pol) for t in TASKINFO}
              for pol in policies}
    out = {"meta": {
        "date": "2026-11-11", "seed": SEED,
        "episodes_per_task": N_EP, "episodes_per_task_sweep": N_EP_SWEEP,
        "n_tasks": len(TASKINFO),
        "declared_hazard": {
            "h_crit": H_CRIT, "h_non": H_NON, "s_crit": S_CRIT, "s_non": S_NON, "q0": Q0, "kappa_h": KAPPA_H,
            "kappa_s": KAPPA_S, "recovery": RECOVERY, "eps_hard": EPS_HARD,
            "planner_assumed_p_hard_undo": P_HARD_NOMINAL},
        "note": ("Declared generative toy model, NOT a robot/benchmark result. "
                 "Real grounding is only the task list, leaderboard difficulty "
                 "and rubric lengths/weights. The p_hard_undo sweep is the "
                 "central sensitivity result: norm-aware planning only pays "
                 "when a social breach actually triggers a costly human undo."),
    }, "scenarios": {}, "penalty_sweep_ood": []}

    for scenario in ("id", "ood"):
        rows = {}
        for pol in policies:
            rs = [evaluate(t, chosen[pol][t["name"]], scenario, rng,
                           P_HARD_NOMINAL, N_EP) for t in TASKINFO]
            rows[pol] = {k: round(statistics.mean(r[k] for r in rs), 3)
                         for k in rs[0]}
        out["scenarios"][scenario] = rows

    for penalty in (0.0, 0.2, 0.4, 0.6, 0.8, 0.95, 1.0):
        row = {"p_hard_undo": penalty}
        for pol in policies:
            rs = [evaluate(t, chosen[pol][t["name"]], "ood", rng,
                           penalty, N_EP_SWEEP) for t in TASKINFO]
            row[pol] = {k: round(statistics.mean(r[k] for r in rs), 3)
                        for k in ("step_score", "success",
                                  "hard_violation_episode", "hard_per_100_steps")}
        out["penalty_sweep_ood"].append(row)

    # per-task OOD delta at the nominal penalty
    deltas = []
    for t in TASKINFO:
        a = evaluate(t, chosen["step"][t["name"]], "ood", rng,
                     P_HARD_NOMINAL, N_EP_SWEEP)
        b = evaluate(t, chosen["stepnorm"][t["name"]], "ood", rng,
                     P_HARD_NOMINAL, N_EP_SWEEP)
        deltas.append({"task": t["name"], "n": t["n"],
                       "delta_step_score": round(b["step_score"] - a["step_score"], 2),
                       "hard_step": a["hard_violation_episode"],
                       "hard_stepnorm": b["hard_violation_episode"]})
    deltas.sort(key=lambda r: r["delta_step_score"])
    out["per_task_ood_stepnorm_minus_step"] = deltas
    out["summary"] = {
        "n_tasks": len(deltas),
        "stepnorm_worse_tasks": sum(1 for r in deltas if r["delta_step_score"] < 0),
        "stepnorm_better_tasks": sum(1 for r in deltas if r["delta_step_score"] > 0),
    }
    with open(os.path.join(OUTDIR, "round55_stepnorm_results.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
