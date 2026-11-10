#!/usr/bin/env python3
"""Round 43 toy check: scenario contract + innovation ledger (v20).

This is a *mechanism* check, not a robot benchmark. The failure-mode
probabilities and coverage numbers below are explicit assumptions; the point
is to check that the proposed ledger operators (transport tax, decision
quotient, falsification admission, leave-one-out attribution) behave
monotonically and produce a non-trivial innovation kernel.

Scenarios (UniBot ladder):
  P0  tabletop single-object pick/place, static base, fixed light
  P1  cluttered tabletop, occlusion + same-category object swap
  P2  mobile pick/place, moving base + clutter + changing viewpoint
  P3  dynamic interference (people / moving obstacles), replanning

Failure modes:
  F1 pose ambiguity (symmetry / multi-hypothesis)
  F2 sim-to-real gap (metric/friction/mass shift)
  F3 quantisation slip (INT8 / lookup interpolation)
  F4 retrieval hallucination (inapplicable template reused)
  F5 occlusion / unknown treated as free
  F6 long-horizon drift (map / calibration / distribution)
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "res_round43.json")
MODES = ["F1_pose_amb", "F2_sim_gap", "F3_quant_slip",
         "F4_rag_halluc", "F5_occlusion", "F6_drift"]

# Base active-probability per scenario rung (assumptions, documented in
# artifact). F3/F4 are *not* environmental modes: they are introduced by
# mechanisms (edge quantisation / template retrieval), so they start at 0.
P = {
    "P0": [0.10, 0.02, 0.00, 0.00, 0.05, 0.01],
    "P1": [0.20, 0.05, 0.00, 0.00, 0.22, 0.04],
    "P2": [0.20, 0.16, 0.00, 0.00, 0.26, 0.10],
    "P3": [0.25, 0.26, 0.00, 0.00, 0.36, 0.22],
}
RF = {"P0": 0.5, "P1": 1.0, "P2": 1.6, "P3": 2.4}
W = {"P0": 0.10, "P1": 0.20, "P2": 0.40, "P3": 0.30}
FAILSAFE = 0.97

# innovation: coverage per failure mode, false-block, normalised cost,
# additive hazard per failure mode at rung factor 1.0 (a mechanism that
# *introduces* risk), and an optional runtime cost factor.
INN = {
    "v18_ball": dict(cov=[0.95, 1.00, 0.00, 0.00, 0.60, 0.70],
                     fb=0.22, cost=0.15, add=[0, 0, 0, 0, 0, 0],
                     over=[0.20, 0.55, 0, 0, 0, 0.35]),
    "scv_sim": dict(cov=[0.00, 0.45, 0.00, 0.00, 0.30, 0.50],
                    fb=0.02, cost=0.10, add=[0, 0, 0, 0, 0, 0], over=[0]*6),
    "ckb_rag": dict(cov=[0.00, 0.00, 0.00, 0.00, 0.15, 0.15],
                    fb=0.02, cost=0.05, add=[0, 0, 0.005, 0.100, 0, 0], over=[0]*6),
    "ecr_edge": dict(cov=[0.75, 0.00, 0.85, 0.00, 0.00, 0.20],
                     fb=0.01, cost=0.10, add=[0, 0, 0.020, 0, 0, 0], over=[0]*6),
    "scx_transport": dict(cov=[0.00, 1.00, 0.00, 0.20, 0.00, 0.00],
                          fb=0.03, cost=0.12, add=[0, 0, 0, 0.040, 0, 0], over=[0]*6),
    "cdq_quotient": dict(cov=[0.00, 0.00, 0.30, 0.00, 0.00, 0.10],
                         fb=0.01, cost=0.02, add=[0, 0, 0.000, 0, 0, 0], over=[0]*6),
    "fal_ledger": dict(cov=[0.00, 0.00, 0.20, 1.00, 0.00, 0.00],
                       fb=0.03, cost=0.06, add=[0, 0, 0, 0, 0, 0], over=[0]*6),
}

# v20 core kernel; leave-one-out removes exactly one member
KERNEL = ["scv_sim", "ckb_rag", "ecr_edge",
          "scx_transport", "cdq_quotient", "fal_ledger"]
STRATEGIES = {
    "v18_ball": ["v18_ball"],
    "v19_flywheel": ["scv_sim", "ckb_rag", "ecr_edge"],
    "v20_transport": ["scv_sim", "ckb_rag", "ecr_edge", "scx_transport"],
    "v20_quotient": ["scv_sim", "ckb_rag", "ecr_edge",
                     "scx_transport", "cdq_quotient"],
    "v20_kernel": KERNEL,
}


def p_effective(strategy, rung):
    rf = RF[rung]
    out = []
    for f in range(len(MODES)):
        p = P[rung][f]
        for name in strategy:
            p += INN[name]["add"][f] * rf
        out.append(min(0.95, p))
    return out


def run_strategy(strategy, rung, n, seed=20261110):
    rng = random.Random(seed)
    peff = p_effective(strategy, rung)
    fb = 1.0
    cost = 0.0
    for name in strategy:
        fb *= (1.0 - INN[name]["fb"])
        cost += INN[name]["cost"]
    fb = 1.0 - fb
    if "cdq_quotient" in strategy:
        cost *= 0.35
    nom = deg = unsafe = 0
    for _ in range(n):
        active = [f for f in range(len(MODES)) if rng.random() < peff[f]]
        if not active:
            if rng.random() < fb:
                deg += 1
            else:
                nom += 1
            continue
        covered = True
        for f in active:
            hit = False
            for name in strategy:
                c = INN[name]["cov"][f]
                if c > 0.0 and rng.random() < c:
                    hit = True
                    break
            if not hit:
                covered = False
                break
        over_block = False
        if covered:
            for f in active:
                for name in strategy:
                    if rng.random() < INN[name]["over"][f]:
                        over_block = True
                        break
                if over_block:
                    break
        if covered and not over_block:
            if rng.random() < fb:
                deg += 1
            else:
                nom += 1
        elif covered:
            deg += 1
        elif rng.random() < FAILSAFE:
            deg += 1
        else:
            unsafe += 1
    return {
        "nominal": nom / n,
        "degraded": deg / n,
        "unsafe": unsafe / n,
        "cost": cost,
    }


def evaluate(strategy, n=120000):
    per = {r: run_strategy(strategy, r, n) for r in P}
    agg = {
        "nominal": sum(W[r] * per[r]["nominal"] for r in P),
        "degraded": sum(W[r] * per[r]["degraded"] for r in P),
        "unsafe": sum(W[r] * per[r]["unsafe"] for r in P),
        "cost": sum(W[r] * per[r]["cost"] for r in P),
        "per_rung": per,
    }
    return agg


def attribution(n=120000):
    full = evaluate(KERNEL, n)
    rows = {}
    for name in KERNEL:
        reduced = [x for x in KERNEL if x != name]
        loo = evaluate(reduced, n)
        d_unsafe = loo["unsafe"] - full["unsafe"]      # removed -> more unsafe
        d_nominal = loo["nominal"] - full["nominal"]   # removed -> more nominal
        d_cost = full["cost"] - loo["cost"]            # added cost of the member
        rows[name] = {
            "d_unsafe_pp": 100.0 * d_unsafe,
            "d_nominal_pp": 100.0 * d_nominal,
            "d_cost": d_cost,
            "value_per_cost": (d_unsafe * 100.0) / max(1e-6, d_cost),
        }
    return rows


def target_aggregate(ev):
    w = {"P2": W["P2"], "P3": W["P3"]}
    z = sum(w.values())
    return {k: sum(w[r] * ev["per_rung"][r][k] for r in w) / z
            for k in ("nominal", "degraded", "unsafe")}


def main():
    strategies = {k: evaluate(v) for k, v in STRATEGIES.items()}
    res = {
        "assumption_note": "Mechanism check only; probabilities/coverage are "
                           "documented scenario assumptions, not measurements.",
        "scenario_weights": W,
        "target_scenarios": ["P2", "P3"],
        "strategies": strategies,
        "target_P2P3": {k: target_aggregate(v) for k, v in strategies.items()},
        "leave_one_out": attribution(),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
