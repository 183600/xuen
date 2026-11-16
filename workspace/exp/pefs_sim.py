"""Synthetic mechanism check for PEFS (research line round 11).

NOT benchmark evidence. Pure standard library, fixed seeds, no learned modules.
Three isolated checks:

  A. NEGATIVE vs POSITIVE EVIDENCE under a transparent obstacle.
     v10 (negative evidence) avoids an obstacle iff any detector fires.
     v11 (positive evidence) certifies free space only when *all* independent
     modalities agree that it is free; any detection / disagreement -> unknown.
     A single-modality positive rule is included as a control: it is *worse*
     than negative evidence, which is exactly why concordance is required.

  B. OCCLUSION SHADOW. A target is hidden behind an occluder; it is first
     visible only d_reveal metres before contact. v10 treats unobserved space
     as free and brakes after reveal; v11 never certifies unobserved space and
     brakes at the shadow frontier. Metric: collision rate.

  C. FEW-SHOT CONFORMAL RISK CONTROL. Voxel occupancy scores. Calibrate a
     free-space threshold on n support occupied samples with CRC to target a
     false-free risk delta. Compare a fixed threshold (v10 style), split-CRC
     (v11 few-shot), and adaptive ACI under a material shift. Also report the
     free-acceptance rate, exposing the information-theoretic limit: when a
     transparent object looks exactly like free space, no threshold can fix it.

Run:  python exp/pefs_sim.py
Writes exp/pefs_results.json and prints a compact summary.
"""
import json
import math
import os
import random

N = 40000
SEED = 20261116


# ----------------------------------------------------------------------------
# A. transparent obstacle: negative vs positive evidence
# ----------------------------------------------------------------------------
# detection probability of a transparent object, per independent cue.
P_V10 = {"depth": 0.45, "appearance": 0.35}          # v10 channels (OR rule)
P_V11 = {"depth": 0.45, "stereo": 0.55, "parallax": 0.50}  # v11 modalities (AND-free rule)


def check_transparent():
    rng = random.Random(SEED)
    n = N
    v10_coll = 0          # negative evidence: collision iff every v10 cue misses
    single_coll = 0       # positive evidence, depth only: collision iff depth misses
    v11_coll = 0          # positive evidence + concordance: collision iff all miss
    v11_unknown = 0       # any cue fires -> unknown -> certified path abstains
    for _ in range(n):
        d10 = [rng.random() < p for p in P_V10.values()]
        d11 = [rng.random() < p for p in P_V11.values()]
        if not any(d10):
            v10_coll += 1
        if not d11[0]:
            single_coll += 1
        if any(d11):
            v11_unknown += 1
        if not any(d11):
            v11_coll += 1
    return {
        "n": n,
        "v10_negative_evidence_collision": v10_coll / n,
        "v11_positive_single_modality_collision": single_coll / n,
        "v11_positive_concordance_collision": v11_coll / n,
        "v11_abstain_to_unknown": v11_unknown / n,
    }


# ----------------------------------------------------------------------------
# B. occlusion shadow
# ----------------------------------------------------------------------------
def check_occlusion():
    rng = random.Random(SEED + 1)
    n = N
    # time from first sight to contact (s), speed 1 m/s, brake decel 1 m/s^2
    v = 1.0
    a_brake = 1.0
    d_brake = v * v / (2.0 * a_brake)  # 0.5 m
    v10_coll = 0
    for _ in range(n):
        d_reveal = rng.uniform(0.10, 1.10)   # metres of warning after reveal
        if d_reveal < d_brake:
            v10_coll += 1
    return {
        "n": n,
        "d_brake_m": d_brake,
        "reveal_range_m": [0.10, 1.10],
        "v10_negative_evidence_collision": v10_coll / n,
        "v11_positive_evidence_collision": 0.0,
        "v11_extra_stops_at_shadow_frontier": 1.0,
    }


# ----------------------------------------------------------------------------
# C. few-shot conformal risk control
# ----------------------------------------------------------------------------
def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _sample_occupied(rng, mu, sigma=1.0):
    return rng.gauss(mu, sigma)


