#!/usr/bin/env python3
"""Mechanism check: reactive redo vs proactive guarding under a human undo process.

Declared generative toy model, not a real-robot or benchmark result.

It asks one question that the official `human_*` notes make salient: if a
human can REVERSE a completed subgoal, is it better to
  (a) react after detecting the reversal and redo it, or
  (b) spend a little time "committing" the completed subgoal so the reversal
      is less likely to succeed?

The task weights are the real rubric weights of the 13 tasks whose official
notes contain an explicit progress-undo (see hri_disturbance_audit.py).

Run: PYTHONPATH=.pylibs python3 exp/hri_guard_sim.py
"""
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "hri_guard_sim.json"

# Rubric weights of the 13 explicit-undo tasks (official info.json fixture).
UNDO_TASKS = [
    [50, 50],                    # T08 OrganizeBookshelf
    [30, 30, 40],                # T10 PlugCharger
    [30, 30, 40],                # T11 PickOutBatteries
    [30, 30, 40],                # T12 Unlock
    [50, 50],                    # T14 PourOutMedicine
    [20, 20, 20, 20, 20],        # T16 FoldTowel
    [20, 20, 20, 20, 20],        # T17 OrganizeStationery
    [50, 50],                    # T19 ZipUp
    [50, 50],                    # T24 ConveyorSorting
    [30, 30, 40],                # T25 StoreCups
    [30, 30, 40],                # T26 PlugInEthernet
    [30, 30, 40],                # T27 StackBowls
    [30, 30, 40],                # T29 PackPhone
]

DEFAULTS = dict(
    n=20000,
    T=24,
    p_succ=0.85,        # per-step probability of completing the current subgoal
    q=0.90,             # probability a human undo succeeds without a guard
    q_guard=0.10,       # probability a human undo succeeds against a guard
    recency_bias=0.70,  # human prefers to undo the most recently completed step
    seed=20261113,
)


def _order(weights, mode):
    if mode == "weight_asc":
        return np.argsort(weights, kind="stable")
    return np.arange(len(weights))


