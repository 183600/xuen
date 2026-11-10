"""Round 41 / v18: when is a self-initiated physical probe worth its steps?

Toy decision model (not a robot experiment).  A task needs N steps and succeeds
only if the latent lateral error |e| <= tol.  Prior e ~ N(0, sigma^2).  A probe
costs c steps and yields a posterior sigma' < sigma, but with probability q it
perturbs the object and makes the posterior worse (sigma_bad > sigma).
The score combines success and step score with two interpretations of g(N):
    g_recip(N) = 1/N                 (rank by inverse steps, A34)
    g_lin(N)   = 1 - N/N_max         (bounded linear step score, A34)
plus an optional failure penalty lambda.  Probe iff

    (w_s + lambda) * (p1_eff - p0) > w_n * (g(N) - g(N+c))
    p1_eff = (1-q) * p(sigma') + q * p(sigma_bad)

This file computes (a) the break-even probe cost c* and (b) the maximum
perturbation risk q_max that still justifies a fixed probe budget.  It is a
mathematical sanity check for IP-51, not evidence about the real challenge.

Run: PYTHONPATH=.pylibs python3 exp/v41/voi_probe_sim.py
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "voi_probe_sim_results.json")


def p_success(sigma, tol):
    if sigma <= 1e-12:
        return 1.0
    return math.erf(tol / (sigma * math.sqrt(2.0)))


def step_loss(c, N, Nmax, form, w_n=1.0):
    if form == "recip":
        return w_n * (1.0 / N - 1.0 / (N + c))
    return w_n * c / Nmax


def c_star(p_delta, N, Nmax, form, w_s=1.0, w_n=1.0, lam=0.0):
    A = (w_s + lam) * p_delta
    if A <= 0:
        return 0.0
    if form == "recip":
        if A * N >= w_n:
            return None            # any cost is justified
        return A * N * N / (w_n - A * N)
    return A * Nmax / w_n


def q_max(p0, p_good, p_bad, c, N, Nmax, form, w_s=1.0, w_n=1.0, lam=0.0):
    """Largest perturbation risk q such that probing is still worth it."""
    loss = step_loss(c, N, Nmax, form, w_n) / (w_s + lam)
    # (1-q) p_good + q p_bad - p0 >= loss
    denom = p_good - p_bad
    if denom <= 1e-12:
        return 0.0
    q = (p_good - p0 - loss) / denom
    return float(min(1.0, max(0.0, q)))


def main():
    tol = 0.005                      # 5 mm placement tolerance (illustrative)
    N = 300                          # steps per attempt (illustrative)
    Nmax = 600
    rows = []
    for ratio in (2.0, 1.0, 0.5, 0.25):
        sigma = tol * ratio
        p0 = p_success(sigma, tol)
        for gain in (0.5, 0.2, 0.1):       # sigma'/sigma (1 = no info)
            p_good = p_success(sigma * gain, tol)
            p_bad = p_success(math.hypot(sigma, 2.0 * tol), tol)
            row = {
                "sigma_over_tol": ratio, "posterior_over_prior": gain,
                "p0": round(p0, 4), "p_good": round(p_good, 4),
                "p_bad": round(p_bad, 4), "delta_p": round(p_good - p0, 4),
                "c_star_recip": {k: (None if (v := c_star(p_good - p0, N, Nmax, "recip")) is None
                                     else round(v, 2)) for k in ["value"]}["value"],
                "c_star_lin": round(c_star(p_good - p0, N, Nmax, "lin"), 2),
                "q_max": {},
            }
            for c in (5, 15, 30):
                row["q_max"][str(c)] = {
                    "recip": round(q_max(p0, p_good, p_bad, c, N, Nmax, "recip"), 3),
                    "lin": round(q_max(p0, p_good, p_bad, c, N, Nmax, "lin"), 3),
                }
            rows.append(row)
    # Monte Carlo check of the analytic p0/p1 for one cell
    rng = np.random.default_rng(20261110)
    M = 200_000
    sigma = tol * 2.0
    e = rng.normal(0.0, sigma, M)
    p0_mc = float((np.abs(e) <= tol).mean())
    sigma_p = sigma * 0.05
    e_meas = e + rng.normal(0.0, sigma_p, M)
    p1_mc = float((np.abs(e - e_meas) <= tol).mean())
    out = {
        "assumptions": {
            "tol_m": tol, "N_steps": N, "N_max": Nmax,
            "weights": {"success": 1.0, "steps": 1.0, "failure_penalty": 0.0},
            "perturbation_sigma_m": 2.0 * tol,
            "note": "illustrative only; N, tol, weights are parameters, not measured",
        },
        "grid": rows,
        "monte_carlo": {
            "sigma_over_tol": 2.0, "posterior_over_prior": 0.05,
            "p0_analytic": round(p_success(sigma, tol), 6), "p0_mc": p0_mc,
            "p1_analytic": round(p_success(sigma_p, tol), 6), "p1_mc": p1_mc,
        },
        "link_to_audit": {
            "observed_churn_core_frac": {"left": 0.2438, "right": 0.2302},
            "observed_dwell_frac": {"left": 0.1087, "right": 0.1017},
            "hypothesis": "if proactive probing removes half the churn at a "
                          "5% step budget, net step saving is ~7-9%",
            "warning": "churn includes necessary pre-grasp dwell; this is an "
                       "upper bound on reclaimable steps, not a measurement",
        },
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"{'s/tol':>6} {'post/prior':>10} {'p0':>6} {'p1':>6} {'dP':>6} "
          f"{'c*_1/N':>8} {'c*_lin':>8} {'qmax@5':>10} {'qmax@15':>10}")
    for r in rows:
        print(f"{r['sigma_over_tol']:6.2f} {r['posterior_over_prior']:10.2f} "
              f"{r['p0']:6.3f} {r['p_good']:6.3f} {r['delta_p']:6.3f} "
              f"{str(r['c_star_recip']):>8} {r['c_star_lin']:8.2f} "
              f"{r['q_max']['5']['recip']:>10.3f} {r['q_max']['15']['recip']:>10.3f}")
    print("\nMC   ", out["monte_carlo"])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
