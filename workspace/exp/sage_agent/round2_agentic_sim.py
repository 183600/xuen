"""Round-2 mechanism simulations for the agentic / causal-identification story.

Part A: intervention policies on a hidden grasp state (never / fixed-FPR /
posterior-threshold / VoI-band / oracle).  Synthetic parameters; this is a
mechanism check, NOT real-robot evidence.

Part B: why the usual treated-vs-control comparison is confounded, and why a
randomized *encouragement* design + placebo recover the causal effect of
intervention.  Also synthetic.

Run with  PYTHONPATH=.pylibs python3 exp/sage_agent/round2_agentic_sim.py
"""
import json
import os

import numpy as np
from scipy.stats import norm

RNG = np.random.default_rng(20261118)

Q_G = 0.80
Q_B = 0.05
PRIOR = 0.70
C_RETRY = 6.0
C_PRIM = 10.0
C_PROBE = 2.5
Q_PRIM = 0.25
F_PRIM = 0.35
MAX_RETRY = 3
T_EPISODE = 44.0
T_MIN = 3.0


def d_from_auc(auc):
    return np.sqrt(2.0) * norm.ppf(auc)


def posterior_from_score(score, d, prior):
    lg = norm.logpdf(score, d / 2.0, 1.0) + np.log(prior)
    lb = norm.logpdf(score, -d / 2.0, 1.0) + np.log(1.0 - prior)
    m = np.maximum(lg, lb)
    return np.exp(lg - m) / (np.exp(lg - m) + np.exp(lb - m))


def bayes_update(prior, score, d):
    return posterior_from_score(score, d, prior)


def policy_decision(policy, p, score, R, n, probed, prim, d, d_probe, tau_fixed,
                    tau_p=PRIOR):
    if policy == "never":
        return "continue"
    if policy == "fixed":
        if score < tau_fixed and n < MAX_RETRY and R >= C_RETRY + T_MIN:
            return "retry"
        if n >= MAX_RETRY and prim and R >= C_PRIM + T_MIN:
            return "switch"
        return "continue"
    if policy == "posterior":
        if p < tau_p and n < MAX_RETRY and R >= C_RETRY + T_MIN:
            return "retry"
        if n >= MAX_RETRY and prim and R >= C_PRIM + T_MIN:
            return "switch"
        return "continue"
    if policy == "voi_band":
        if (not probed) and (0.20 <= p <= 0.80) and R >= C_PROBE + C_RETRY + T_MIN:
            return "probe"
        if p < 0.45 and n < MAX_RETRY and R >= C_RETRY + T_MIN:
            return "retry"
        if p < 0.45 and n >= MAX_RETRY and prim and R >= C_PRIM + T_MIN:
            return "switch"
        return "continue"
    if policy == "oracle":
        return "continue"
    raise ValueError(policy)


def run_episode(policy, d, d_probe, prim, rng, tau_fixed, tau_p=PRIOR):
    R = T_EPISODE
    n = 0
    probed = False
    good = rng.random() < PRIOR
    score = rng.normal(d / 2.0 if good else -d / 2.0, 1.0)
    p = posterior_from_score(score, d, PRIOR)
    while True:
        if policy == "oracle":
            act = "continue"
            if not good and n < MAX_RETRY and R >= C_RETRY + T_MIN:
                act = "retry"
            elif not good and n >= MAX_RETRY and prim and R >= C_PRIM + T_MIN:
                act = "switch"
        else:
            act = policy_decision(policy, p, score, R, n, probed, prim, d,
                                  d_probe, tau_fixed, tau_p)
        if act == "continue":
            return int(rng.random() < (Q_G if good else Q_B)), n
        if act == "switch":
            return int(rng.random() < Q_PRIM), n + 1
        if act == "probe":
            R -= C_PROBE
            probed = True
            s2 = rng.normal(d_probe / 2.0 if good else -d_probe / 2.0, 1.0)
            p = bayes_update(p, s2, d_probe)
            continue
        R -= C_RETRY
        n += 1
        good = rng.random() < PRIOR
        score = rng.normal(d / 2.0 if good else -d / 2.0, 1.0)
        p = posterior_from_score(score, d, PRIOR)