def run(policy, lam, c_guard, order_mode="weight_asc", him_accuracy=1.0,
        lam_hat=None, **kw):
    cfg = dict(DEFAULTS)
    cfg.update(kw)
    n, T = cfg["n"], cfg["T"]
    rng = np.random.default_rng(cfg["seed"])
    if lam_hat is None:
        lam_hat = lam

    G = max(len(t) for t in UNDO_TASKS)
    task_idx = rng.integers(0, len(UNDO_TASKS), n)
    W = np.zeros((n, G))
    order = np.full((n, G), -1, dtype=int)
    for i, t in enumerate(UNDO_TASKS):
        m = task_idx == i
        W[m, :len(t)] = t
        order[m, :len(t)] = _order(np.array(t), order_mode)

    done = np.zeros((n, G), dtype=bool)
    ever_done = np.zeros((n, G), dtype=bool)
    guarded = np.zeros((n, G), dtype=bool)
    guard_timer = np.zeros(n, dtype=int)
    guard_target = np.full(n, -1, dtype=int)
    last_done = np.full(n, -1, dtype=int)
    rows = np.arange(n)

    n_undo = np.zeros(n, dtype=int)
    n_guard = np.zeros(n, dtype=int)

    for t in range(T):
        remaining = T - t - 1
        guarding = guard_timer > 0

        # --- finish a guard that was started on an earlier step -------------
        if guarding.any():
            guard_timer[guarding] -= 1
            finished = guarding & (guard_timer == 0)
            if finished.any():
                guarded[rows[finished], guard_target[finished]] = True

        # --- work on the next incomplete subgoal ---------------------------
        active = ~guarding
        target = np.full(n, -1, dtype=int)
        for j in range(G):
            col = order[:, j]
            valid = col >= 0
            # reactive redoes undone steps; monotone never revisits them
            incomplete = ~done[rows, np.clip(col, 0, G - 1)] if policy != "monotone" \
                else ~ever_done[rows, np.clip(col, 0, G - 1)]
            pick = active & (target < 0) & valid & incomplete
            target[pick] = col[pick]

        can_work = active & (target >= 0)
        success = can_work & (rng.random(n) < cfg["p_succ"])
        if success.any():
            done[rows[success], target[success]] = True
            ever_done[rows[success], target[success]] = True
            last_done[success] = target[success]

        # --- decide whether to guard the just-completed subgoal ------------
        if policy in ("guard_last", "guard_smart", "guard_noisy") and success.any():
            cand = success & (remaining >= c_guard + 1)
            w = np.where(cand, W[rows, np.clip(target, 0, G - 1)], 0.0)
            should = np.zeros(n, dtype=bool)
            if policy == "guard_last":
                should = cand & (w > 0)
            else:
                R = max(1, remaining)
                lam_q = lam_hat * cfg["q"]
                lam_qg = lam_hat * cfg["q_guard"]
                saved = w * ((1.0 - lam_qg) ** R - (1.0 - lam_q) ** R)
                shadow = c_guard * (W.sum(axis=1) / T)
                should = cand & (w > 0) & (saved > shadow)
            if policy == "guard_noisy":
                hit = rng.random(n) < him_accuracy
                # on a miss, waste the same guard budget on an arbitrary
                # completed, unguarded subgoal (the cost of a bad intent model)
                miss = should & ~hit
                should = should & hit
                for i in np.flatnonzero(miss):
                    elig = np.flatnonzero(done[i] & ~guarded[i])
                    if len(elig):
                        g = int(rng.choice(elig))
                        guard_timer[i] = c_guard
                        guard_target[i] = g
                        n_guard[i] += c_guard
            start = should & (guard_timer == 0)
            if start.any():
                guard_timer[start] = c_guard
                guard_target[start] = target[start]
                n_guard[start] += c_guard

        # --- human intervention -------------------------------------------
        event = rng.random(n) < lam
        has_done = done.any(axis=1)
        event &= has_done
        if event.any():
            idx = np.flatnonzero(event)
            dd = done[idx]
            # most-recent target with probability recency_bias, else uniform
            rand = rng.random((len(idx), G))
            rand[~dd] = 2.0
            choice = np.argmin(rand, axis=1)
            want_recent = rng.random(len(idx)) < cfg["recency_bias"]
            recent = last_done[idx]
            valid_recent = want_recent & (recent >= 0)
            if valid_recent.any():
                rr = np.flatnonzero(valid_recent)
                vt = recent[rr]
                ok = done[idx[rr], np.clip(vt, 0, G - 1)]
                choice[rr[ok]] = vt[ok]
            q_eff = np.where(guarded[idx, choice], cfg["q_guard"], cfg["q"])
            undo = rng.random(len(idx)) < q_eff
            for k, i in enumerate(idx):
                if undo[k]:
                    g = int(choice[k])
                    done[i, g] = False
                    n_undo[i] += 1
                    if last_done[i] == g:
                        last_done[i] = -1

    scores = (done * W).sum(axis=1)
    n_steps = (W > 0).sum(axis=1)
    proper = np.arange(G)[None, :] < n_steps[:, None]
    success = (done | ~proper).all(axis=1)
    return {
        "policy": policy,
        "lam": lam,
        "lam_hat": lam_hat,
        "T": T,
        "c_guard": c_guard,
        "q_guard": cfg["q_guard"],
        "order": order_mode,
        "him_accuracy": him_accuracy,
        "step_score": round(float(scores.mean()), 3),
        "success_rate": round(float(success.mean()), 4),
        "undo_per_ep": round(float(n_undo.mean()), 3),
        "guard_steps_per_ep": round(float(n_guard.mean()), 3),
    }


def aggregate(policy, lam, c_guard, seeds=(20261113, 7, 42), **kw):
    vals = [run(policy, lam, c_guard, seed=s, **kw) for s in seeds]
    first = vals[0]

    def ms(key):
        xs = [v[key] for v in vals]
        return round(float(np.mean(xs)), 3), round(float(np.std(xs, ddof=1)), 3)

    step_m, step_s = ms("step_score")
    succ_m, succ_s = ms("success_rate")
    return {
        "policy": policy,
        "lam": lam,
        "lam_hat": first["lam_hat"],
        "T": first["T"],
        "q_guard": first["q_guard"],
        "him_accuracy": first["him_accuracy"],
        "step_mean": step_m,
        "step_sd": step_s,
        "success_mean": succ_m,
        "success_sd": succ_s,
    }


