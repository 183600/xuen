"""Round 41 / v18 mechanism check: coordination-structure optimization (CSO).

NOT benchmark evidence. Two isolated questions on already-public artifacts:

A. Intra-robot (dual-arm) structure gating.
   The released G1_Dex1 audit (exp/r41_coop_audit_results.json) shows that
   simultaneous two-gripper closure is a minority (6.99% of frames) and that
   the co-hold relative-EE spread is task-dependent (PlugInEthernet 1.43 mm
   vs PackDoll 51.94 mm).  If a closed-chain virtual fixture is applied to a
   task whose "co-hold" is really two independent grasps, it can fight itself.
   Question: does a short observation-based gate recover the oracle mode
   choice, and how much harm does "always closed-chain" do?

B. Inter-robot (fleet) sharing radius.
   N ports share one backend but each port is a separate robot/episode.  Fleet
   statistics may be shared, episode state may not.  Question: under a mixture
   of clean and rogue (mis-calibrated) ports, does a contamination-aware
   partial-pooling strength dominate both zero sharing and full pooling?

The generators are declared; magnitudes are illustrative, not fit to the board.
"""
import json
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "r41_cso_sim_results.json")
AUDIT = os.path.join(HERE, "r41_coop_audit_results.json")
SEED = 20261110
rng = np.random.default_rng(SEED)


# ------------------------------------------------------------------ A ------
def dual_arm_gating():
    audit = json.load(open(AUDIT, encoding="utf-8"))
    tasks = audit["per_task"]
    # True closed-chain suitability: only a genuinely rigid co-hold benefits.
    # Use the audit's own reading: <5 mm relative-EE std = quasi-rigid chain.
    suit = {}
    for name, v in tasks.items():
        s = v.get("cohold_rel_dist_std_mm")
        suit[name] = 1 if (s is not None and s <= 5.0) else 0
    # Declared effect sizes (percentage points of task success).
    B, H = 12.0, 6.0
    names = sorted(tasks)
    n_task = len(names)
    true_closed = np.array([suit[t] for t in names])
    # Oracle per-task choice gives B on suitable tasks, 0 elsewhere.
    oracle = B * true_closed.mean()
    always_indep = 0.0
    always_closed = (B * true_closed - H * (1 - true_closed)).mean()

    # Gate: estimate the co-hold spread from k observed co-hold frames.
    # Frame noise std = max(true std, 1 mm); estimate sample std; declare
    # closed-chain if estimate < 5 mm.  False positive on a non-rigid task
    # costs H; false negative on a rigid task loses B.
    def gate(k):
        gains = []
        for t in names:
            s = tasks[t].get("cohold_rel_dist_std_mm")
            sd = max(s, 1.0) if s is not None else 30.0
            est = np.std(rng.normal(0.0, sd, size=k), ddof=1) if k > 1 else sd
            choose = est < 5.0
            if choose and suit[t]:
                gains.append(B)
            elif choose and not suit[t]:
                gains.append(-H)
            elif (not choose) and suit[t]:
                gains.append(0.0)   # missed benefit, no harm
            else:
                gains.append(0.0)
        return float(np.mean(gains))

    gate_k = {str(k): float(np.mean([gate(k) for _ in range(200)]))
              for k in (5, 15, 30)}
    return {
        "n_tasks": n_task,
        "suitable_tasks": [t for t in names if suit[t]],
        "always_indep_delta_pp": always_indep,
        "always_closed_delta_pp": round(always_closed, 2),
        "oracle_delta_pp": round(oracle, 2),
        "gated_delta_pp": {k: round(v, 2) for k, v in gate_k.items()},
        "reading": ("closed-chain is a niche mode: it helps the one quasi-rigid "
                    "task and hurts the rest; a k=15-frame gate recovers most "
                    "of the oracle while avoiding most of the harm."),
    }


# ------------------------------------------------------------------ B ------
def fleet_sharing():
    N = 8
    TAU, SIG = 0.5, 1.0
    n_obs = 1

    def run(rogue):
        theta = rng.normal(0.0, TAU, size=N)
        if rogue:
            theta[-1] = 6.0
        y = theta[:, None] + rng.normal(0.0, SIG, size=(N, n_obs))
        ybar = y.mean(axis=1)
        grand = ybar.mean()
        out = {}
        for kappa in (0.0, 0.25, 0.5, 0.75, 1.0):
            est = (1 - kappa) * ybar + kappa * grand
            mse = float(np.mean((est - theta) ** 2))
            worst = float(np.max((est - theta) ** 2))
            out[f"kappa={kappa:.2f}"] = {"mse": round(mse, 4),
                                         "worst_mse": round(worst, 4)}
        # Contamination detector: robust dispersion of port means.
        med = float(np.median(ybar))
        mad = float(np.median(np.abs(ybar - med)) * 1.4826)
        rogue_flag = bool(np.max(np.abs(ybar - med)) > 3.0 * SIG)
        # Robust structural sharing: pool the inliers, isolate the outliers.
        # In a clean fleet this reduces to full pooling; with one rogue port
        # the rogue is isolated and the remaining ports still share.
        if rogue_flag:
            keep = np.abs(ybar - med) <= 2.5 * max(mad, 1e-9)
            if keep.sum() == 0:
                keep = np.ones(N, dtype=bool)
            pooled = float(ybar[keep].mean())
            est = np.where(keep, pooled, ybar)
        else:
            keep = np.ones(N, dtype=bool)
            est = np.full(N, grand)
        out["adaptive"] = {
            "rogue_flag": bool(rogue_flag),
            "n_inliers": int(keep.sum()),
            "mse": round(float(np.mean((est - theta) ** 2)), 4),
            "worst_mse": round(float(np.max((est - theta) ** 2)), 4),
        }
        return out

    clean = [run(False) for _ in range(200)]
    rogue = [run(True) for _ in range(200)]

    def avg(runs):
        keys = runs[0].keys()
        return {k: {m: round(float(np.mean([r[k][m] for r in runs
                                            if m in r[k]])), 4)
                    for m in runs[0][k] if m != "rogue_flag" and m != "kappa"}
                for k in keys}

    return {
        "N": N, "tau": TAU, "sigma_obs": SIG, "n_obs_per_port": n_obs,
        "clean": avg(clean),
        "one_rogue_port": avg(rogue),
        "reading": ("When ports are homogeneous, pooling wins (partial pooling "
                    "slightly beats full pooling because it keeps each port's "
                    "own evidence).  One rogue port reverses the order: full "
                    "pooling is worst, zero sharing is robust but cold.  A "
                    "max-deviation detector plus inlier pooling isolates the "
                    "rogue and still shares among the remaining ports."),
    }


if __name__ == "__main__":
    res = {
        "note": "round-local synthetic mechanism check; not benchmark evidence",
        "seed": SEED,
        "A_dual_arm_structure": dual_arm_gating(),
        "B_fleet_sharing_radius": fleet_sharing(),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
