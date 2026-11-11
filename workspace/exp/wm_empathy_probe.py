#!/usr/bin/env python3
"""Round-55 probe: world-model imagination leakage + empathy trust calibration.

Pure-numpy synthetic probe (NOT a robotics benchmark). It is designed to test:
  1) imagined rollouts can inflate a certificate's coverage when the world model
     hallucinates outside its validity domain (circular evidence);
  2) a truthful-but-miscalibrated expression can cause over-trust / under-trust
     even when the underlying capability is fixed.

Run: python3 exp/wm_empathy_probe.py
"""
import sys
sys.path.insert(0, "/home/runner/work/xuen/xuen/workspace/.pylibs")
import json
import numpy as np

RNG = np.random.default_rng(20261111)

# ----------------------------------------------------------------------------
# Part A: imagination leakage
# ----------------------------------------------------------------------------
N_ACT = 101
A = np.linspace(0.0, 1.0, N_ACT)
THETA = 0.60          # certificate success threshold
Z = 1.64              # one-sided 95% lower confidence bound
N_DRAW = 60

def p_true(a):
    return np.where(a >= 0.6, 0.95, 0.05)

def p_model(a):
    p = p_true(a).copy()
    p[a < 0.30] = 0.90            # OOD hallucination: bad actions look good
    return p

# The world model is only audited/calibrated on this validity domain.
IN_VALID = (A >= 0.30) & (A <= 0.70)

real = RNG.random((N_ACT, N_DRAW)) < p_true(A)[:, None]
imag = RNG.random((N_ACT, N_DRAW)) < p_model(A)[:, None]

def lower_bound(mean, n, discount=0.0):
    return mean - Z * np.sqrt(np.clip(mean * (1 - mean), 0, 1) / n) - discount

def evaluate(certified, real_samples):
    good = p_true(A) >= THETA
    n_cert = certified.sum()
    fa = (certified & ~good).sum() / max(n_cert, 1)
    cov = (certified & good).sum() / max(good.sum(), 1)
    return {"false_accept": float(fa), "coverage": float(cov),
            "n_certified": int(n_cert), "real_samples": int(real_samples)}

modes = {}
# pure imagination: model certifies itself
modes["imag_only"] = evaluate(
    lower_bound(imag.mean(1), N_DRAW) >= THETA, 0)
# real evidence only
modes["real_only"] = evaluate(
    lower_bound(real.mean(1), N_DRAW) >= THETA, N_ACT * N_DRAW)
# naive mixing: 80% imagined + 20% real, validity ignored
naive_mean = 0.8 * imag.mean(1) + 0.2 * real.mean(1)
modes["naive_mix"] = evaluate(
    lower_bound(naive_mean, N_DRAW) >= THETA, int(0.2 * N_ACT * N_DRAW))
# grounded: imagined only inside V_w, real outside; audit discount on imagined
g_mean = np.where(IN_VALID, imag.mean(1), real.mean(1))
g_disc = np.where(IN_VALID, 0.03, 0.0)
modes["grounded"] = evaluate(
    lower_bound(g_mean, N_DRAW, g_disc) >= THETA,
    int((~IN_VALID).sum() * N_DRAW))

# ----------------------------------------------------------------------------
# Part B: empathy expression and trust calibration
# ----------------------------------------------------------------------------
N_EP = 6000
levels = np.array([0.10, 0.30, 0.60, 0.90])
p_ep = RNG.choice(levels, size=N_EP, p=[0.30, 0.25, 0.25, 0.20])
# 45% of the hard tasks are outside the world-model validity domain, where the
# model hallucinates a high success probability.
ood = (p_ep <= 0.30) & (RNG.random(N_EP) < 0.45)
p_hat = np.clip(p_ep + 0.10, 0, 1)
p_hat[ood] = 0.88

HEDGE = 0.50
# Audited calibration: subtract the model's validated optimistic residual on
# the validity domain, and abstain (low confidence) on detected-OOD items.
# In-domain residual is tiny (the audit measured it); OOD is not trustworthy.
p_cal = np.clip(p_hat - 0.05, 0, 1)
p_cal[ood] = 0.30

def ece(c, p, bins=10):
    idx = np.clip((c * bins).astype(int), 0, bins - 1)
    err = 0.0
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        err += m.mean() * abs(c[m].mean() - p[m].mean())
    return float(err)

def simulate(expressed, seed):
    rng = np.random.default_rng(seed)
    order = rng.permutation(N_EP)
    tau, lam, thresh = 0.50, 0.60, 0.52
    eta_pos, eta_neg = 0.15, 0.25
    over = under = succ = delegated = 0
    for i in order:
        c = expressed[i]
        tau_post = (1 - lam) * tau + lam * c
        dec = tau_post >= thresh
        if dec:
            delegated += 1
            ok = rng.random() < p_ep[i]
            if ok:
                succ += 1
                tau = tau_post + eta_pos * (1 - tau_post)
            else:
                tau = tau_post - eta_neg * tau_post
        else:
            tau = tau_post
        if dec and p_ep[i] < 0.50:
            over += 1
        if (not dec) and p_ep[i] > 0.70:
            under += 1
    return {"over_trust_rate": over / N_EP,
            "under_trust_rate": under / N_EP,
            "team_success": succ / N_EP,
            "delegation_rate": delegated / N_EP,
            "delegation_precision": succ / max(delegated, 1),
            "trust_utility": (succ - over) / N_EP,
            "expressive_ece": ece(expressed, p_ep)}

policies = {
    "raw_model_confidence": p_hat,
    "constant_hedge": np.full(N_EP, HEDGE),
    "calibrated_empathy": p_cal,
}
trust = {k: simulate(v, 7000 + i) for i, (k, v) in enumerate(policies.items())}

out = {
    "part_a_imagination_leakage": modes,
    "part_b_trust_calibration": trust,
    "config": {"theta": THETA, "n_draw": N_DRAW, "n_episodes": N_EP,
               "validity_domain": [0.30, 0.70], "ood_rate_hard": 0.45},
}
print(json.dumps(out, indent=2))
with open("/home/runner/work/xuen/xuen/workspace/exp/wm_empathy_probe_results.json", "w") as f:
    json.dump(out, f, indent=2)
