"""Synthetic mechanism check for PROSO-GEAR (round 16).

NOT benchmark evidence. It isolates three questions:

  A. When part of the action-observation residual is *predictable* (harmonic
     reducer play/hysteresis + action prosody), does subtracting a lightweight
     observer improve OOD detection? How much model error can it tolerate?
  B. Does an innovation-based trust gate convert that AUROC gain into
     success-rate / cost gains, and what does misspecification do?
  C. Does unit-selection fallback beat first-match grammar when the target
     pose is uncertain but observable?

Generative model (declared, not fit):
  - raw residual r = p + nu (+ shift on OOD), with p the predictable part,
    nu the innovation, shift the OOD signature.
  - observer returns p_hat = p + eps_model; innovation = r - p_hat.
  - OOD-G ("silent") has shift = 0, so it is indistinguishable from ID in
    residual space (the round-15 boundary, preserved here on purpose).
"""

import json
import math
import os

import numpy as np
from scipy.stats import mannwhitneyu

RNG = np.random.default_rng(20261102)
N = 40000


def auroc(pos, neg):
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    u = mannwhitneyu(pos, neg, alternative="greater").statistic
    return float(u / (len(pos) * len(neg)))


def sample_residual(rng, n, sigma_p, sigma_nu, sigma_m, shift):
    p = rng.normal(0.0, sigma_p, size=(n, 3))
    nu = rng.normal(0.0, sigma_nu, size=(n, 3))
    r = p + nu + np.asarray(shift)
    p_hat = p + rng.normal(0.0, sigma_m, size=(n, 3))
    return r, r - p_hat


# ----------------------------------------------------------------------
# Experiment A: AUROC vs predictable fraction and model error ratio
# ----------------------------------------------------------------------
def experiment_a():
    sigma_nu = 0.15
    shift = np.array([0.20, 0.20, 0.00])
    rows = []
    for rho in (0.0, 0.2, 0.4, 0.6, 0.8):
        sigma_p = 0.0 if rho == 0 else sigma_nu * math.sqrt(rho / (1.0 - rho))
        for mu in (0.0, 0.25, 0.5, 1.0, 1.5):
            sigma_m = mu * sigma_p
            r_id, inn_id = sample_residual(RNG, N, sigma_p, sigma_nu, sigma_m, [0, 0, 0])
            r_ood, inn_ood = sample_residual(RNG, N, sigma_p, sigma_nu, sigma_m, shift)
            rows.append({
                "rho": rho,
                "mu": mu,
                "auroc_raw": round(auroc(r_ood.mean(axis=1), r_id.mean(axis=1)), 4),
                "auroc_innovation": round(auroc(inn_ood.mean(axis=1), inn_id.mean(axis=1)), 4),
            })
    return rows


# ----------------------------------------------------------------------
# Experiment B: gate pipeline (success / cost)
# ----------------------------------------------------------------------
TYPE_PARAMS = {
    "id":          dict(p=1.00, c=0.80, g=0.50, shift=(0.00, 0.00, 0.00)),
    "ood_exec":    dict(p=0.00, c=0.30, g=0.60, shift=(0.20, 0.20, 0.00)),
    "ood_sem":     dict(p=0.00, c=0.30, g=0.60, shift=(0.00, 0.00, 0.20)),
    "ood_silent":  dict(p=0.00, c=0.30, g=0.30, shift=(0.00, 0.00, 0.00)),
}


def sample_type(rng, pi=0.35, rho=0.3, mapok=0.5):
    if rng.random() >= pi:
        return "id"
    if rng.random() >= rho:
        return "ood_exec"
    return "ood_sem" if rng.random() < mapok else "ood_silent"


