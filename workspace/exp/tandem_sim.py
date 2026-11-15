#!/usr/bin/env python3
"""TANDEM-RAS synthetic mechanism check (round 70: multi-sensor fusion x dual-arm).

NOT benchmark evidence. Four isolated toy claims behind the round:

  A. Correlated agreement is not corroboration.  If k sources share a
     common-mode latent (pairwise correlation rho), then conditioning on
     "they agree" does NOT lower the probability that the agreed value is
     wrong as k grows; for rho -> 1 the false-consensus rate stays flat.
     R69's "k orthogonal sources agree" silently assumes rho = 0.

  B. Effective independent source count n_eff = k^2 / (1^T R 1) restores
     calibrated confidence.  The naive "k independent" prediction of the
     standard error (1/sqrt(k)) is overconfident by sqrt(k/n_eff); the
     n_eff prediction matches the empirical error.

  C. Active decorrelation is the only way to raise n_eff.  An action with
     efficacy gamma reduces rho -> rho*(1-gamma); gamma = 0 (same viewpoint /
     contact / time / body) has EXACTLY zero independence gain (the dual-arm
     analogue of R69's zero-information repeat).

  D. Consistency is not correctness.  A closed-chain residual can be driven
     to ~0 by a self-consistent wrong relative calibration.  Whether the
     loop-closure channel can detect a real object-model error depends on an
     EXOGENOUS calibration prior; with an uninformative prior its AUC -> 0.5.

Pure Python, deterministic seed.  Reproduce:
  python tandem_sim.py > tandem_results.json
"""
import json
import math
import random

SEED = 20261115


def norm(rng):
    return rng.gauss(0.0, 1.0)


def sample_equicorr(rng, k, rho):
    """Variance-1 equicorrelated samples: shared c + independent e."""
    c = norm(rng) * math.sqrt(max(rho, 0.0))
    s = math.sqrt(max(1.0 - rho, 0.0))
    return [c + norm(rng) * s for _ in range(k)]


def claim_A(n=40000):
    rows = []
    for rho in (0.0, 0.3, 0.6, 0.9, 0.99):
        for k in (2, 3, 5):
            agree = 0
            agree_wrong = 0
            for _ in range(n):
                xs = sample_equicorr(rng, k, rho)
                mean = sum(xs) / k
                spread = max(xs) - min(xs)
                if spread < 0.5:            # naive consensus threshold
                    agree += 1
                    if abs(mean) > 0.5:     # but the consensus is wrong
                        agree_wrong += 1
            rows.append({
                "rho": rho,
                "k": k,
                "agree_rate": agree / n,
                "false_consensus_rate_given_agree":
                    (agree_wrong / agree) if agree else 0.0,
            })
    return rows


def claim_B(n=40000):
    rows = []
    for rho in (0.0, 0.3, 0.6, 0.9, 0.99):
        for k in (2, 3, 5):
            means = []
            for _ in range(n):
                means.append(sum(sample_equicorr(rng, k, rho)) / k)
            mu = sum(means) / n
            var = sum((m - mu) ** 2 for m in means) / n
            emp_se = math.sqrt(var)
            n_eff = k * k / (k + k * (k - 1) * rho)   # = k/(1+(k-1)rho)
            naive_se = math.sqrt(1.0 / k)
            neff_se = math.sqrt(1.0 / n_eff)
            rows.append({
                "rho": rho,
                "k": k,
                "n_eff": n_eff,
                "empirical_se": emp_se,
                "naive_se": naive_se,
                "n_eff_se": neff_se,
                "naive_overconfidence": naive_se / emp_se,
                "n_eff_abs_error": abs(neff_se - emp_se),
            })
    return rows


def claim_C():
    rows = []
    for rho0 in (0.3, 0.6, 0.9):
        for gamma in (0.0, 0.3, 0.6, 1.0):
            rho1 = rho0 * (1.0 - gamma)
            n_eff0 = 2.0 / (1.0 + rho0)
            n_eff1 = 2.0 / (1.0 + rho1)
            rows.append({
                "rho_before": rho0,
                "decorrelation_efficacy": gamma,
                "rho_after": rho1,
                "n_eff_before": n_eff0,
                "n_eff_after": n_eff1,
                "independence_gain": n_eff1 - n_eff0,
            })
    return rows


def _auc(pos, neg):
    """P(score_pos > score_neg) via rank counting (Mann-Whitney)."""
    if not pos or not neg:
        return 0.0
    wins = 0.0
    for p in pos:
        for q in neg:
            wins += 1.0 if p > q else (0.5 if p == q else 0.0)
    return wins / (len(pos) * len(neg))


def claim_D(n=6000):
    """Loop residual r = d_obj - d_cal + noise.  Detect d_obj != 0."""
    rows = []
    d_true = 0.5
    for s_cal in (0.01, 0.05, 0.1, 0.3, 1.0):
        pos, neg = [], []
        for _ in range(n):
            d_cal = norm(rng) * s_cal
            d_obj = d_true
            r1 = abs(d_obj - d_cal + norm(rng) * 0.01)
            pos.append(r1)
            d_obj0 = 0.0
            r0 = abs(d_obj0 - d_cal + norm(rng) * 0.01)
            neg.append(r0)
        rows.append({
            "calibration_prior_std": s_cal,
            "loop_closure_auc": _auc(pos, neg),
        })
    return rows


if __name__ == "__main__":
    rng = random.Random(SEED)
    out = {
        "seed": SEED,
        "note": "synthetic mechanism check; not benchmark evidence",
        "A_correlated_agreement": claim_A(),
        "B_effective_independence": claim_B(),
        "C_active_decorrelation": claim_C(),
        "D_consistency_not_correctness": claim_D(),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
