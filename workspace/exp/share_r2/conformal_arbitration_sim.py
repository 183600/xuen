#!/usr/bin/env python3
"""Round-2 mechanism check (UniBot SHARE line): few-shot conformal arbitration.

This is a *synthetic mechanism check*, not UniBot benchmark evidence.  It asks:
if a slow generalist and a fast contact authority have complementary competence
along a latent context x, can a K-shot retrieval + split-conformal interval
decide when to switch without paying too much for harmful switches?

Model
-----
x        : latent contact-precision demand of a task/phase (support ~ N(0,1))
c_s(x)   : P(contact-phase success | slow authority, x)
c_f(x)   : P(contact-phase success | fast authority, x)
Delta(x) : c_f - c_s  (the quantity the arbiter needs)
y        : offline estimate of Delta for a support task, y = Delta + noise
predictor: linear fit Delta_hat = a + b x on support tasks
interval : split-conformal, q = (1-alpha) quantile of |y - Delta_hat| on calib
switch   : only if Delta_hat - q > kappa (lower confidence bound beats cost)

Outputs exp/share_r2/conformal_arbitration_results.json
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "conformal_arbitration_results.json")
RNG = np.random.default_rng(20261122)


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def c_slow(x):
    return sigmoid(1.2 - 1.0 * x)


def c_fast(x):
    return sigmoid(0.4 + 0.3 * x)


def delta_true(x):
    return c_fast(x) - c_slow(x)


def fit_linear(x, y):
    # y = a + b x, least squares
    A = np.stack([np.ones_like(x), x], axis=1)
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return coef


def run_once(K, alpha=0.10, kappa=0.02, noise=0.05, shift=0.0, n_query=4000):
    # support tasks drawn from the reference distribution
    x_s = RNG.normal(0.0, 1.0, size=K)
    y_s = delta_true(x_s) + RNG.normal(0.0, noise, size=K)
    # split conformal: half fit, half calibrate (at least 1 each)
    n_fit = max(1, K // 2)
    x_fit, y_fit = x_s[:n_fit], y_s[:n_fit]
    x_cal, y_cal = x_s[n_fit:], y_s[n_fit:]
    a, b = fit_linear(x_fit, y_fit)
    if len(x_cal) == 0:
        q = np.inf
    else:
        res = np.abs(y_cal - (a + b * x_cal))
        # finite-sample conformal quantile: ceil((n+1)(1-alpha))/n
        n = len(res)
        level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
        q = float(np.quantile(res, level, method="higher"))
    # query tasks, optionally shifted
    x_q = RNG.normal(shift, 1.0, size=n_query)
    d_true = delta_true(x_q)
    d_hat = a + b * x_q
    # policies
    def evaluate(switch):
        gain = np.where(switch, d_true, 0.0)
        harmful = switch & (d_true < 0.0)
        return {
            "mean_gain": float(gain.mean()),
            "switch_rate": float(switch.mean()),
            "harmful_switch_rate": float(harmful.mean()),
            "harmful_share_of_switches": float(harmful.sum() / max(1, switch.sum())),
        }
    no = evaluate(np.zeros_like(x_q, dtype=bool))
    point = evaluate(d_hat > kappa)
    conf = evaluate((d_hat - q) > kappa)
    oracle = evaluate(d_true > kappa)
    # interval coverage on query (true Delta inside [d_hat-q, d_hat+q])
    cover = float(np.mean(np.abs(d_true - d_hat) <= q))
    return {
        "K": K,
        "alpha": alpha,
        "kappa": kappa,
        "noise": noise,
        "shift": shift,
        "q": q,
        "coverage_query": cover,
        "no_switch": no,
        "point_switch": point,
        "conformal_switch": conf,
        "oracle_switch": oracle,
    }


def main():
    out = {"note": "synthetic mechanism check; not UniBot benchmark evidence",
           "competence_model": {"c_slow": "sigmoid(1.2 - 1.0*x)",
                                "c_fast": "sigmoid(0.4 + 0.3*x)",
                                "delta": "c_fast - c_slow"},
           "sweeps": {}}
    for shift in [0.0, 0.5, 1.0]:
        rows = []
        for K in [2, 5, 10, 20, 50, 100, 200]:
            reps = [run_once(K, shift=shift) for _ in range(200)]
            agg = {"K": K, "shift": shift}
            for pol in ["no_switch", "point_switch", "conformal_switch", "oracle_switch"]:
                agg[pol] = {
                    "mean_gain": float(np.mean([r[pol]["mean_gain"] for r in reps])),
                    "switch_rate": float(np.mean([r[pol]["switch_rate"] for r in reps])),
                    "harmful_switch_rate": float(np.mean([r[pol]["harmful_switch_rate"] for r in reps])),
                }
            agg["coverage_query"] = float(np.mean([r["coverage_query"] for r in reps]))
            agg["mean_q"] = float(np.mean([r["q"] for r in reps]))
            rows.append(agg)
        out["sweeps"][f"shift_{shift}"] = rows
    json.dump(out, open(OUT, "w"), indent=2)
    print(json.dumps(out, indent=2)[:6000])


if __name__ == "__main__":
    main()