def simulate(policy, auc, n_ep, seed, tau_p=PRIOR):
    rng = np.random.default_rng(seed)
    d = d_from_auc(auc)
    d_probe = d_from_auc(0.75)
    tau_fixed = -d / 2.0 + norm.ppf(0.02)
    succ = np.empty(n_ep)
    ints = np.empty(n_ep)
    for i in range(n_ep):
        prim = rng.random() < F_PRIM
        s, k = run_episode(policy, d, d_probe, prim, rng, tau_fixed, tau_p)
        succ[i] = s
        ints[i] = k
    return float(succ.mean()), float(ints.mean())


def part_a(n_ep=40000):
    out = {}
    for auc in (0.70, 0.85, 0.95):
        row = {}
        for pol in ("never", "fixed", "posterior", "voi_band", "oracle"):
            s, k = simulate(pol, auc, n_ep, seed=1000 + int(auc * 100))
            row[pol] = {"success": round(s, 4), "interventions_per_ep": round(k, 3)}
        out[f"AUC_{auc:.2f}"] = row
    return out


def part_a2_threshold_sweep(n_ep=30000):
    out = []
    for tp in (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90):
        s, k = simulate("posterior", 0.85, n_ep, seed=4242, tau_p=tp)
        out.append({"tau_p": tp, "success": round(s, 4),
                    "interventions_per_ep": round(k, 3)})
    return out


def part_b(n_ep=400000, seed=7):
    rng = np.random.default_rng(seed)
    auc = 0.85
    d = d_from_auc(auc)
    tau = -d / 2.0 + norm.ppf(0.10)
    delta = 0.90
    z = rng.integers(0, 2, n_ep)
    good = rng.random(n_ep) < PRIOR
    score = rng.normal(d / 2.0, 1.0, n_ep)
    score[~good] = rng.normal(-d / 2.0, 1.0, int((~good).sum()))
    treated = score < (tau - delta * z)
    new_good = rng.random(n_ep) < PRIOR
    y0 = np.where(good, rng.random(n_ep) < Q_G, rng.random(n_ep) < Q_B).astype(float)
    y1 = np.where(new_good, rng.random(n_ep) < Q_G, rng.random(n_ep) < Q_B).astype(float)
    y = np.where(treated, y1, y0)
    naive = y[treated].mean() - y[~treated].mean()
    p_z1 = treated[z == 1].mean()
    p_z0 = treated[z == 0].mean()
    wald = (y[z == 1].mean() - y[z == 0].mean()) / (p_z1 - p_z0)
    placebo_rate = treated.mean()
    pd = rng.random(n_ep) < placebo_rate
    y_placebo = np.where(pd, y1, y0)
    placebo = y_placebo[pd].mean() - y_placebo[~pd].mean()
    ate_bad = (y1 - y0)[~good].mean()
    ate_good = (y1 - y0)[good].mean()
    dose = []
    for dl in (0.0, 0.3, 0.6, 0.9, 1.2):
        zz = rng.integers(0, 2, n_ep)
        gg = rng.random(n_ep) < PRIOR
        ss = rng.normal(d / 2.0, 1.0, n_ep)
        ss[~gg] = rng.normal(-d / 2.0, 1.0, int((~gg).sum()))
        dd = ss < (tau - dl * zz)
        ng = rng.random(n_ep) < PRIOR
        yy0 = np.where(gg, rng.random(n_ep) < Q_G, rng.random(n_ep) < Q_B).astype(float)
        yy1 = np.where(ng, rng.random(n_ep) < Q_G, rng.random(n_ep) < Q_B).astype(float)
        yy = np.where(dd, yy1, yy0)
        den = dd[zz == 1].mean() - dd[zz == 0].mean()
        w = (yy[zz == 1].mean() - yy[zz == 0].mean()) / den if abs(den) > 1e-9 else float("nan")
        dose.append({"shift": dl, "first_stage": round(float(den), 4),
                     "wald_late": round(float(w), 4)})
    boot = []
    for _ in range(200):
        idx = rng.integers(0, n_ep, n_ep)
        bz = z[idx]
        bt = treated[idx]
        by = y[idx]
        denom = bt[bz == 1].mean() - bt[bz == 0].mean()
        if abs(denom) > 1e-6:
            boot.append((by[bz == 1].mean() - by[bz == 0].mean()) / denom)
    boot = np.array(boot)
    return {
        "setting": {
            "auc": auc, "prior_good": PRIOR, "q_good": Q_G, "q_bad": Q_B,
            "encouragement_threshold_shift": delta, "n_episodes": n_ep,
        },
        "naive_treated_minus_control": round(float(naive), 4),
        "encouragement_wald_late": round(float(wald), 4),
        "encouragement_late_ci95": [round(float(np.quantile(boot, 0.025)), 4),
                                    round(float(np.quantile(boot, 0.975)), 4)],
        "placebo_intervention_effect": round(float(placebo), 4),
        "first_stage_propensity_z1": round(float(p_z1), 4),
        "first_stage_propensity_z0": round(float(p_z0), 4),
        "true_effect_on_bad_grasp": round(float(ate_bad), 4),
        "true_effect_on_good_grasp": round(float(ate_good), 4),
        "dose_response": dose,
        "note": "synthetic; naive A/B is confounded because low scores both "
                "trigger intervention and indicate a bad grasp",
    }


