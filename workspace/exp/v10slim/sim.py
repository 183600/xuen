"""Synthetic check for v10 MetricVoiceGauge-SLIM.

Two independent toy studies (NOT a full simulator, NOT measured robot logs):

1. Joint coverage of multi-task heads under a shared trunk, with a common
   latent factor producing cross-head error correlation.  Compares
   Bonferroni-calibrated joint coverage against naive per-head marginal
   calibration, both in-distribution and under a scale shift.
2. Anytime-depth latency bookkeeping: stage-cost model -> latency, beta
   inflation, effective chunk length, and speculative-prefetch boundary
   latency.

Run: PYTHONPATH=.pylibs python3 exp/v10slim/sim.py
"""
import json
import numpy as np

RNG = np.random.default_rng(20261116)

# ---------------------------------------------------------------- study 1
N_HEADS = 5
DEPTHS = (1, 2, 3)
ALPHA = 0.05                 # target family-wise error
RHO = 0.5                    # shared-trunk latent correlation
BASE = np.array([1.00, 1.20, 0.80, 1.50, 1.10])
FLOOR = np.array([0.30, 0.35, 0.25, 0.40, 0.30])
DECAY = 0.55
N_CAL = 4000
N_TEST = 40000


def draw(n, mult=1.0):
    """Errors for each depth: (n, N_HEADS). Common latent z -> correlated heads."""
    z = RNG.normal(size=(n, 1))
    common = np.sqrt(RHO) * z
    idio = np.sqrt(1.0 - RHO) * RNG.normal(size=(n, N_HEADS))
    out = []
    for d in DEPTHS:
        sigma = (BASE * DECAY ** (d - 1) + FLOOR) * mult
        out.append(np.abs((common + idio) * sigma))
    return out


def conformal_quantile(scores, level):
    n = len(scores)
    k = int(np.ceil((n + 1) * level))
    if k > n:
        return float("inf")
    return float(np.sort(scores)[k - 1])


def calibrate(alpha_per_head):
    cal = draw(N_CAL)
    q = []
    for d_idx in range(len(DEPTHS)):
        q.append([conformal_quantile(cal[d_idx][:, h],
                                     1.0 - float(alpha_per_head[h]))
                  for h in range(N_HEADS)])
    return np.array(q)


def coverage(q, mult):
    test = draw(N_TEST, mult=mult)
    per_depth = []
    for d_idx in range(len(DEPTHS)):
        inside = test[d_idx] <= q[d_idx]
        per_head = inside.mean(axis=0)
        joint = inside.all(axis=1).mean()
        per_depth.append({
            "depth": DEPTHS[d_idx],
            "per_head_coverage": [round(float(x), 4) for x in per_head],
            "joint_coverage": round(float(joint), 4),
            "mean_envelope": round(float(np.mean(q[d_idx])), 4),
        })
    return per_depth


def rolling_alarm(mult, window=200, margin=0.03, seq=20000, seed=7):
    """Per-head rolling miss-rate alarm.

    Returns (first_alarm_index_or_None, alarmed_window_fraction) per head.
    A window is 200 samples = 4 s at 50 Hz.
    """
    r = np.random.default_rng(seed)
    z = r.normal(size=(seq, 1))
    common = np.sqrt(RHO) * z
    idio = np.sqrt(1.0 - RHO) * r.normal(size=(seq, N_HEADS))
    q_cal = calibrate(np.full(N_HEADS, ALPHA / N_HEADS))
    sigma = (BASE * DECAY ** 2 + FLOOR) * mult
    err = np.abs((common + idio) * sigma)
    miss = err > q_cal[-1]
    first, rates = [], []
    for h in range(N_HEADS):
        alarm = None
        alarmed = 0
        checks = 0
        for t in range(window, seq):
            rate = miss[t - window:t, h].mean()
            checks += 1
            if rate > ALPHA / N_HEADS + margin:
                alarmed += 1
                if alarm is None:
                    alarm = int(t)
        first.append(alarm)
        rates.append(round(alarmed / checks, 4))
    return first, rates


