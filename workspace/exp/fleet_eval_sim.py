"""Round-70 synthetic mechanism checks: FLEET-RAS.

NOT benchmark evidence. Four isolated mechanism questions.

S1  Common-mode floor / effective independence (Lemma 19)
    k observers, each error = common cause OR idiosyncratic error.
    Question: how fast does majority-vote error vanish with k, and what does
    the R69 "k orthogonal sources" bound miss once a common-mode floor exists?

S2  Fleet corroboration of a mode (Lemma 20)
    One robot reports a phantom mode.  Other robots independently (or with a
    correlated common cause) corroborate it.  Question: when does "several robots
    agree" mean the mode is real, and when is it just shared hallucination?

S3  Certification-boundary data collection (Lemma 21 / MEV)
    A gate asks whether any scenario family exceeds an unsafe threshold theta0.
    Policies: uniform, worst-first, easy-first, boundary.  Question: which
    collection policy buys the most gate confidence per episode?

S4  Provenance / Byzantine robustness (Lemma 22 / DPC)
    n robots report a calibration scalar; f are rogue.  Compare mean / median /
    trimmed mean and leave-one-robot-out influence detection.
"""
import json
import math
import os
import statistics as st

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fleet_eval_results.json")
LEADER = os.path.join(HERE, "unibot_leaderboard_20261102.json")

SEED = 20261114
rng = np.random.default_rng(SEED)


