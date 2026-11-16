"""Synthetic mechanism check for OCRB (research line round 10, cycle-2 round 2).

NOT benchmark evidence.  Three isolated mechanism checks, no learned components:

  A. ROBUST BARRIER (lemma 87).  Start a point mass on a random inbound
     trajectory toward one circular obstacle, add a bounded per-step disturbance
     |w| <= wbar, and compare:
       - "stale-cert": follow the nominal action (the v9 chunk certificate was
         computed without this disturbance; no safety filter),
       - "rob": project the next state onto the disturbance-shifted barrier.
     Metric: physical collision rate (true clearance < 0) over 20 steps.

  B. DETECTION LAG (lemma 89).  An obstacle is revealed d_warn metres ahead
     while the robot travels at v0.  The *object* channel updates after 20
     frames in v9 and 1 frame in v10; both then brake at a_max.
     Metric: collision rate as a function of the effective warning distance.

  C. OPEN-SET MISS (BOB fallback).  The obstacle is never classified as an
     object.  Compare object-only (no BOB), occupancy fallback BOB, and a
     transparent object invisible to both channels.
     Metric: collision rate.

The true dynamics / true obstacle set are identical in every condition; only the
information channel and the safety filter differ.
"""
import json
import math
import random

DT = 0.02
A_MAX = 4.0
D_SAFE = 0.15
ALPHA = 0.5
WBAR = 0.05
RHO = 0.20
N = 20000


def norm(x, y):
    return math.hypot(x, y)


def run_barrier(rng, use_filter, inflate):
    r = rng.uniform(0.30, 0.60)
    d0 = rng.uniform(0.85, 2.20)
    theta = rng.uniform(-0.6, 0.6)
    v0 = rng.uniform(0.4, 2.0)
    # start on a circle around the obstacle, velocity roughly inbound
    px, py = d0 * math.cos(theta), d0 * math.sin(theta)
    vx, vy = -v0 * math.cos(theta), -v0 * math.sin(theta)
    for _ in range(20):
        # bounded per-step disturbance (model error / state estimate)
        wx = rng.uniform(-WBAR, WBAR)
        wy = rng.uniform(-WBAR, WBAR)
        nvx, nvy = vx + wx, vy + wy
        px_n, py_n = px + nvx * DT, py + nvy * DT
        if use_filter:
            R = r + D_SAFE + WBAR / ALPHA + inflate
            d = norm(px_n, py_n)
            if d < R:
                if d < 1e-9:
                    px_n, py_n, d = R, 0.0, R
                px_n, py_n = px_n / d * R, py_n / d * R
            nvx, nvy = (px_n - px) / DT, (py_n - py) / DT
        px, py, vx, vy = px_n, py_n, nvx, nvy
        if norm(px, py) < r:                 # physical collision
            return True
    return False


def braking_collision(d_warn, v0, r):
    if d_warn <= 0:
        return True
    stop = v0 * v0 / (2.0 * A_MAX)
    return d_warn < r + stop


def run_lag(rng, delay_frames, missed=False, bob=False, glass=False):
    r = rng.uniform(0.30, 0.60)
    v0 = rng.uniform(0.5, 2.0)
    d_warn = rng.uniform(0.40, 3.00)
    if glass:
        return True                         # invisible to object *and* depth
    if missed and not bob:
        return True                         # open-set miss, no fallback
    if bob:
        delay_frames = 1                    # occupancy sees it in one frame
    d_eff = d_warn - v0 * delay_frames * DT
    return braking_collision(d_eff, v0, r)


def rate(fn, *args, seed=11):
    rng = random.Random(seed)
    return sum(fn(rng, *args) for _ in range(N)) / N


def main():
    out = {
        "A_barrier": [
            {"speed_band": "0.4-2.0", "stale_cert": rate(run_barrier, False, 0.0),
             "rob_no_inflate": rate(run_barrier, True, 0.0),
             "rob_rho_novel": rate(run_barrier, True, RHO)},
        ],
        "B_detection_lag": [
            {"channel": "v9 object 20f", "collision": rate(run_lag, 20)},
            {"channel": "v10 object 1f", "collision": rate(run_lag, 1)},
        ],
        "C_open_set": [
            {"channel": "missed, no BOB", "collision": rate(run_lag, 20, True, False, False)},
            {"channel": "missed, BOB occupancy 1f", "collision": rate(run_lag, 20, True, True, False)},
            {"channel": "glass (no channel)", "collision": rate(run_lag, 20, True, False, True)},
        ],
    }
    print(json.dumps(out, indent=2))
    with open("/home/runner/work/xuen/xuen/workspace/exp/ocrb_results.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
