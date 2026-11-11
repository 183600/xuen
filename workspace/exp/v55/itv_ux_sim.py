#!/usr/bin/env python3
"""Round 55 toy study: certificate revocation under iterative validation.

Scenario: a skill is safe before drift (p=0.93, rho_min=0.85) and degrades
after t_drift (p=0.72).  We compare three ways to *revoke* the safety claim:

  cumulative : one hedged e-process accumulated over all history
  block      : non-overlapping windows with Bonferroni alpha spending
  cusum      : one-sided CUSUM change detector on failures

The point is not to benchmark a production detector, but to expose the
"revocation latency" of a cumulative anytime-valid certificate and motivate
a two-timescale validation contract (certify + revoke).
"""
import json
import numpy as np

RNG = np.random.default_rng(55)
P0 = 0.85           # rho_min
P_PRE = 0.93        # safe regime
P_POST = 0.72       # degraded regime
T_DRIFT = 150
T_END = 400
ALPHA = 0.05
LAMS = np.array([0.1, 0.2, 0.35, 0.5, 0.7, 1.0])


def cumulative_detect(xs):
    log_k = np.zeros(len(LAMS))
    for t, x in enumerate(xs):
        log_k += np.log1p(LAMS * (P0 - x))
        m = log_k.max()
        k = np.exp(log_k - m).sum() * np.exp(m)
        if k >= 1.0 / ALPHA:
            return t
    return None


def block_detect(xs, width, thr):
    for b in range(0, len(xs) - width + 1, width):
        seg = xs[b:b + width]
        log_k = np.log1p(LAMS[None, :] * (P0 - seg[:, None])).sum(0)
        m = log_k.max()
        k = np.exp(log_k - m).sum() * np.exp(m)
        if k >= thr:
            return b + width - 1
    return None


def cusum_detect(xs, k=0.05, h=6.0):
    s = 0.0
    for t, x in enumerate(xs):
        s = max(0.0, s + (P0 - x) - k)
        if s >= h:
            return t
    return None


def summarise(delays, false_alarms, misses, runs):
    return {
        "false_alarm_rate": round(false_alarms / runs, 4),
        "detection_rate": round(1.0 - misses / runs, 4),
        "median_delay": None if not delays else round(float(np.median(delays)), 1),
        "p95_delay": None if not delays else round(float(np.percentile(delays, 95)), 1),
    }


def main(n_runs=2000, width=100):
    names = ("cumulative", "block", "cusum")
    delays = {n: [] for n in names}
    fa = {n: 0 for n in names}
    miss = {n: 0 for n in names}
    n_blocks = T_END // width
    block_thr = 1.0 / (ALPHA / n_blocks)

    for _ in range(n_runs):
        xs = np.r_[
            RNG.random(T_DRIFT) < P_PRE,
            RNG.random(T_END - T_DRIFT) < P_POST,
        ].astype(float)
        alarms = {
            "cumulative": cumulative_detect(xs),
            "block": block_detect(xs, width, block_thr),
            "cusum": cusum_detect(xs),
        }
        for name, alarm in alarms.items():
            if alarm is None:
                miss[name] += 1
            elif alarm < T_DRIFT:
                fa[name] += 1
            else:
                delays[name].append(alarm - T_DRIFT)

    out = {
        "config": {
            "runs": n_runs,
            "rho_min": P0,
            "p_pre": P_PRE,
            "p_post": P_POST,
            "t_drift": T_DRIFT,
            "t_end": T_END,
            "alpha": ALPHA,
            "block_width": width,
            "cusum_k": 0.05,
            "cusum_h": 6.0,
        },
        "revocation": {
            name: summarise(delays[name], fa[name], miss[name], n_runs)
            for name in names
        },
    }
    with open("exp/v55/itv_ux_sim_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
