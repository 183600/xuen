#!/usr/bin/env python3
"""Round-55 toy simulation: Empathic Real-Time control (EMRT).

Compares four policies on a partially-observable affective loop:
  open   : open-loop max expression, no timing awareness
  blind  : calibrated content, but no deadline fallback (late delivery)
  ernrt  : calibrated content + anytime degradation + risk gating (proposed)
  quiet  : attentive silence / minimal acknowledgement

Metrics: distress reduction, perceived empathic quality Q, overclaim rate,
late-delivery rate, social-safety violations, CVaR_0.9 of final distress.
Pure stdlib; no numpy.
"""
import json
import math
import random
import statistics

D_EMP = 0.8          # seconds, affective deadline
TAU_HARM = 1.8       # beyond this, late empathy is worse than none
SIG_OBS = 0.25       # observation noise on true distress
N_EP = 4000
T = 24
SEED = 55


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def sample_full_latency(rng):
    lat = 0.15 + rng.expovariate(1 / 0.18) + rng.uniform(0, 0.15)
    if rng.random() < 0.12:
        lat += rng.uniform(0.5, 1.3)
    return lat


def kernel(lat):
    if lat > TAU_HARM:
        return -0.35
    return math.exp(-(lat / D_EMP) ** 2)


def run_episode(policy, rng):
    # true latent distress
    if rng.random() < 0.30:
        d = rng.uniform(0.65, 0.92)
    else:
        d = rng.uniform(0.28, 0.60)
    d0 = d

    # Gaussian belief over distress: N(mu, var)
    mu, var = 0.5, 0.30 ** 2
    q_sum = 0.0
    q_den = 0.0
    overclaim_steps = 0
    late_steps = 0
    violations = 0

    for _ in range(T):
        # --- perception ---
        z = clip(d + rng.gauss(0, SIG_OBS), 0.0, 1.0)
        r_obs = SIG_OBS ** 2
        post_var = 1.0 / (1.0 / var + 1.0 / r_obs)
        post_mu = post_var * (mu / var + z / r_obs)
        mu, var = post_mu, post_var + 0.010 ** 2
        sd = math.sqrt(var)
        s_max = clip(1.0 - 1.6 * sd, 0.10, 1.0)

        # --- reference / congruent expression ---
        w_ref = clip(0.25 + 0.90 * mu, 0.0, 1.0)
        s_ref = clip(s_max * (0.50 + 0.70 * mu), 0.0, 1.0)

        # --- policy chooses warmth / specificity / latency ---
        if policy == "open":
            w, s = 1.0, 1.0
            lat = sample_full_latency(rng)
        elif policy == "blind":
            w, s = w_ref, min(s_ref, s_max)
            lat = sample_full_latency(rng)
        elif policy == "ernrt":
            w, s = w_ref, min(s_ref, s_max)
            lat_full = sample_full_latency(rng)
            if lat_full > D_EMP:
                # anytime degradation: timely, low-bandwidth but sincere
                w, s = 0.25, 0.05
                lat = 0.12 + rng.uniform(0, 0.10)
            else:
                lat = lat_full
        elif policy == "quiet":
            w, s = 0.22, 0.05
            lat = 0.12 + rng.uniform(0, 0.10)
        else:
            raise ValueError(policy)

        k = kernel(lat)
        if lat > D_EMP:
            late_steps += 1

        # --- perceived empathic quality ---
        err = abs(w - w_ref) + 0.5 * abs(s - s_ref)
        q = max(0.0, 1.0 - err / 1.5)
        q_sum += k * q
        q_den += 1.0

        # --- overclaim of understanding ---
        overclaim = max(0.0, s - s_max)
        wrong = abs(mu - d) > 0.25
        if overclaim > 1e-9:
            overclaim_steps += 1

        # --- social safety: over-intense when calm, or false certainty ---
        if (w > 0.90 and d < 0.30) or (s > 0.80 and sd > 0.25):
            violations += 1

        # --- affective dynamics (true state) ---
        if lat <= TAU_HARM:
            delta = -0.13 * w * max(k, 0.0)
        else:
            delta = -0.01 * w + 0.10          # late expression adds irritation
        if overclaim > 1e-9 and wrong:
            delta += 0.10 * overclaim
        delta += rng.gauss(0, 0.02)
        d = clip(d + delta, 0.0, 1.0)

    return {
        "reduction": d0 - d,
        "final_distress": d,
        "Q": q_sum / q_den,
        "overclaim": overclaim_steps / T,
        "late": late_steps / T,
        "violations": violations,
    }


def summarize(name, rows):
    red = [r["reduction"] for r in rows]
    fin = sorted(r["final_distress"] for r in rows)
    k = max(1, int(0.10 * len(fin)))
    cvar = statistics.mean(fin[-k:])          # worst 10% final distress
    return {
        "policy": name,
        "distress_reduction": round(statistics.mean(red), 4),
        "empathic_quality_Q": round(statistics.mean(r["Q"] for r in rows), 4),
        "overclaim_rate": round(statistics.mean(r["overclaim"] for r in rows), 4),
        "late_rate": round(statistics.mean(r["late"] for r in rows), 4),
        "social_safety_violations": round(
            statistics.mean(r["violations"] for r in rows), 3),
        "CVaR90_final_distress": round(cvar, 4),
    }


def main():
    rng = random.Random(SEED)
    policies = ["open", "blind", "ernrt", "quiet"]
    rows = {p: [run_episode(p, rng) for _ in range(N_EP)] for p in policies}
    out = {
        "seed": SEED,
        "episodes": N_EP,
        "steps_per_episode": T,
        "params": {"D_emp": D_EMP, "tau_harm": TAU_HARM,
                   "sigma_obs": SIG_OBS},
        "results": [summarize(p, rows[p]) for p in policies],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    path = "/home/runner/work/xuen/xuen/workspace/exp/round55_emrt_results.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("wrote", path)


if __name__ == "__main__":
    main()