def part_c(n_ep=40000, seed=11):
    rng = np.random.default_rng(seed)
    auc = 0.85
    d = d_from_auc(auc)
    d_probe = d_from_auc(0.75)
    bands = [(0.05, 0.95), (0.15, 0.85), (0.25, 0.75), (0.35, 0.65)]
    out = []
    for lo, hi in bands:
        succ = 0.0
        probes = 0.0
        for _ in range(n_ep):
            R = T_EPISODE
            probed = False
            good = rng.random() < PRIOR
            score = rng.normal(d / 2.0 if good else -d / 2.0, 1.0)
            p = posterior_from_score(score, d, PRIOR)
            n = 0
            while True:
                if (not probed) and (lo <= p <= hi) and R >= C_PROBE + C_RETRY + T_MIN:
                    R -= C_PROBE
                    probed = True
                    probes += 1
                    s2 = rng.normal(d_probe / 2.0 if good else -d_probe / 2.0, 1.0)
                    p = bayes_update(p, s2, d_probe)
                    continue
                prim = F_PRIM
                act = policy_decision("voi_band", p, score, R, n, probed, prim,
                                      d, d_probe, -1e9)
                if act == "continue":
                    succ += int(rng.random() < (Q_G if good else Q_B))
                    break
                if act == "switch":
                    succ += int(rng.random() < Q_PRIM)
                    break
                R -= C_RETRY
                n += 1
                good = rng.random() < PRIOR
                score = rng.normal(d / 2.0 if good else -d / 2.0, 1.0)
                p = posterior_from_score(score, d, PRIOR)
        out.append({"band": [lo, hi], "success": round(succ / n_ep, 4),
                    "probes_per_ep": round(probes / n_ep, 3)})
    return out


def main():
    out = {
        "part_a_intervention_policies": part_a(),
        "part_a2_posterior_threshold_sweep": part_a2_threshold_sweep(),
        "part_b_causal_identification": part_b(),
        "part_c_probe_band_sweep": part_c(),
        "assumptions": {
            "q_good": Q_G, "q_bad": Q_B, "prior_good": PRIOR,
            "retry_cost_s": C_RETRY, "primitive_cost_s": C_PRIM,
            "probe_cost_s": C_PROBE, "primitive_success": Q_PRIM,
            "primitive_feasible_frac": F_PRIM, "max_retries": MAX_RETRY,
            "episode_seconds": T_EPISODE, "t_min_s": T_MIN,
        },
        "disclaimer": "synthetic mechanism simulation; not real-robot evidence",
    }
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "round2_agentic_sim_results.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
