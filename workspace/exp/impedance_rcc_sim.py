"""Synthetic mechanism check for the IMPEDANCE / software-RCC idea (UniBot line, round 2).

NOT benchmark evidence.  This script isolates *one* mechanism question that the
next round would otherwise have to burn scarce real-robot time on:

  Q1  Under a POSITION-ONLY action interface (no torque / no tactile command),
      does anisotropic reference compliance (a "software RCC": low lateral
      stiffness, high axial stiffness) recover peg-in-hole success that a stiff
      position controller loses to lateral misalignment / jamming?
  Q2  Is there an interior optimum in lateral stiffness (too soft = bias pushes
      the peg out of the chamfer capture zone; too stiff = normal force explodes
      and the peg jams)?
  Q3  Can contact be detected WITHOUT a force sensor, from the residual between
      the commanded pose and the observed pose alone (AUROC)?
  Q4  Is anisotropic (RCC) compliance better than *uniform* softening at the
      same lateral stiffness (i.e. does keeping axial stiffness high matter)?

Generative model (DECLARED, NOT FIT; all quantities unitless):
  - Rigid chamfered hole. Clearance c, chamfer width w, chamfer depth h.
    opening(s) = c + w*(1 - s/h) for 0<=s<=h; = c for s>h.
  - The base policy commands lateral target y_ref = e (e ~ N(0, sigma_e)),
    i.e. its pose error is the misalignment we must survive.
  - A constant lateral bias force f_b exists (cable / gravity component / friction
    bias).  Under lateral stiffness k_l it shifts the effective target by
    f_b / k_l, so very soft control can miss the chamfer entirely.
  - Contact is a rigid wall: actual lateral position y = clamp(y_eff, +-opening).
    The normal force the position controller presses with is
        N = k_l * max(0, |y_eff| - opening) * cos(theta)
    where theta is the chamfer wall slope.  Jam if N > N_jam.
  - Axial insertion follows an overdamped admittance:
        s_dot = (1/d) * ( -k_a*(s - s_ref) - N*sin(theta) ),   s_ref = v*t
    A too-soft axial stiffness therefore stalls (timeout) -> this is what makes
    *uniform* softening worse than anisotropic softening.
  - Observed pose = true pose + N(0, sigma_m^2); contact detector score is the
    normalised command-observation residual.
"""

import json
import math
import os
import numpy as np
from scipy.stats import rankdata

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "impedance_rcc_results.json")

# geometry (unitless; 0.04 clearance ~ 4 mm, 0.16 chamfer ~ 16 mm)
C = 0.04
W = 0.16
H = 0.03
S_TGT = 0.06

# dynamics
D = 1.0
V = 0.08          # commanded insertion speed (depth / s)
DT = 1.0 / 500.0
T_MAX = 1.5
N_JAM = 40.0      # normal-force jam threshold
F_BIAS = 5.0      # constant lateral bias force

SIGMA_M = 0.002   # measurement noise for the contact detector

K_AX_HI = 4000.0  # anisotropic RCC keeps axial stiffness high
K_LAT_GRID = np.array([10, 18, 32, 56, 100, 180, 320, 560,
                       1000, 1800, 3200, 5600, 10000], dtype=float)
SIGMA_GRID = [0.04, 0.07, 0.10]
N_EPS = 20000
RNG = np.random.default_rng(20261119)


def slope_factor(s):
    """Return (cos_theta, sin_theta) of the chamfer wall at depth s."""
    in_chamfer = (s >= 0) & (s <= H)
    # wall slope d(opening)/ds = -W/H -> normal tilt
    tan_t = np.where(in_chamfer, W / H, 0.0)
    norm = np.sqrt(1.0 + tan_t * tan_t)
    return 1.0 / norm, tan_t / norm


def opening_of(s):
    s_c = np.clip(s, 0.0, H)
    op = C + W * (1.0 - s_c / H)
    return np.where(s > H, C, op)


def run_condition(k_lat, k_ax, sigma_e, n=N_EPS, rng=RNG, sigma_m=None, return_scores=False):
    """Vectorised Monte Carlo for one (k_lat, k_ax, sigma_e) condition."""
    if sigma_m is None:
        sigma_m = SIGMA_M
    e = rng.normal(0.0, sigma_e, size=n)
    y_eff = e + F_BIAS / k_lat
    y_ref = e

    # capture-zone miss: outside the funnel at the top -> lands on the rim
    miss = np.abs(y_eff) > (C + W)

    s = np.zeros(n)
    jam = np.zeros(n, dtype=bool)
    contact_any = np.zeros(n, dtype=bool)
    b_sum = np.zeros(n)
    b_cnt = np.zeros(n)
    b_hat = None

    score_samples = []
    label_samples = []

    for t_i in range(int(T_MAX / DT)):
        t = t_i * DT
        s_ref = min(V * t, S_TGT)
        op = opening_of(s)
        abs_eff = np.abs(y_eff)
        in_contact = abs_eff > op
        contact_any |= in_contact

        cos_t, sin_t = slope_factor(s)
        overlap = np.maximum(0.0, abs_eff - op)
        N = k_lat * overlap * cos_t
        jam |= N > N_JAM

        # axial admittance (overdamped), exact exponential integrator
        f_s = N * sin_t
        s_eq = s_ref - f_s / k_ax
        decay = math.exp(-k_ax * DT / D)
        s = s_eq + (s - s_eq) * decay

        # observed pose
        y_actual = np.sign(y_eff) * np.minimum(abs_eff, op)
        y_obs = y_actual + rng.normal(0.0, sigma_m, size=n)
        s_obs = s + rng.normal(0.0, sigma_m, size=n)

        # online bias estimate from the pre-contact phase (first 25 steps),
        # then a bias-corrected lateral residual = contact signal
        if t_i < 25:
            b_sum += (y_obs - y_ref)
            b_cnt += 1.0
            if t_i == 24:
                b_hat = b_sum / b_cnt
        else:
            r = np.abs((y_obs - y_ref) - b_hat) / 0.01
            if t_i % 40 == 0:
                score_samples.append(r)
                label_samples.append(in_contact)

    reached = s >= S_TGT - 5e-3
    y_final = np.sign(y_eff) * np.minimum(np.abs(y_eff), opening_of(s))
    inside = np.abs(y_final) <= C + 1e-6
    success = (~jam) & (~miss) & reached & inside

    scores = np.concatenate(score_samples)
    labels = np.concatenate(label_samples)
    auc = auroc(scores, labels) if labels.any() else float("nan")

    out = {
        "k_lat": float(k_lat),
        "k_ax": float(k_ax),
        "sigma_e": float(sigma_e),
        "success": float(success.mean()),
        "jam_rate": float((jam & ~miss).mean()),
        "miss_rate": float(miss.mean()),
        "contact_rate": float(contact_any.mean()),
        "detect_auroc": float(auc),
    }
    if return_scores:
        out["_scores"] = scores
        out["_labels"] = labels
    return out