def main():
    budget = []
    for T in (8, 10, 14):
        for lam in (0.05, 0.15, 0.25):
            for policy in ("monotone", "reactive", "guard_last", "guard_smart"):
                budget.append(run(policy, lam, 2, T=T, q_guard=0.10,
                                  recency_bias=0.80))

    calibration = []
    for lam_hat in (0.02, 0.05, 0.10, 0.15, 0.25, 0.40):
        calibration.append(run("guard_smart", 0.15, 2, T=14, q_guard=0.10,
                               recency_bias=0.80, lam_hat=lam_hat))

    target_acc = []
    for acc in (0.4, 0.6, 0.8, 1.0):
        target_acc.append(run("guard_noisy", 0.15, 2, T=14, q_guard=0.10,
                              recency_bias=0.80, him_accuracy=acc))

    strength = []
    for qg in (0.05, 0.10, 0.30, 0.60):
        strength.append(run("guard_smart", 0.15, 2, T=14, q_guard=qg,
                            recency_bias=0.80))

    order_null = []
    for mode in ("original", "weight_asc"):
        order_null.append(run("reactive", 0.15, 2, T=10, q_guard=0.10,
                              order_mode=mode))
    weights_nondecreasing = all(
        all(w[i] <= w[i + 1] for i in range(len(w) - 1)) for w in UNDO_TASKS)

    seeds = (20261113, 7, 42)
    ms_budget = []
    for T, lam in ((8, 0.15), (10, 0.25), (14, 0.15), (14, 0.25)):
        for policy in ("reactive", "guard_last", "guard_smart"):
            ms_budget.append(aggregate(policy, lam, 2, seeds=seeds, T=T,
                                       q_guard=0.10, recency_bias=0.80))
    ms_cal = []
    for lam_hat in (0.02, 0.05, 0.10, 0.15, 0.25, 0.40):
        ms_cal.append(aggregate("guard_smart", 0.15, 2, seeds=seeds, T=14,
                                q_guard=0.10, recency_bias=0.80,
                                lam_hat=lam_hat))
    ms_acc = []
    for acc in (0.4, 0.6, 0.8, 1.0):
        ms_acc.append(aggregate("guard_noisy", 0.15, 2, seeds=seeds, T=14,
                                q_guard=0.10, recency_bias=0.80,
                                him_accuracy=acc))

    out = {
        "meta": {
            "date": "2026-11-13",
            "seed": DEFAULTS["seed"],
            "multiseed": seeds,
            "n_episodes": DEFAULTS["n"],
            "note": "declared generative toy; not a robot/benchmark result",
            "undo_tasks": UNDO_TASKS,
            "rubric_weights_nondecreasing": weights_nondecreasing,
        },
        "guard_budget": budget,
        "hazard_calibration": calibration,
        "target_accuracy": target_acc,
        "guard_strength": strength,
        "order_null": order_null,
        "multiseed_budget": ms_budget,
        "multiseed_calibration": ms_cal,
        "multiseed_target_accuracy": ms_acc,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print("| T | lambda | policy | step | success | undos | guard steps |")
    print("|---:|---:|---|---:|---:|---:|---:|")
    for r in budget:
        print("| {T} | {lam} | {policy} | {step_score} | {success_rate} | "
              "{undo_per_ep} | {guard_steps_per_ep} |".format(**r))
    print("\nHazard-calibration ablation (actual lambda=0.15, T=14):")
    for r in calibration:
        print("  lam_hat={lam_hat}: step={step_score} success={success_rate} "
              "guard={guard_steps_per_ep}".format(**r))
    print("\nTarget-identity accuracy ablation (actual lambda=0.15, T=14):")
    for r in target_acc:
        print("  acc={him_accuracy}: step={step_score} success={success_rate} "
              "guard={guard_steps_per_ep}".format(**r))
    print("\nGuard-strength ablation (lambda=0.15, T=14):")
    for r in strength:
        print("  q_guard={q_guard}: step={step_score} success={success_rate} "
              "guard={guard_steps_per_ep}".format(**r))
    print("\nOrder null result (rubric weights nondecreasing = {}):".format(
        weights_nondecreasing))
    for r in order_null:
        print("  order={order}: step={step_score} success={success_rate}".format(**r))
    print("\nMulti-seed (3 seeds, mean +/- sd):")
    for r in ms_budget:
        print("  T={T} lam={lam} {policy}: step={step_mean}+/-{step_sd} "
              "success={success_mean}+/-{success_sd}".format(**r))
    print("  hazard calibration:")
    for r in ms_cal:
        print("    lam_hat={lam_hat}: step={step_mean}+/-{step_sd}".format(**r))
    print("  target accuracy:")
    for r in ms_acc:
        print("    acc={him_accuracy}: step={step_mean}+/-{step_sd}".format(**r))


if __name__ == "__main__":
    main()
