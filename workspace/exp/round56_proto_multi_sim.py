"""Round 56 toy pilot: prototype-falsification + cross-embodiment transfer.

This is a *phenomenon* pilot, not evidence for a real robot method.
It asks three questions:
  1. Does a single-robot certificate falsely accept other embodiments?
  2. Can boundary-targeted prototype tests find counterexamples faster?
  3. Does averaging over robots hide a worst embodiment stratum?
"""
import json
import numpy as np

rng = np.random.default_rng(20261111)

N = 4000
L = rng.uniform(0.60, 1.00, N)       # leg length (m)
s = rng.uniform(0.05, 0.12, N)       # foot radius (m)
mu = rng.uniform(0.30, 0.80, N)      # friction
m = rng.uniform(8.0, 30.0, N)        # mass (kg)
sig = rng.uniform(0.005, 0.030, N)   # sensor/actuator noise


def sim_margin(L, s):
    """Deliberately incomplete simulator: no friction, mass, or noise."""
    return 0.025 + 0.10 * (L - 0.80) + 0.20 * (s - 0.085)


def true_margin(L, s, mu, m, sig, rng, reps=1):
    L, s, mu, m, sig = np.broadcast_arrays(
        *(np.asarray(v, dtype=float) for v in (L, s, mu, m, sig)))
    base = (0.025 + 0.10 * (L - 0.80) + 0.20 * (s - 0.085)
            + 0.035 * (mu - 0.55) - 0.004 * (m - 19.0))
    if reps == 1:
        return base + rng.normal(0, sig)
    noise = rng.normal(0, 1, base.shape + (reps,)) * sig[..., None]
    return base[..., None] + noise


theta = 0.02
pred = sim_margin(L, s)
Mtrue = true_margin(L, s, mu, m, sig, rng)
fail_true = Mtrue < 0.0

# ---- naive single-robot certificate: assume embodiment invariance ----
accept_naive = pred >= theta
fa_naive = float(np.sum(accept_naive & fail_true) / max(1, np.sum(accept_naive)))
risk_naive = float(np.mean(accept_naive & fail_true))

# ---- transfer-aware gate: stratified eval robots + residual bound ----
n_eval = 24
order = np.lexsort((s, L))
strata = np.array_split(order, n_eval)
eval_idx = np.array([rng.choice(st) for st in strata])
P = np.column_stack([(L - 0.8) / 0.2, (s - 0.085) / 0.035,
                     (mu - 0.55) / 0.25, (m - 19) / 11])
Pe = P[eval_idx]
d = np.sqrt(((P[:, None, :] - Pe[None, :, :]) ** 2).sum(2))
nn = d.argmin(1)
dnn = d.min(1)
res = np.array([
    true_margin(L[i], s[i], mu[i], m[i], sig[i], rng, 40).mean()
    - sim_margin(L[i], s[i]) for i in eval_idx
])
q = float(np.quantile(res, 0.10))
L_T = 0.02
pred_transfer = pred + res[nn] + q - L_T * dnn
accept_transfer = pred_transfer >= theta
fa_transfer = float(np.sum(accept_transfer & fail_true) /
                    max(1, np.sum(accept_transfer)))
risk_transfer = float(np.mean(accept_transfer & fail_true))
fr_transfer = float(np.sum(~accept_transfer & ~fail_true) /
                    max(1, np.sum(~accept_transfer)))

# ---- boundary-targeted prototype tests vs random tests ----
n_rand = 2000
rand_idx = rng.choice(N, n_rand, replace=False)
targ_pool = np.where((pred >= theta) & (pred <= theta + 0.012))[0]
targ_idx = rng.choice(targ_pool, size=min(n_rand, len(targ_pool)), replace=False)


def violation_rate(idx):
    mt = true_margin(L[idx], s[idx], mu[idx], m[idx], sig[idx], rng)
    acc = sim_margin(L[idx], s[idx]) >= theta
    return float(np.mean(acc & (mt < 0)))


vr_rand = violation_rate(rand_idx)
vr_targ = violation_rate(targ_idx)

# ---- worst embodiment stratum vs mean ----
bins = np.quantile(pred, [0, 0.25, 0.5, 0.75, 1.0])
stratum_risk = []
for a, b in zip(bins[:-1], bins[1:]):
    mask = (pred >= a) & (pred <= b)
    if mask.sum():
        stratum_risk.append(float(
            np.mean(accept_naive[mask] & fail_true[mask]) /
            max(1e-9, np.mean(accept_naive[mask]))))
mean_risk = float(np.mean(stratum_risk))
worst_ratio = float(max(stratum_risk) / max(mean_risk, 1e-9))

# ---- Pareto sweep of transfer safety margin ----
pareto = []
for lam in [0.0, 0.005, 0.01, 0.02, 0.03, 0.05]:
    acc = (pred + res[nn] - lam * dnn) >= theta
    pareto.append({
        "lambda": lam,
        "accept_rate": float(acc.mean()),
        "false_accept": float(np.sum(acc & fail_true) / max(1, np.sum(acc))),
        "false_reject": float(np.sum(~acc & ~fail_true) / max(1, np.sum(~acc))),
        "population_risk": float(np.mean(acc & fail_true)),
    })

out = {
    "seed": 20261111,
    "n_embodiments": N,
    "population_failure_rate": float(fail_true.mean()),
    "naive_single_robot": {
        "accept_rate": float(accept_naive.mean()),
        "false_accept": fa_naive,
        "population_risk": risk_naive,
    },
    "transfer_aware_gate": {
        "n_eval_robots": n_eval,
        "residual_q10": q,
        "mean_nearest_neighbour_distance": float(dnn.mean()),
        "accept_rate": float(accept_transfer.mean()),
        "false_accept": fa_transfer,
        "false_reject": fr_transfer,
        "population_risk": risk_transfer,
    },
    "prototype_test_efficiency": {
        "random_violation_rate": vr_rand,
        "boundary_targeted_violation_rate": vr_targ,
        "speedup": float(vr_targ / max(vr_rand, 1e-9)),
        "n_random": int(len(rand_idx)),
        "n_targeted": int(len(targ_idx)),
    },
    "stratum_risk": {
        "per_pred_quartile": stratum_risk,
        "mean": mean_risk,
        "worst_over_mean": worst_ratio,
    },
    "pareto_sweep": pareto,
    "note": "toy phenomenon pilot; not a real-robot result",
}

with open("/home/runner/work/xuen/xuen/workspace/exp/round56_proto_multi_results.json",
          "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