def auroc(scores, labels):
    """Mann-Whitney AUROC with average ranks for ties."""
    labels = np.asarray(labels, dtype=bool)
    n_pos = labels.sum()
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = rankdata(scores)
    auc = (ranks[labels].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


def main():
    results = {"declared_model": True, "config": {
        "C": C, "W": W, "H": H, "S_TGT": S_TGT, "V": V,
        "N_JAM": N_JAM, "F_BIAS": F_BIAS, "SIGMA_M": SIGMA_M,
        "K_AX_HI": K_AX_HI, "N_EPS": N_EPS,
    }, "sweeps": {}, "anisotropic_vs_uniform": {}}

    # ---- A. constant lateral stiffness sweep (anisotropic: axial stays stiff)
    print("== A. lateral stiffness sweep (k_ax = %.0f) ==" % K_AX_HI)
    for sigma in SIGMA_GRID:
        rows = []
        for k in K_LAT_GRID:
            r = run_condition(k, K_AX_HI, sigma)
            rows.append(r)
        results["sweeps"][str(sigma)] = rows
        best = max(rows, key=lambda r: r["success"])
        stiff = next(r for r in rows if abs(r["k_lat"] - 10000) < 1e-9)
        print("  sigma=%.2f  best k=%.0f succ=%.3f | k=1e4 succ=%.3f "
              "| delta=+%.3f | AUROC(best)=%.3f"
              % (sigma, best["k_lat"], best["success"], stiff["success"],
                 best["success"] - stiff["success"], best["detect_auroc"]))

    # ---- B. anisotropic vs uniform softening at matched lateral stiffness
    print("== B. anisotropic (k_ax=%.0f) vs uniform (k_ax=k_lat) ==" % K_AX_HI)
    sigma = 0.07
    rows = []
    for k in K_LAT_GRID:
        aniso = run_condition(k, K_AX_HI, sigma)
        unif = run_condition(k, k, sigma)
        rows.append({"k": float(k),
                     "aniso_success": aniso["success"],
                     "unif_success": unif["success"],
                     "aniso_jam": aniso["jam_rate"],
                     "unif_jam": unif["jam_rate"],
                     "unif_miss": unif["miss_rate"]})
    results["anisotropic_vs_uniform"] = rows
    for r in rows:
        if r["k"] in (32.0, 100.0, 320.0, 1000.0):
            print("  k=%6.0f  aniso=%.3f  uniform=%.3f  (delta %+0.3f)"
                  % (r["k"], r["aniso_success"], r["unif_success"],
                     r["aniso_success"] - r["unif_success"]))

    # ---- C. detector AUROC across noise (fixed good k)
    print("== C. sensorless contact detector vs measurement noise ==")
    detect = []
    for sm in [0.001, 0.002, 0.004, 0.008, 0.016]:
        r = run_condition(180.0, K_AX_HI, 0.07, n=8000, sigma_m=sm)
        detect.append({"sigma_m": sm, "auroc": r["detect_auroc"]})
        print("  sigma_m=%.3f  AUROC=%.3f" % (sm, r["detect_auroc"]))
    results["detector_noise"] = detect

    # ---- D. high-precision operating point (FPR <= 2%), matching the
    #         "intervene only when confident" design rule from the prior round
    print("== D. precision-constrained contact detector (FPR <= 2%) ==")
    prec = []
    for sm in [0.002, 0.004, 0.008]:
        r = run_condition(180.0, K_AX_HI, 0.07, n=8000, sigma_m=sm,
                          return_scores=True)
        sc, lb = r["_scores"], r["_labels"]
        neg = sc[~lb]
        thr = np.quantile(neg, 0.98)          # only 2% of free-space steps fire
        tpr = float((sc[lb] > thr).mean())
        prec.append({"sigma_m": sm, "auroc": r["detect_auroc"],
                     "threshold_fpr2pct": float(thr), "tpr_at_fpr2pct": tpr})
        print("  sigma_m=%.3f  AUROC=%.3f  TPR@FPR2%%=%.3f"
              % (sm, r["detect_auroc"], tpr))
    results["detector_precision"] = prec

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
