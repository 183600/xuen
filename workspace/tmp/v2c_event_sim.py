#!/usr/bin/env python3
"""Synthetic sanity check for the v2c round.

NOT robot evidence. It only illustrates three qualitative claims:
  1. a virtual-IMU (vIMU) residual detects body/contact-coupled withdrawals
     faster than a low-rate visual verifier;
  2. the same vIMU is blind to free-object withdrawals (zero coupling);
  3. routing by disturbance class dominates any single sensor.

Run: python3 tmp/v2c_event_sim.py
"""
import json
import math
import random
import statistics

DT = 1.0 / 30.0
N = 400
VISION_K = 8          # visual verifier every 8 control steps (open-loop chunk)
VISION_LATENCY = 2    # steps from image to verifier decision
T_WITHDRAW = (150, 250)
WITHDRAW_LEN = 10
N_EPISODES = 3000


def progress(t):
    if t < 100:
        return t / 100.0
    return 1.0


def sample_withdrawal(seed):
    rng = random.Random(seed)
    t0 = rng.randint(*T_WITHDRAW)
    vals = []
    for t in range(N):
        p = progress(t)
        if t0 <= t < t0 + WITHDRAW_LEN:
            p = max(0.0, 1.0 - (t - t0 + 1) / WITHDRAW_LEN)
        elif t >= t0 + WITHDRAW_LEN:
            p = 0.0  # the reversal persists until an explicit redo
        vals.append(p)
    return t0, vals


def vimu_residual(t, t0, klass, rng):
    """Residual magnitude of the virtual IMU (proprioceptive acceleration)."""
    noise = abs(rng.gauss(0.0, 0.15))
    if klass == "B" and t0 <= t < t0 + 4:
        return abs(1.0 + rng.gauss(0.0, 0.15))
    if klass == "C" and t0 <= t < t0 + 6:
        return abs(0.5 + rng.gauss(0.0, 0.15))
    return noise


def detect_vimu(series, mu0=0.35, drift=0.05, h=0.35):
    s = 0.0
    for i, r in enumerate(series):
        s = max(0.0, s + r - mu0 - drift)
        if s > h:
            return i
    return None


def detect_vision(p_vals, t0, rng):
    """Visual verifier: sees p only at multiples of K, with latency L."""
    done_seen = False
    for sample_t in range(0, N, VISION_K):
        idx = sample_t - VISION_LATENCY
        if idx < 0:
            continue
        # observation available at sample_t was captured VISION_LATENCY steps ago
        p_obs = p_vals[idx] + rng.gauss(0.0, 0.03)
        if p_obs > 0.75:
            done_seen = True
        low = p_obs < 0.6
        if sample_t >= t0 + VISION_LATENCY and done_seen and low:
            return sample_t
    return None


def measure(klass, policy, episodes=N_EPISODES):
    delays, misses, fas = [], 0, 0
    for ep in range(episodes):
        rng = random.Random(10_000 * (ord(klass) + 1) + ep)
        t0, p_vals = sample_withdrawal(ep * 7 + ord(klass))
        if policy == "vision":
            det = detect_vision(p_vals, t0, rng)
        elif policy == "vimu":
            res = [vimu_residual(t, t0, klass, rng) for t in range(N)]
            det = detect_vimu(res)
            # count false alarms in the quiescent prefix
            pre = detect_vimu(res[:t0])
            fas += 0 if pre is None else 1
        elif policy == "routed":
            if klass in ("B", "C"):
                res = [vimu_residual(t, t0, klass, rng) for t in range(N)]
                det = detect_vimu(res)
            else:
                det = detect_vision(p_vals, t0, rng)
        elif policy == "hybrid":
            det = None
            if klass in ("B", "C"):
                res = [vimu_residual(t, t0, klass, rng) for t in range(N)]
                det = detect_vimu(res)
            if det is None:
                det = detect_vision(p_vals, t0, rng)
        else:
            raise ValueError(policy)
        if det is None or det < t0 or det - t0 > 25:
            misses += 1
        else:
            delays.append(det - t0)
    recall = 1.0 - misses / episodes
    med = statistics.median(delays) if delays else None
    p90 = (sorted(delays)[int(0.9 * (len(delays) - 1))] if delays else None)
    return {
        "recall": round(recall, 3),
        "median_delay_steps": med,
        "p90_delay_steps": p90,
        "false_alarms_per_episode": round(fas / episodes, 3) if policy == "vimu" else None,
    }


def main():
    out = {}
    for policy in ("vision", "vimu", "routed", "hybrid"):
        out[policy] = {k: measure(k, policy) for k in ("B", "C", "F")}

    # payload accounting for a 30-frame proprioceptive stack
    per_frame = 7 + 7 + 6 + 6 + 1 + 1 + 15  # arm, arm, ee, ee, gripper, gripper, lower_body
    stack_bytes = per_frame * 4 * 30
    raw_image = 480 * 640 * 3
    out["payload"] = {
        "proprio_floats_per_frame": per_frame,
        "proprio_30frame_bytes": stack_bytes,
        "raw_image_bytes": raw_image,
        "ratio_30frame_vs_one_raw_image": round(stack_bytes / raw_image, 5),
        "ratio_30frame_vs_one_jpeg_100kb": round(stack_bytes / 100_000, 3),
    }
    out["assumptions"] = {
        "dt": DT,
        "vision_chunk_k": VISION_K,
        "vision_latency_steps": VISION_LATENCY,
        "withdraw_after_step": T_WITHDRAW,
        "episodes_per_cell": N_EPISODES,
        "note": "synthetic, illustrative only; not robot evidence",
    }
    path = "tmp/v2c_event_sim.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