def run_episode(t, policy, rng, sigma_p, sigma_nu, sigma_m, q_z,
                B=10.0, need=3.0, fb_cost=1.2, alpha=0.12, k=0.05, h=2.5):
    par = TYPE_PARAMS[t]
    progress = 0.0
    spent = 0.0
    cusum = 0.0
    mode = "trust"
    dwell = 0
    ever_fb = False
    scores = []

    while spent < B - 1e-9 and progress < need:
        if policy == "vla":
            act = "servo"
        elif mode == "trust":
            if cusum > h:
                mode = "fallback"
                dwell = 0
                act = "fallback"
            else:
                act = "servo"
        elif mode == "fallback":
            dwell += 1
            if dwell >= 3:
                mode = "probe"
                act = "servo"
            else:
                act = "fallback"
        else:
            act = "servo"

        if act == "fallback":
            ever_fb = True
            ok = rng.random() < par["g"] * 0.8
            spent += fb_cost
        else:
            ok = rng.random() < par["c"] * 0.9
            spent += 1.0

            p = rng.normal(0.0, sigma_p, 3)
            nu = rng.normal(0.0, sigma_nu, 3)
            eps = rng.normal(0.0, sigma_m, 3)
            r = p + nu + np.asarray(par["shift"])
            if policy == "vla":
                score = 0.0
            elif policy == "raw":
                score = float(r.mean())
            else:
                score = float((r - (p + eps)).mean())
            if policy != "vla":
                z = score / max(1e-6, q_z[0])
                surprise = 1 if z > q_z[1] else 0
                scores.append(score)
                cusum = max(0.0, cusum + surprise - alpha - k)
                if mode == "probe":
                    if not surprise:
                        mode = "trust"
                        cusum = 0.0
                    else:
                        mode = "fallback"
                        dwell = 0

        if ok:
            progress += 1.0

    return progress >= need, spent, ever_fb, scores


def calibrate_q(policy, sigma_p, sigma_nu, sigma_m, n=200000):
    rng = np.random.default_rng(7)
    p = rng.normal(0.0, sigma_p, size=(n, 3))
    nu = rng.normal(0.0, sigma_nu, size=(n, 3))
    if policy == "raw":
        vals = (p + nu).mean(axis=1)
    else:
        vals = (nu - rng.normal(0.0, sigma_m, size=(n, 3))).mean(axis=1)
    scale = 1.4826 * np.median(np.abs(vals - np.median(vals))) + 1e-9
    q = float(np.quantile(vals / scale, 0.90))
    return float(scale), q


def evaluate_b(policy, n=12000, pi=0.35, rho=0.3, mapok=0.5,
               sigma_p=0.184, sigma_nu=0.15, sigma_m=0.0, seed=11):
    rng = np.random.default_rng(seed)
    q_z = calibrate_q(policy, sigma_p, sigma_nu, sigma_m)
    succ, cost, fb_id, fb_ood = [], [], [], []
    s_id, s_ood = [], []
    for _ in range(n):
        t = sample_type(rng, pi, rho, mapok)
        s, sp, ef, sc = run_episode(t, policy, rng, sigma_p, sigma_nu,
                                    sigma_m, q_z)
        succ.append(1.0 if s else 0.0)
        cost.append(sp)
        if t == "id":
            fb_id.append(1.0 if ef else 0.0)
            s_id.extend(sc)
        else:
            fb_ood.append(1.0 if ef else 0.0)
            s_ood.extend(sc)
    return dict(succ=round(float(np.mean(succ)), 4),
                cost=round(float(np.mean(cost)), 3),
                spc=round(float(np.mean(succ) / np.mean(cost)), 4),
                fb_id=round(float(np.mean(fb_id)), 4),
                fb_ood=round(float(np.mean(fb_ood)), 4),
                auroc=round(auroc(np.asarray(s_ood), np.asarray(s_id)), 4),
                q_scale=round(q_z[0], 5), q=round(q_z[1], 3))