cal_bonf = calibrate(np.full(N_HEADS, ALPHA / N_HEADS))
cal_naive = calibrate(np.full(N_HEADS, ALPHA))
study1 = {
    "bonferroni": {
        "in_distribution": coverage(cal_bonf, 1.0),
        "shift_1.5x": coverage(cal_bonf, 1.5),
    },
    "naive_marginal": {
        "in_distribution": coverage(cal_naive, 1.0),
    },
    "shift_alarm": dict(zip(("first_detect_sample", "alarmed_window_fraction"),
                            rolling_alarm(1.5))),
    "in_dist_alarm": dict(zip(("first_detect_sample", "alarmed_window_fraction"),
                              rolling_alarm(1.0))),
}

# ---------------------------------------------------------------- study 2
TRUNK_WCET = {1: 1.60, 2: 2.80, 3: 4.00}       # ms
HEAD_WCET = np.array([0.18, 0.22, 0.16, 0.14, 0.18])
SAFE_HEADS = (0, 1, 2)                          # clearance / effort / grasp
FUSE_OVERHEAD = 0.55
D_MARGIN = 0.50
BETA_V9 = 0.02
BETA_MAX = 0.12
LAMBDA_SAFE = np.array([0.02, 0.02, 0.02])     # per-head certificate sensitivity
K_MAX = 10
V9_SOFT_PATH = 9.50                            # ms, independent modules
CHUNK_FULL = 12.0                              # ms, v9 5 Hz chunk generation
PREFETCH_VERIFY = 1.20                         # ms
PREFETCH_HIT = 0.75


def latency(d):
    return TRUNK_WCET[d] + HEAD_WCET.sum() + FUSE_OVERHEAD


def envelopes_at(d):
    idx = DEPTHS.index(d)
    return cal_bonf[idx]


def beta_eff(d):
    """Normalized envelope inflation: eps_tilde_h(d) = eps_h(d)/eps_h(D)-1."""
    full = envelopes_at(3)
    cur = envelopes_at(d)
    ratio = np.maximum(0.0, cur[list(SAFE_HEADS)] / full[list(SAFE_HEADS)] - 1.0)
    return BETA_V9 + float(np.sum(LAMBDA_SAFE * ratio))


def k_eff(d):
    b = beta_eff(d)
    return int(max(1, np.floor(K_MAX * (1.0 - min(1.0, b / BETA_MAX)))))


deadlines = [3.6, 4.0, 5.0, 6.0, 8.0]
pareto = []
for D in deadlines:
    feasible = [d for d in DEPTHS if latency(d) <= D - D_MARGIN]
    d = max(feasible) if feasible else 1
    pareto.append({
        "deadline_ms": D,
        "exit_depth": d,
        "latency_wcet_ms": round(latency(d), 3),
        "beta_eff": round(beta_eff(d), 4),
        "K_eff": k_eff(d),
        "uses_v9_independent_fallback": not feasible,
    })

prefetch_boundary = PREFETCH_HIT * PREFETCH_VERIFY + (1 - PREFETCH_HIT) * CHUNK_FULL
prefetch_amortized = prefetch_boundary / k_eff(3)

study2 = {
    "v9_independent_soft_path_ms": V9_SOFT_PATH,
    "v10_shared_full_depth_ms": round(latency(3), 3),
    "v10_speedup_full_depth": round(V9_SOFT_PATH / latency(3), 2),
    "pareto": pareto,
    "prefetch": {
        "hit_rate": PREFETCH_HIT,
        "boundary_ms": round(prefetch_boundary, 3),
        "boundary_speedup_vs_v9": round(CHUNK_FULL / prefetch_boundary, 2),
        "amortized_ms_per_cycle_at_full_depth": round(prefetch_amortized, 3),
    },
}

print(json.dumps({"study1_joint_coverage": study1,
                  "study2_latency": study2}, indent=2, ensure_ascii=False))
