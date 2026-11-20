"""Synthetic proxy experiments for the 'mobile chassis x scene generalization' round.

NOT real-robot data. These are mechanism-level simulations with explicit
assumptions, used only to (a) sanity-check the direction of the proposed
canonicalization / null-space ideas and (b) produce order-of-magnitude numbers
to pre-register against real-robot experiments.

Run:  PYTHONPATH=workspace/.pylibs python workspace/exp/round_mobile_canon_sim.py
"""
import json
import numpy as np

rng = np.random.default_rng(20261120)


def reach_kernel(r, s=0.18):
    return np.exp(-0.5 * (r / s) ** 2)


def part_a(n=400_000):
    """Position-axis canonicalization: fixed base vs active base."""
    rows = []
    B_MAX = 0.60
    VIS_SIGMA = 0.03
    DRIFT_FRAC = 0.04          # proportional dead-reckoning drift
    for sigma in [0.08, 0.15, 0.25, 0.35, 0.50]:
        x = rng.normal(0.0, sigma, n)
        # passive: base fixed at 0
        succ_fixed = reach_kernel(x)
        # active: observe x with noise, command base to cancel relative offset
        x_hat = x + rng.normal(0.0, VIS_SIGMA, n)
        b_cmd = np.clip(x_hat, -B_MAX, B_MAX)
        b_act = b_cmd + rng.normal(0.0, 1.0, n) * DRIFT_FRAC * np.abs(b_cmd)
        succ_active = reach_kernel(x - b_act)
        for dsem in [0.0, 0.3, 0.6]:
            sf = float(np.mean(succ_fixed) * (1 - dsem))
            sa = float(np.mean(succ_active) * (1 - dsem))
            # empirical canonicalizability: fraction of remaining failures closed
            kappa = (sa - sf) / max(1e-9, (1 - sf))
            rows.append({
                "sigma": sigma, "delta_sem": dsem,
                "succ_fixed": round(sf, 4), "succ_active": round(sa, 4),
                "abs_gain": round(sa - sf, 4), "kappa_emp": round(kappa, 4),
            })
    return rows


def part_b():
    """Base-arm coupling: world-frame EE displacement vs. grasp retention."""
    rows = []
    for db in [0.0, 0.02, 0.05, 0.10, 0.20, 0.30, 0.50]:
        # uncompensated: base-frame target held while base moves
        p_raw = float(np.exp(-0.5 * (db / 0.04) ** 2))
        # compensated with 10% residual (imperfect base-state / IK)
        db_eff = 0.10 * db
        p_comp = float(np.exp(-0.5 * (db_eff / 0.04) ** 2))
        rows.append({"delta_base_m": db, "p_hold_uncompensated": round(p_raw, 4),
                     "p_hold_compensated_10pct_residual": round(p_comp, 4)})
    return rows


def part_c():
    """Peek value as a function of the current grasp posterior q=P(held|o).

    Utility: continue -> 0.9 if held else 0.1; re-grasp -> 0.6 if held else 0.7.
    Peek reveals the true state with accuracy rho, otherwise leaves q unchanged.
    Peek cost c. Value peaks where the current posterior is near the
    continue/re-grasp indifference point (q ~= 2/3), and is ~0 when confident.
    """
    rho, c = 0.90, 0.04
    rows = []
    for q in [0.05, 0.20, 0.40, 0.55, 0.667, 0.80, 0.95]:
        u_cont = 0.9 * q + 0.1 * (1 - q)
        u_regr = 0.6 * q + 0.7 * (1 - q)
        act_now = max(u_cont, u_regr)
        v_peek = rho * (0.9 * q + 0.7 * (1 - q)) + (1 - rho) * act_now - c
        rows.append({"post_held_q": q, "succ_act_now": round(act_now, 4),
                     "succ_peek_then_act": round(v_peek, 4),
                     "peek_gain": round(v_peek - act_now, 4)})
    return rows


if __name__ == "__main__":
    out = {"part_a_position_canonicalization": part_a(),
           "part_b_base_arm_coupling": part_b(),
           "part_c_peek_value": part_c()}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open("workspace/exp/round_mobile_canon_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