# ----------------------------------------------------------------------
# Experiment C: unit selection vs first-match grammar
# ----------------------------------------------------------------------
def experiment_c():
    offsets = np.array([-0.02, -0.01, 0.0, 0.01, 0.02])
    rows = []
    for s_true in (0.0, 0.005, 0.010, 0.020):
        for s_obs in (0.001, 0.005, 0.015):
            rng = np.random.default_rng(23)
            n = 30000
            t = rng.normal(0.0, s_true, n) if s_true > 0 else np.zeros(n)
            obs = t + rng.normal(0.0, s_obs, n)
            g_true = 0.85 * np.exp(-((np.abs(offsets[None, :] - t[:, None])) / 0.008) ** 2)
            succ_grammar = rng.random(n) < g_true[:, 2]
            pick = np.argmin(np.abs(offsets[None, :] - obs[:, None]), axis=1)
            succ_select = rng.random(n) < g_true[np.arange(n), pick]
            lam = s_true ** 2 / (s_true ** 2 + s_obs ** 2 + 1e-12)
            t_eff = lam * obs
            pick_s = np.argmin(np.abs(offsets[None, :] - t_eff[:, None]), axis=1)
            succ_shrunk = rng.random(n) < g_true[np.arange(n), pick_s]
            rows.append({
                "target_std": s_true,
                "obs_std": s_obs,
                "grammar": round(float(succ_grammar.mean()), 4),
                "unit_selection": round(float(succ_select.mean()), 4),
                "shrunk_selection": round(float(succ_shrunk.mean()), 4),
                "delta_pp": round(100.0 * float(succ_select.mean() - succ_grammar.mean()), 2),
                "shrunk_delta_pp": round(100.0 * float(succ_shrunk.mean() - succ_grammar.mean()), 2),
            })
    return rows


# ----------------------------------------------------------------------
# Experiment D: adaptive chunking trade-off (analytic allocation)
# ----------------------------------------------------------------------
def experiment_d():
    steps = 30
    risks = {"free": 0.2, "near": 1.0}
    frac_near = 0.4
    out = []
    for h_free, h_near in ((5, 5), (6, 3), (6, 2), (5, 2), (4, 2)):
        n_free = int(round(steps * (1 - frac_near)))
        n_near = steps - n_free
        blocks = math.ceil(n_free / h_free) + math.ceil(n_near / h_near)
        risk_latency = (risks["free"] * n_free * h_free / 2.0
                        + risks["near"] * n_near * h_near / 2.0) / steps
        out.append(dict(h_free=h_free, h_near=h_near,
                        blocks=blocks,
                        risk_weighted_half_block=round(risk_latency, 3)))
    return out


if __name__ == "__main__":
    print("A. AUROC vs predictable fraction rho and model-error ratio mu")
    a = experiment_a()
    for r in a:
        if r["mu"] in (0.0, 0.5, 1.0):
            print(f"  rho={r['rho']:.1f} mu={r['mu']:.1f} "
                  f"raw={r['auroc_raw']:.3f} inn={r['auroc_innovation']:.3f}")

    print("\nB. gate pipeline sweep over predictable fraction rho (sigma_nu=0.15)")
    b = []
    for rho in (0.0, 0.2, 0.4, 0.6):
        sp = 0.0 if rho == 0 else 0.15 * math.sqrt(rho / (1.0 - rho))
        for name, pol, mu in (("vla", "vla", 0.0), ("raw", "raw", 0.0),
                              ("innovation", "innovation", 0.0),
                              ("innovation_miss_0.5", "innovation", 0.5),
                              ("innovation_miss_1.0", "innovation", 1.0)):
            r = evaluate_b(pol, sigma_p=sp, sigma_m=mu * sp)
            r.update(policy=name, rho=rho, mu=mu)
            b.append(r)
            print(f"  rho={rho:.1f} {name:20s} succ={r['succ']:.3f} "
                  f"cost={r['cost']:.2f} spc={r['spc']:.3f} "
                  f"fb_id={r['fb_id']:.3f} fb_ood={r['fb_ood']:.3f} "
                  f"auroc={r['auroc']:.3f}")

    print("\nC. unit selection vs grammar")
    c = experiment_c()
    for r in c:
        print(f"  target_std={r['target_std']:.3f} obs_std={r['obs_std']:.3f} "
              f"grammar={r['grammar']:.3f} select={r['unit_selection']:.3f} "
              f"delta={r['delta_pp']:+.2f}pp")

    print("\nD. adaptive chunking allocation")
    d = experiment_d()
    for r in d:
        print(f"  h_free={r['h_free']} h_near={r['h_near']} "
              f"blocks={r['blocks']} risk_latency={r['risk_weighted_half_block']}")

    out = dict(a=a, b=b, c=c, d=d)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "proso_gear_results.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote", path)