def _crc_threshold(scores, delta):
    """Conformal risk control for loss 1[s < lambda] on occupied samples.

    Returns None when delta < 1/(n+1): with a finite support set the
    distribution-free guarantee cannot certify risks below that floor, so the
    certifier must abstain (never certify free space). This is the few-shot
    sample-size floor, reported explicitly rather than hidden.
    """
    n = len(scores)
    if 1.0 / (n + 1.0) > delta:
        return None
    best = None
    for lam in [-1e9] + sorted(set(scores)):
        risk = sum(1 for s in scores if s < lam) / n
        if n / (n + 1.0) * risk + 1.0 / (n + 1.0) <= delta:
            best = lam
    return best


def check_conformal():
    rng = random.Random(SEED + 2)
    delta = 0.05
    mu_free = -2.0
    mu_occ_src = 1.0
    mu_occ_shift = -1.0
    sigma = 1.0
    lam_fixed = 0.0

    n_q = 200000
    q_occ_src = [_sample_occupied(rng, mu_occ_src, sigma) for _ in range(n_q)]
    q_occ_shift = [_sample_occupied(rng, mu_occ_shift, sigma) for _ in range(n_q)]
    q_free = [rng.gauss(mu_free, sigma) for _ in range(n_q)]

    def fpr(scores, lam):
        if lam is None:
            return 0.0          # abstain: nothing is certified free
        return sum(1 for s in scores if s < lam) / len(scores)

    def far(scores, lam):
        if lam is None:
            return 0.0          # abstain: no free space is accepted
        return sum(1 for s in scores if s < lam) / len(scores)

    curves = []
    lam20 = None
    for n_cal in (10, 20, 40, 100):
        cal = [_sample_occupied(rng, mu_occ_src, sigma) for _ in range(n_cal)]
        lam = _crc_threshold(cal, delta)
        if n_cal == 20:
            lam20 = lam
        curves.append({
            "n_cal": n_cal,
            "feasible": lam is not None,
            "lambda_crc": lam,
            "source_false_free": fpr(q_occ_src, lam),
            "source_free_accept": far(q_free, lam),
            "shift_false_free": fpr(q_occ_shift, lam),
            "shift_free_accept": far(q_free, lam),
        })

    # adaptive conformal inference on a shifted occupied stream (delayed label)
    T = 50000
    gamma = 0.01
    lam = lam20 if lam20 is not None else -1.0
    losses = 0
    lam_trace = []
    for t in range(T):
        s = _sample_occupied(rng, mu_occ_shift, sigma)
        loss = 1 if s < lam else 0
        losses += loss
        lam = lam + gamma * (delta - loss)
        lam = max(-8.0, min(4.0, lam))
        if t >= T // 2:
            lam_trace.append(lam)
    lam_bar = sum(lam_trace) / max(1, len(lam_trace))

    return {
        "delta": delta,
        "lambda_fixed": lam_fixed,
        "fixed_baseline": {
            "source_false_free": fpr(q_occ_src, lam_fixed),
            "source_free_accept": far(q_free, lam_fixed),
            "shift_false_free": fpr(q_occ_shift, lam_fixed),
            "shift_free_accept": far(q_free, lam_fixed),
        },
        "few_shot_curve": curves,
        "shifted_adaptive": {
            "aci_long_run_false_free": losses / T,
            "aci_mean_lambda_second_half": lam_bar,
            "aci_free_accept": far(q_free, lam_bar),
        },
        "theoretical": {
            "phi_0_src_occ": _phi((lam_fixed - mu_occ_src) / sigma),
            "phi_0_shift_occ": _phi((lam_fixed - mu_occ_shift) / sigma),
        },
    }


def main():
    res = {
        "transparent_obstacle": check_transparent(),
        "occlusion_shadow": check_occlusion(),
        "few_shot_conformal": check_conformal(),
    }
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "pefs_results.json"), "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
