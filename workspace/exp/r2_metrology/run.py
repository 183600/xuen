#!/usr/bin/env python3
"""R2 metrology: is the UniBot leaderboard's per-task 'skill' identifiable,
and what effects can a 32-task x 1-evaluation benchmark resolve?

Inputs : exp/unibot_leaderboard_20261102.json (teaser snapshot, synthetic)
Outputs: exp/r2_metrology/results.json

Run: PYTHONPATH=.pylibs python exp/r2_metrology/run.py
"""
import json
import os
from itertools import combinations

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, "exp", "unibot_leaderboard_20261102.json")
OUT = os.path.join(HERE, "results.json")

rng = np.random.default_rng(20261118)

raw = json.load(open(DATA))
models = [m["model_name"] for m in raw["models"]]
tasks = [t["task"] for t in raw["models"][0]["task_metrics"]]
M, T = len(models), len(tasks)
Y = np.zeros((M, T))
for i, m in enumerate(raw["models"]):
    for j, tm in enumerate(m["task_metrics"]):
        Y[i, j] = tm["success_rate"]
res = {"n_models": M, "n_tasks": T, "models": models, "tasks": tasks}

# ---------------------------------------------------------------- 0. forensics
# Success rates should be multiples of 100/n if they came from n integer trials.
best_n, best_err = None, 1e9
for n in range(2, 2001):
    scaled = Y * n / 100.0
    err = np.mean(np.abs(scaled - np.round(scaled)))
    if err < best_err:
        best_err, best_n = err, n
res["forensics"] = {
    "best_integer_trial_n": best_n,
    "mean_abs_dev_from_integer_counts": float(best_err),
    "verdict": "not consistent with any integer trial count (synthetic values)"
    if best_err > 0.02 else "consistent with integer trials",
    "example_values": Y[0, :6].tolist(),
}

# ------------------------------------------- 1. pairwise rank agreement (tau)
pairs = list(combinations(range(M), 2))


def mean_pair_tau(mat):
    vals = []
    for a, b in pairs:
        tau = stats.kendalltau(mat[a], mat[b]).statistic
        if np.isfinite(tau):
            vals.append(tau)
    return float(np.mean(vals)), float(np.std(vals))


obs_tau, obs_tau_sd = mean_pair_tau(Y)
# null: permute the 8 model labels independently inside every task
null_tau = np.empty(4000)
for r in range(null_tau.size):
    P = np.empty_like(Y)
    for j in range(T):
        P[:, j] = Y[rng.permutation(M), j]
    null_tau[r], _ = mean_pair_tau(P)
res["pairwise_tau"] = {
    "observed_mean": obs_tau,
    "observed_sd": obs_tau_sd,
    "null_mean": float(null_tau.mean()),
    "null_sd": float(null_tau.std()),
    "null_p95": float(np.quantile(null_tau, 0.95)),
    "perm_p_one_sided": float((1 + np.sum(null_tau >= obs_tau)) / (1 + null_tau.size)),
    "z_vs_null": float((obs_tau - null_tau.mean()) / null_tau.std()),
}

# ------------------------------------- 2. additive decomposition + reliabilty
grand = Y.mean()
alpha = Y.mean(axis=1) - grand           # model effect
beta = Y.mean(axis=0) - grand            # task effect
fit = grand + alpha[:, None] + beta[None, :]
resid = Y - fit
res["anova"] = {
    "grand_mean": float(grand),
    "var_model_effect": float(np.mean(alpha ** 2)),
    "var_task_effect": float(np.mean(beta ** 2)),
    "var_residual": float(np.mean(resid ** 2)),
    "sd_model_effect": float(np.sqrt(np.mean(alpha ** 2))),
    "sd_task_effect": float(np.sqrt(np.mean(beta ** 2))),
    "sd_residual": float(np.sqrt(np.mean(resid ** 2))),
    "frac_model": float(np.mean(alpha ** 2) / Y.var()),
    "frac_task": float(np.mean(beta ** 2) / Y.var()),
    "frac_resid": float(np.mean(resid ** 2) / Y.var()),
}

