#!/usr/bin/env python3
"""CPAI synthetic calibration: sequential change detection + per-instance
personalization for "regressed" detection at action-chunk boundaries.

This is a *synthetic* illustration of the decision rule, NOT a robot result.
Question: given noisy progress evidence and a per-instance nuisance offset,
which verifier attains the best detection/delay at a fixed false-redo budget?
  - fixed1: v2-like one-shot threshold on the progress residual
  - fixed2: one-shot threshold with 2-checkpoint confirmation
  - cusum : one-sided CUSUM on the log-likelihood ratio (persistent reversal)
Personalization estimates delta_hat from n_cal intact checkpoints and tests
the calibrated residual instead of the raw one.

Generative model per subgoal, H checkpoints:
  H0 (progress intact):  x_t = delta + N(+mu, sigma)
  H1 (progress undone):  x_t = delta + N(-mu, sigma)  for t >= s
  delta ~ N(0, sigma_inst)
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cpai_sprt_results.json")

MU = 1.0
SIGMA = 1.0
SIGMA_INST = 0.8
H = 8
N_CAL = 3
C_REDO = 5.0   # cost of a wasted redo (step-score-equivalent units)
L_MISS = 35.0  # lost step score when a regression is missed
C_DELAY = 1.0  # cost per checkpoint of detection delay
N_EP = 40000
SEED = 20261113


def _prep(x, delta_hat, use_pers):
    if use_pers:
        return x - delta_hat[:, None], 1.0 + 1.0 / N_CAL
    return x, 1.0


def cusum_vec(x, delta_hat, use_pers, h):
    """One-sided CUSUM; returns first alarm time (H if never)."""
    z, v = _prep(x, delta_hat, use_pers)
    n = z.shape[0]
    S = np.zeros(n)
    alarm_t = np.full(n, H, dtype=int)
    active = np.ones(n, dtype=bool)
    for t in range(H):
        idx = np.where(active)[0]
        if len(idx) == 0:
            break
        S[idx] = np.maximum(0.0, S[idx] + (-2.0 * MU * z[idx, t] / v))
        hit = idx[S[idx] >= h]
        alarm_t[hit] = t
        active[hit] = False
    return alarm_t


def fixed_vec(x, delta_hat, use_pers, tau, confirm=1):
    z, _ = _prep(x, delta_hat, use_pers)
    n = z.shape[0]
    below = z < tau
    alarm_t = np.full(n, H, dtype=int)
    fired = np.zeros(n, dtype=bool)
    run = np.zeros(n, dtype=int)
    for t in range(H):
        run = np.where(below[:, t], run + 1, 0)
        hit = (~fired) & (run >= confirm)
        alarm_t[hit] = t
        fired[hit] = True
    return alarm_t


def score(alarm_t, s, has_regression):
    det = (alarm_t < H) & (alarm_t >= s)
    fa = (alarm_t < H) & (alarm_t < s)
    out = {"false_alarm_rate": float(np.mean(fa))}
    if has_regression:
        out["detect_rate"] = float(np.mean(det))
        d = (alarm_t[det] - s[det] + 1)
        out["mean_delay_ckpt"] = float(np.mean(d)) if len(d) else None
        p_miss = 1.0 - out["detect_rate"]
        dd = out["mean_delay_ckpt"] or 0.0
        out["expected_loss"] = float(out["false_alarm_rate"] * C_REDO
                                     + p_miss * L_MISS + dd * C_DELAY)
    else:
        out["detect_rate"] = None
        out["mean_delay_ckpt"] = None
        out["expected_loss"] = float(out["false_alarm_rate"] * C_REDO)
    return out


def tune(method, x0, dh, target_fa):
    """Pick the parameter that gets H0 false-alarm closest to target_fa."""
    if method.startswith("cusum"):
        grid = np.linspace(0.5, 16.0, 80)
        pers = method.endswith("personalized") or method == "cusum_oracle"
        fn = lambda p: cusum_vec(x0, dh, pers, p)
    else:
        grid = np.linspace(-4.0, 2.0, 121)
        confirm = 1 if method.startswith("fixed1") else 2
        fn = lambda p: fixed_vec(x0, dh, method.endswith("personalized"),
                                 p, confirm)
    best_p, best_gap, best_fa = None, 1e9, None
    for p in grid:
        fa = float(np.mean(fn(p) < H))
        gap = abs(fa - target_fa)
        if gap < best_gap:
            best_p, best_gap, best_fa = float(p), gap, fa
    return best_p, best_fa


def main():
    rng = np.random.default_rng(SEED)
    delta = rng.normal(0.0, SIGMA_INST, N_EP)
    delta_hat = delta + rng.normal(0.0, SIGMA / np.sqrt(N_CAL), N_EP)

    x0 = delta[:, None] + rng.normal(MU, SIGMA, (N_EP, H))
    s0 = np.full(N_EP, H)
    s1 = rng.integers(1, H, N_EP)
    x1 = delta[:, None] + rng.normal(MU, SIGMA, (N_EP, H))
    for i in range(N_EP):
        x1[i, s1[i]:] = delta[i] + rng.normal(-MU, SIGMA, H - s1[i])

    methods = [
        "fixed1_population", "fixed1_personalized",
        "fixed2_population", "fixed2_personalized",
        "cusum_population", "cusum_personalized", "cusum_oracle",
    ]

    results = {
        "config": dict(MU=MU, SIGMA=SIGMA, SIGMA_INST=SIGMA_INST, H=H,
                       N_CAL=N_CAL, C_REDO=C_REDO, L_MISS=L_MISS,
                       C_DELAY=C_DELAY, N_EP=N_EP, SEED=SEED,
                       note="synthetic calibration; not a robot result"),
        "matched_false_alarm": {},
    }

    for target in (0.05, 0.10, 0.20):
        key = f"target_fa_{int(target * 100)}"
        results["matched_false_alarm"][key] = {}
        for name in methods:
            dh = delta if name == "cusum_oracle" else delta_hat
            p, fa0 = tune(name, x0, dh, target)
            if name.startswith("cusum"):
                at = cusum_vec(x1, dh, name.endswith("personalized")
                               or name == "cusum_oracle", p)
                at0 = cusum_vec(x0, dh, name.endswith("personalized")
                                or name == "cusum_oracle", p)
            else:
                confirm = 1 if name.startswith("fixed1") else 2
                pers = name.endswith("personalized")
                at = fixed_vec(x1, dh, pers, p, confirm)
                at0 = fixed_vec(x0, dh, pers, p, confirm)
            results["matched_false_alarm"][key][name] = {
                "param": p,
                "H0_false_alarm": float(np.mean(at0 < H)),
                **score(at, s1, True),
            }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
