import json, math
import numpy as np
from scipy import stats

rng = np.random.default_rng(20261119)
out = {}

# ---------- 1) Selection bias of per-task oracle under the iid-null ----------
# If the teaser table is iid noise, how large is oracle - best_single purely by selection?
M, T, sigma, reps = 8, 32, 5.6, 20000
gap = np.empty(reps); oracle = np.empty(reps); best = np.empty(reps)
for r in range(reps):
    S = rng.normal(0.0, sigma, size=(M, T))
    oracle[r] = S.max(axis=0).mean()
    best[r] = S.mean(axis=1).max()
    gap[r] = oracle[r] - best[r]
out["oracle_null"] = {
    "M": M, "T": T, "sigma": sigma, "reps": reps,
    "oracle_mean": float(oracle.mean()),
    "best_single_mean": float(best.mean()),
    "gap_mean": float(gap.mean()),
    "gap_sd": float(gap.std(ddof=1)),
    "gap_p95": float(np.quantile(gap, 0.95)),
    "p_gap_ge_4_26": float((gap >= 4.26).mean()),
    "p_gap_ge_2_52": float((gap >= 2.52).mean()),
}

# ---------- 2) Delay margin for the scalar integrator loop ----------
# e_{t+1} = e_t - k e_{t-d}: characteristic z^{d+1} - z^d + k = 0
def kmax(d):
    ks = np.linspace(1e-4, 3.0, 30001)
    stable = []
    for k in ks:
        coeffs = np.zeros(d + 2)
        coeffs[0] = 1.0
        coeffs[1] -= 1.0
        coeffs[d + 1] += k
        r = np.roots(coeffs)
        if np.max(np.abs(r)) < 1.0:
            stable.append(k)
    return (max(stable) if stable else float("nan"))
out["delay_margin"] = {str(d): kmax(d) for d in [0,1,2,3,4,6,8,12,16]}

# ---------- 3) Paired vs unpaired MDE / n ----------
def n_needed(mde, p, rho, T=32, alpha=0.05, power=0.8):
    z = stats.norm.ppf(1-alpha/2) + stats.norm.ppf(power)
    # variance of the 32-task mean difference, per-task n episodes per arm
    var_mean_diff = 2*p*(1-p)*(1-rho)/T
    n_per_task = (z/mde)**2 * var_mean_diff
    return n_per_task, n_per_task*T
mde_table = {}
for mde in [0.05, 0.03]:
    row = {}
    for rho in [0.0, 0.3, 0.5, 0.7]:
        npt, tot = n_needed(mde, 0.3, rho)
        row[str(rho)] = {"n_per_task_per_arm": round(npt,1), "total_per_arm": round(tot,1)}
    mde_table[str(mde)] = row
out["paired_power"] = {"p":0.3, "T":32, "alpha":0.05, "power":0.8, "table":mde_table}

# ---------- 4) Open-loop vs closed-loop terminal error under disturbance ----------
def sim_loop(closed, sigma_w, T=20, reps=20000, tol=0.5, rho=0.6):
    e = rng.normal(0, 0.5, size=reps)
    if not closed:
        for _ in range(T):
            e = e + rng.normal(0, sigma_w, size=reps)
    else:
        for _ in range(T):
            e = rho*e + rng.normal(0, sigma_w, size=reps)
    return float((np.abs(e) <= tol).mean())
loop_res = {}
for sw in [0.05, 0.10, 0.20, 0.30]:
    loop_res[str(sw)] = {"open": sim_loop(False, sw), "closed_rho0.6": sim_loop(True, sw)}
out["open_vs_closed"] = {"T":20, "e0_sd":0.5, "tol":0.5, "success":loop_res}

# ---------- 5) Recovery-AUC power under a logistic perturbation-response model ----------
# R(delta) = sigmoid(a - b*delta); policy A a=1.2, B a=0.8, b=4, delta in 0..1
def auc_from_a(a, b=4.0, grid=np.linspace(0,1,101)):
    return float(np.trapezoid(1/(1+np.exp(-(a-b*grid))), grid))
aucA, aucB = auc_from_a(1.2), auc_from_a(0.8)
# approximate power: n episodes per delta level, independent, plug-in normal CI
def power_auc(aA, aB, n_per_delta, reps=4000, b=4.0, grid=np.linspace(0,1,11)):
    pA = 1/(1+np.exp(-(aA-b*grid)))
    pB = 1/(1+np.exp(-(aB-b*grid)))
    diffs = []
    for _ in range(reps):
        sA = rng.binomial(n_per_delta, pA)/n_per_delta
        sB = rng.binomial(n_per_delta, pB)/n_per_delta
        diffs.append(np.trapezoid(sA, grid) - np.trapezoid(sB, grid))
    diffs = np.array(diffs)
    se = diffs.std(ddof=1)
    # two-sided alpha=.05, true diff = aucA-aucB
    true = aucA - aucB
    crit = 1.96*se
    return float((np.abs(diffs) > crit).mean()), float(true), float(se)
pow_res = {}
for n in [10, 20, 40, 80]:
    p, d, se = power_auc(1.2, 0.8, n)
    pow_res[str(n)] = {"power": round(p,3), "true_auc_diff": round(d,4), "se": round(se,4)}
out["recovery_auc"] = {"auc_A":round(aucA,4), "auc_B":round(aucB,4), "by_n_per_delta":pow_res}

print(json.dumps(out, indent=2, ensure_ascii=False))