# additive-skills null: keep alpha/beta, re-draw i.i.d. interaction-residual noise.
# If observed tau is inside this null, there is no evidence of reproducible
# model x task SPECIALIZATION beyond a common per-model skill offset.
add_tau = np.empty(3000)
for r in range(add_tau.size):
    # residual bootstrap: resample residual entries within each task column
    R = np.empty_like(resid)
    for j in range(T):
        R[:, j] = resid[rng.permutation(M), j]
    add_tau[r], _ = mean_pair_tau(fit + R)
res["pairwise_tau"]["additive_null_mean"] = float(add_tau.mean())
res["pairwise_tau"]["additive_null_sd"] = float(add_tau.std())
res["pairwise_tau"]["additive_null_p95"] = float(np.quantile(add_tau, 0.95))
res["pairwise_tau"]["p_vs_additive_null"] = float(
    (1 + np.sum(add_tau >= obs_tau)) / (1 + add_tau.size))

# split-half reliability of the 8 model means: does the ORDER of models replicate?
def split_half_r(mat, trials=5000):
    rs = []
    for _ in range(trials):
        idx = rng.permutation(T)
        h1, h2 = idx[: T // 2], idx[T // 2:]
        a = mat[:, h1].mean(axis=1)
        b = mat[:, h2].mean(axis=1)
        rs.append(stats.pearsonr(a, b).statistic)
    return np.array(rs)


obs_sh = split_half_r(Y)
# null: shuffle model labels within each task (destroys model identity)
null_sh = []
for _ in range(2000):
    P = np.empty_like(Y)
    for j in range(T):
        P[:, j] = Y[rng.permutation(M), j]
    null_sh.append(float(split_half_r(P, trials=1)[0]))
null_sh = np.array(null_sh)
# Spearman-Brown correction to full-length reliability
sb = 2 * obs_sh.mean() / (1 + obs_sh.mean())
res["model_mean_reliability"] = {
    "split_half_r_mean": float(obs_sh.mean()),
    "split_half_r_p05": float(np.quantile(obs_sh, 0.05)),
    "spearman_brown_full": float(sb),
    "null_split_half_mean": float(null_sh.mean()),
    "perm_p": float((1 + np.sum(null_sh >= obs_sh.mean())) / (1 + null_sh.size)),
}

# ---------------------------------- 3. oracle dividend and its replicability
def oracle_gain(mat):
    per_task_best = mat.max(axis=0).mean()
    best_single = mat.mean(axis=1).max()
    return float(per_task_best - best_single)


obs_oracle = oracle_gain(Y)
res["oracle"] = {"observed_gain_pp": obs_oracle}

# Under an additive-skills null (no true model x task interaction above noise),
# observed = mu + alpha_m + beta_t + eps.  A router fitted on evaluation A and
# re-tested on independent evaluation B can only cash what is real in alpha.
sd_eps = float(res["anova"]["sd_residual"])
sim = []
for f in [0.0, 0.25, 0.5, 0.75, 1.0]:
    # fraction f of residual variance is fresh measurement noise; the rest is
    # treated as true (stable) interaction, which no one-shot design can rule out
    sd_noise = sd_eps * np.sqrt(f)
    sd_int = sd_eps * np.sqrt(1 - f)
    reps = 400
    gains = []
    for _ in range(reps):
        true_int = rng.normal(0, sd_int, size=(M, T)) if sd_int > 0 else 0.0
        truth = grand + alpha[:, None] + beta[None, :] + true_int
        ev1 = truth + rng.normal(0, sd_noise, size=(M, T)) if sd_noise > 0 else truth
        ev2 = truth + rng.normal(0, sd_noise, size=(M, T)) if sd_noise > 0 else truth
        pick = ev1.argmax(axis=0)
        routed = ev2[pick, np.arange(T)].mean()
        best_single = ev2.mean(axis=1).max()
        gains.append(routed - best_single)
    gains = np.array(gains)
    sim.append({
        "noise_fraction_f": f,
        "replicable_oracle_gain_pp_mean": float(gains.mean()),
        "replicable_oracle_gain_pp_p05": float(np.quantile(gains, 0.05)),
        "replicable_oracle_gain_pp_p95": float(np.quantile(gains, 0.95)),
    })
res["oracle_replication"] = {
    "observed_one_shot_gain_pp": obs_oracle,
    "sd_residual_pp": sd_eps,
    "curve": sim,
    "note": "with one evaluation per (model,task) cell, f is not identifiable; "
            "the observed +4.26pp is reproduced by every f, but only f=0 cashes out",
}

# ------------------------------------- 4. benchmark resolution (MDE) vs trials
pt = Y.mean(axis=0) / 100.0          # per-task success probability (pooled)
pbar = float(pt.mean())
episode_sec = float(np.mean([[t["avg_duration_sec"] for t in m["task_metrics"]]
                             for m in raw["models"]]))
z = stats.norm.ppf(0.975) + stats.norm.ppf(0.8)   # 80% power, two-sided 5%


def mde(n, paired_discordance=None):
    if paired_discordance is None:
        se = np.sqrt(np.sum(2 * pt * (1 - pt) / n)) / T
    else:
        se = np.sqrt(paired_discordance / (T * n))
    return float(z * se)


ns = [5, 10, 20, 30, 50, 100]
res["power"] = {
    "pooled_success_pct": 100 * pbar,
    "mean_episode_sec": episode_sec,
    "z_factor_80pct_2sided": float(z),
    "mde_unpaired_pp": {str(n): 100 * mde(n) for n in ns},
    "mde_paired_pp_pi_0.10": {str(n): 100 * mde(n, 0.10) for n in ns},
    "mde_paired_pp_pi_0.20": {str(n): 100 * mde(n, 0.20) for n in ns},
    "mde_paired_pp_pi_0.30": {str(n): 100 * mde(n, 0.30) for n in ns},
    "n_for_mde_unpaired": {
        f"{target}_pp": int(np.ceil(np.sum(2 * pt * (1 - pt)) / (T * (target / 100 / z) ** 2)))
        for target in [1.0, 1.5, 3.0, 5.0]
    },
    "n_for_mde_paired": {
        f"pi_{pi}": {
            f"{target}_pp": int(np.ceil(pi / (T * (target / 100 / z) ** 2)))
            for target in [1.0, 1.5, 3.0, 5.0]
        } for pi in [0.10, 0.20, 0.30]
    },
}


def robo_hours(n, arms=2):
    return T * n * arms * episode_sec / 3600.0


res["power"]["robo_hours_unpaired"] = {
    str(n): robo_hours(n, 1) for n in ns}
res["power"]["robo_hours_two_arm_paired"] = {
    str(n): robo_hours(n, 2) for n in ns}

# ------------------------------------- 5. selection inflation (best of k runs)
se_avg = {str(n): float(np.sqrt(np.sum(pt * (1 - pt) / n)) / T) for n in ns}
kmax = 20
E_max = {}
for k in [1, 2, 3, 5, 10, 20]:
    draws = rng.standard_normal((200000, k)).max(axis=1)
    E_max[str(k)] = float(draws.mean())
res["selection_inflation"] = {
    "note": "if a team re-submits k times and keeps the best, the reported mean "
            "success rate is biased upward by E[max_k]*SE under pure luck",
    "E_max_of_k_normal": E_max,
    "se_pp_by_n": {k: 100 * v for k, v in se_avg.items()},
    "inflation_pp_n10": {k: 100 * se_avg["10"] * v for k, v in E_max.items()},
}

# ------------------------------------- 6. metric dilution / leverage
res["leverage"] = {
    "d_avg_d_p_task": 1.0 / T,
    "one_task_plus_10pp_to_avg_pp": 10.0 / T,
    "one_task_needed_for_plus_3pp": 3.0 * T,
    "hard6_mean_pct": float(np.mean(np.sort(Y.mean(axis=0))[:6])),
    "hard6_plus25pct_relative_to_avg_pp": float(
        0.25 * np.mean(np.sort(Y.mean(axis=0))[:6]) * 6 / T),
}

# ------------------------------------- 7. rank stability between two evaluations
# model means sampled from their observed per-task vectors (bootstrap tasks)
boot_rank = []
for _ in range(4000):
    idx = rng.integers(0, T, T)
    boot_rank.append(-stats.rankdata(-Y[:, idx].mean(axis=1)))  # rank 1 = best
boot_rank = np.array(boot_rank)
rank1_model = int(np.argmax(Y.mean(axis=1)))
res["rank_stability"] = {
    "leader": models[rank1_model],
    "p_leader_stays_rank1": float(np.mean(boot_rank[:, rank1_model] == 1)),
    "p_leader_stays_top3": float(np.mean(boot_rank[:, rank1_model] <= 3)),
    "mean_rank_of_each_model": {
        m: float(boot_rank[:, i].mean()) for i, m in enumerate(models)},
}

# ------------------------------------- 8. step score redundancy
step = np.array([[t["step_score"] for t in m["task_metrics"]]
                 for m in raw["models"]])
res["step_score_redundancy"] = {
    "pearson_success_vs_step": float(stats.pearsonr(Y.ravel(), step.ravel()).statistic),
    "spearman_model_rank": float(stats.spearmanr(Y.mean(axis=1), step.mean(axis=1)).statistic),
    "rank_identical": bool((stats.rankdata(Y.mean(axis=1)) ==
                            stats.rankdata(step.mean(axis=1))).all()),
}

# ------------------------------------- 9. Neyman allocation gain
sig = np.sqrt(pt * (1 - pt))
neyman_ratio = float((sig.mean() ** 2) / (sig ** 2).mean())
res["neyman"] = {
    "sigma_min": float(sig.min()), "sigma_max": float(sig.max()),
    "uniform_over_neyman_variance_ratio": neyman_ratio,
    "variance_reduction_from_optimal_allocation_pct": 100 * (1 - neyman_ratio),
}

# ------------------------------------- 10. what a single IP is worth in aggregate
hard6 = np.sort(Y.mean(axis=0))[:6]
res["ip_budget"] = {
    "hard6_tasks": [tasks[i] for i in np.argsort(Y.mean(axis=0))[:6]],
    "hard6_mean_pct": float(hard6.mean()),
    "if_plus25pct_relative_on_hard6_gain_pp": float(0.25 * hard6.mean() * 6 / T),
    "if_plus3pp_absolute_on_all_32_gain_pp": 3.0,
    "mde_note": "each round-1 IP threshold (1.0-1.5pp) is below the 80%-power "
                "MDE at realistic n; only the combined system clears resolution",
}

with open(OUT, "w") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)

print(json.dumps({k: res[k] for k in [
    "forensics", "pairwise_tau", "anova", "model_mean_reliability",
    "oracle_replication", "selection_inflation", "leverage", "rank_stability",
    "step_score_redundancy", "neyman", "ip_budget"]}, ensure_ascii=False, indent=2)[:6000])
print("\nMDE unpaired pp:", res["power"]["mde_unpaired_pp"])
print("MDE paired(0.10/0.20/0.30) pp:", res["power"]["mde_paired_pp_pi_0.10"], res["power"]["mde_paired_pp_pi_0.20"], res["power"]["mde_paired_pp_pi_0.30"])
print("n for MDE unpaired:", res["power"]["n_for_mde_unpaired"])
print("n for MDE paired:", json.dumps(res["power"]["n_for_mde_paired"]))