# ======================================================================
# S0  real leaderboard: why edge/tail differs from the mean
# ======================================================================
def leaderboard_tail():
    with open(LEADER, encoding="utf-8") as f:
        d = json.load(f)
    names = [m["model_name"] for m in d["models"]]
    tasks = d["tasks"]
    S = {m["model_name"]: {t["task"]: t["success_rate"]
                           for t in m["task_metrics"]} for m in d["models"]}

    rows = []
    for n in names:
        vals = sorted(S[n][t] for t in tasks)
        q = max(1, len(vals) // 4)
        rows.append({
            "model": n,
            "mean": round(st.mean(vals), 2),
            "min": round(vals[0], 2),
            "cvar25": round(st.mean(vals[:q]), 2),
        })
    by_mean = sorted(rows, key=lambda r: -r["mean"])
    by_cvar = sorted(rows, key=lambda r: -r["cvar25"])
    # tasks where every submitted model is weak (a fleet-shared hard mode)
    hard_all = []
    for th in (20, 25, 30):
        hard_all.append({
            "threshold": th,
            "n_tasks_all_models_below": sum(
                1 for t in tasks if max(S[n][t] for n in names) < th),
        })
    return {
        "n_models": len(names),
        "n_tasks": len(tasks),
        "ranking_by_mean": [r["model"] for r in by_mean],
        "ranking_by_cvar25": [r["model"] for r in by_cvar],
        "rank_switch_pairs": [
            [a["model"], b["model"]]
            for a, b in zip(by_mean, by_cvar) if a["model"] != b["model"]
        ],
        "models": sorted(rows, key=lambda r: -r["mean"]),
        "hard_all_model_tasks": hard_all,
        "mean_gap_best_worst_pp": round(by_mean[0]["mean"] - by_mean[-1]["mean"], 2),
    }


# ======================================================================
# S1  common-mode floor
# ======================================================================
def common_mode_floor(trials=60000):
    delta_ind = 0.25
    out = {}
    for dc in (0.0, 0.01, 0.03, 0.05):
        curve = {}
        for k in (1, 2, 3, 5, 8, 12):
            common = rng.random(trials) < dc
            # idiosyncratic errors, shape (trials, k)
            ind = rng.random((trials, k)) < delta_ind
            err = common[:, None] | ind
            wrong = err.mean(axis=1) > 0.5
            curve[str(k)] = round(float(wrong.mean()), 4)
        # independent-only reference (R69's implicit dc=0 bound)
        ref = {}
        for k in (1, 2, 3, 5, 8, 12):
            ref[str(k)] = round(float((rng.binomial(k, delta_ind, trials) > k / 2).mean()), 4)
        out[f"dc={dc}"] = {"majority_error": curve, "independent_ref": ref}

    # effective independence under equicorrelation
    n_eff = {}
    for rho in (0.0, 0.05, 0.1, 0.3, 0.5, 0.8):
        n_eff[f"rho={rho}"] = {
            str(k): round(k / (1.0 + (k - 1) * rho), 2) for k in (2, 3, 5, 8, 12)
        }
    return {
        "delta_ind": delta_ind,
        "trials": trials,
        "by_floor": out,
        "n_eff_equicorrelation": n_eff,
    }


# ======================================================================
# S2  phantom-mode corroboration
# ======================================================================
def phantom_corroboration(trials=40000):
    # other robots: common cause with prob dc (all support), else independent
    # false-positive alpha.  A phantom is "corroborated" if >= q others support.
    alpha = 0.05
    out = {}
    for dc in (0.0, 0.01, 0.03, 0.10):
        row = {}
        for n in (2, 3, 5, 10):
            common = rng.random(trials) < dc
            ind = rng.random((trials, n - 1)) < alpha
            support = common[:, None] | ind
            any_other = support.any(axis=1)
            two_other = support.sum(axis=1) >= 2
            row[str(n)] = {
                "corroborated_ge1": round(float(any_other.mean()), 4),
                "corroborated_ge2": round(float(two_other.mean()), 4),
            }
        out[f"dc={dc}"] = row
    # true-mode power: each other robot detects with p_det, no common cause
    power = {}
    for p_det in (0.3, 0.5, 0.7):
        power[f"p_det={p_det}"] = {}
        for n in (2, 3, 5, 10):
            support = (rng.random((trials, n - 1)) < p_det)
            power[f"p_det={p_det}"][str(n)] = {
                "corroborated_ge1": round(float(support.any(axis=1).mean()), 4),
                "corroborated_ge2": round(float((support.sum(axis=1) >= 2).mean()), 4),
            }
    return {"alpha": alpha, "phantom": out, "true_mode_power": power}


# ======================================================================
# S3  certification-boundary collection
# ======================================================================
def boundary_collection(reps=3000, n_fam=20, budget=200, pilot=4):
    """Does the collection policy have to match the risk functional?

    Target A: mean fleet risk   R_mean = sum_f w_f p_f
    Target B: tail fleet risk   R_tail = max_f p_f
    Policies: uniform, risk_prop (allocate ~ p_hat), neyman
    (~ w_f sqrt(p(1-p))), tail_top2 (allocate to top-2 p_hat).
    A pilot of `pilot` episodes per family is collected before allocation.
    """
    w = np.full(n_fam, 1.0 / n_fam)
    policies = ("uniform", "risk_prop", "neyman", "tail_top2")
    results = {}
    for target in ("mean", "tail"):
        results[target] = {pol: {"sq": [], "bias": []} for pol in policies}

    for _ in range(reps):
        p = np.concatenate([
            rng.beta(0.4, 12.0, n_fam - 2),
            rng.beta(3.0, 3.0, 2),
        ])
        true_mean = float(np.sum(w * p))
        true_tail = float(np.max(p))
        # pilot
        succ = rng.binomial(pilot, p).astype(float)
        n = np.full(n_fam, pilot, dtype=int)
        p_hat = (succ + 0.5) / (n + 6.0)
        remaining = budget - pilot * n_fam
        for pol in policies:
            if pol == "uniform":
                alloc = np.full(n_fam, remaining // n_fam)
            elif pol == "risk_prop":
                wt = p_hat + 1e-6
                alloc = np.floor(remaining * wt / wt.sum()).astype(int)
            elif pol == "neyman":
                wt = w * np.sqrt(p_hat * (1 - p_hat) + 1e-6)
                alloc = np.floor(remaining * wt / wt.sum()).astype(int)
            else:  # tail_top2
                alloc = np.zeros(n_fam, dtype=int)
                top = np.argsort(-p_hat)[:2]
                alloc[top] = remaining // 2
                alloc[top[0]] += remaining % 2
            # slop: give leftovers to the first families
            left = remaining - int(alloc.sum())
            alloc[:left] += 1
            n_pol = n + alloc
            succ_pol = succ + rng.binomial(alloc, p)
            p_est = (succ_pol + 0.5) / (n_pol + 6.0)
            est_mean = float(np.sum(w * p_est))
            est_tail = float(np.max(p_est))
            for target, true, est in (("mean", true_mean, est_mean),
                                      ("tail", true_tail, est_tail)):
                results[target][pol]["sq"].append((est - true) ** 2)
                results[target][pol]["bias"].append(est - true)

    out = {}
    for target in ("mean", "tail"):
        out[target] = {}
        for pol in policies:
            sq = np.asarray(results[target][pol]["sq"])
            bi = np.asarray(results[target][pol]["bias"])
            out[target][pol] = {
                "rmse": round(float(np.sqrt(sq.mean())), 4),
                "bias": round(float(bi.mean()), 4),
            }
    return {"reps": reps, "n_families": n_fam, "budget": budget,
            "pilot_per_family": pilot, "by_target": out}


# ======================================================================
# S4  Byzantine robots, robust aggregation, LORO influence
# ======================================================================
def brazilian(trials=4000, n=12, scale=0.10, bias=1.0, gate=0.05):
    def trimmed(x, frac=0.15):
        x = np.sort(x)
        k = int(len(x) * frac)
        return float(x[k:len(x) - k].mean())

    out = {}
    for f in (0, 1, 2):
        errs = {"mean": [], "median": [], "trimmed": []}
        res_tp = res_fp = res_nrog = res_ncln = 0
        loro_tp = loro_fp = loro_nrog = loro_ncln = 0
        for _ in range(trials):
            x = rng.normal(0.0, scale, n)
            rogue = np.zeros(n, dtype=bool)
            if f:
                idx = rng.choice(n, f, replace=False)
                rogue[idx] = True
                x[idx] += bias
            errs["mean"].append(abs(float(x.mean())))
            errs["median"].append(abs(float(np.median(x))))
            errs["trimmed"].append(abs(trimmed(x)))

            # robust residual flag: |x_r - median| / (1.4826 * MAD)
            med = float(np.median(x))
            mad = float(np.median(np.abs(x - med))) + 1e-12
            z = np.abs(x - med) / (1.4826 * mad)
            flags = z > 4.0
            res_tp += int((flags & rogue).sum()); res_fp += int((flags & ~rogue).sum())
            res_nrog += int(rogue.sum()); res_ncln += int((~rogue).sum())

            # LORO influence on the gate decision (mean > gate)
            base = float(x.mean()) > gate
            for r in range(n):
                xm = (x.sum() - x[r]) / (n - 1)
                flip = (float(xm) > gate) != base
                if rogue[r] and flip:
                    loro_tp += 1
                elif not rogue[r] and flip:
                    loro_fp += 1
            loro_nrog += int(rogue.sum()); loro_ncln += int((~rogue).sum())

        out[f"rogue={f}"] = {
            "mae": {k: round(float(np.mean(v)), 4) for k, v in errs.items()},
            "robust_residual": {
                "rogue_recall": round(res_tp / max(res_nrog, 1), 4),
                "clean_false_alarm": round(res_fp / max(res_ncln, 1), 4),
            },
            "loro_gate_flip": {
                "rogue_recall": round(loro_tp / max(loro_nrog, 1), 4),
                "clean_false_alarm": round(loro_fp / max(loro_ncln, 1), 4),
            },
        }
    return {"n": n, "scale": scale, "bias": bias, "gate": gate,
            "trials": trials, "by_f": out}


if __name__ == "__main__":
    res = {
        "note": "synthetic mechanism check; not benchmark evidence",
        "seed": SEED,
        "S0_leaderboard_tail": leaderboard_tail(),
        "S1_common_mode": common_mode_floor(),
        "S2_phantom": phantom_corroboration(),
        "S3_boundary_collection": boundary_collection(),
        "S4_byzantine": brazilian(),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
