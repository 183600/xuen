#!/usr/bin/env python3
"""EFPS toy simulation (v3, round 3).

This is a *synthetic* sanity check, not a robot result.  It isolates one
question: when a human reverses an already-completed step between two
open-loop action chunks, how do

  B0  current-step-only geometric verification (v2 UIP-01')
  B1  periodic full re-check of all completed steps
  V3  event-gated signed-change + CUSUM monitor (this round)

trade detection latency, false alarms, step score and verification cost?

Run:
  PYTHONPATH=.../.pylibs python exp/efps_toy_sim.py \
      --episodes 1000 --out exp/efps_toy_results.json
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass

import numpy as np

RATE = 0.8          # nominal progress rate (1/s)
RDIST = 1.0         # reverse (human undo) rate (1/s)
S = 3
W = np.array([0.30, 0.30, 0.40])
DT = 1.0 / 30.0
T = 600             # 20 s


@dataclass
class EpisodeResult:
    success: float
    step_score: float
    det_rate: float
    det_latency: float
    false_alarms: float
    expensive_calls: float
    cheap_calls: float
    n_regressions: float


def run_episode(rng: np.random.Generator, mode: str, k: int,
                disturb_prob: float = 0.5,
                sigma_obs: float = 0.005,
                event_theta: float = 0.02,
                cusum_h: float = 0.15,
                b1_done_thr: float = 0.85,
                advance_thr: float = 0.95) -> EpisodeResult:
    p = np.zeros(S)
    done = np.zeros(S, dtype=bool)
    scheduled = np.zeros(S, dtype=bool)
    g = 0
    disturbances: list[list] = []   # [s, start, end, target, applied]
    last_alarm = np.full(S, -1e9)
    redo = np.zeros(S, dtype=bool)
    prev_obs = None
    cusum = np.zeros(S)
    alarms: list[tuple[int, float]] = []
    expensive_calls = 0.0
    cheap_calls = 0.0
    completed_at = np.full(S, -1.0)

    def complete_step(s: int, t: float) -> None:
        p[s] = 1.0
        done[s] = True
        completed_at[s] = t
        if not scheduled[s]:
            scheduled[s] = True
            if rng.random() < disturb_prob:
                start = t + rng.uniform(0.2, 1.5)
                dur = rng.uniform(0.2, 0.8)
                tgt = rng.uniform(0.0, 0.6)
                disturbances.append([s, start, start + dur, tgt, False])

    def maybe_advance(obs: np.ndarray, t: float) -> None:
        nonlocal g
        if g < S and not redo[g] and obs[g] >= advance_thr:
            complete_step(g, t)
            g += 1

    for step in range(T + 1):
        t = step * DT

        # --- policy executes the current subgoal open-loop -----------------
        if g < S:
            p[g] = min(1.0, p[g] + RATE * DT)
            if p[g] >= 1.0 and not done[g]:
                complete_step(g, t)

        # --- human undo ----------------------------------------------------
        for d in disturbances:
            s, st, en, tgt, _ = d
            if st <= t < en and p[s] > tgt:
                p[s] = max(tgt, p[s] - RDIST * DT)
                d[4] = True

        # --- redo (recovery) ----------------------------------------------
        for s in range(S):
            if redo[s] and p[s] < 1.0:
                p[s] = min(1.0, p[s] + RATE * DT)
                if p[s] >= 1.0:
                    redo[s] = False

        # --- observation only at chunk boundaries --------------------------
        if step % k == 0:
            obs = np.clip(p + rng.normal(0.0, sigma_obs, size=S), 0.0, 1.0)
            cheap_calls += 1.0

            if mode == "B0":
                # v2: only the current subgoal is checked, no re-check of
                # already-completed steps -> deliberate blindness to undo.
                expensive_calls += 1.0
                maybe_advance(obs, t)

            elif mode == "B1":
                # periodic full geometric re-check of every step
                expensive_calls += S
                for s in range(S):
                    if s < g and done[s] and obs[s] < b1_done_thr:
                        if t - last_alarm[s] > 1.0:
                            alarms.append((s, t))
                            last_alarm[s] = t
                            g = s
                            done[s] = False
                            redo[s] = True
                maybe_advance(obs, t)

            elif mode == "V3":
                # cheap signed frame-difference gate on completed steps
                if prev_obs is None:
                    prev_obs = obs
                    continue
                d = obs - prev_obs
                energy = float(np.sum(np.abs(d[:g])))
                if energy > event_theta:
                    expensive_calls += S
                    for s in range(S):
                        if s < g and done[s]:
                            cusum[s] = max(0.0, cusum[s] - d[s])
                            if cusum[s] > cusum_h and t - last_alarm[s] > 1.0:
                                alarms.append((s, t))
                                last_alarm[s] = t
                                g = s
                                done[s] = False
                                redo[s] = True
                                cusum[s] = 0.0
                maybe_advance(obs, t)
                prev_obs = obs

            else:
                raise ValueError(mode)

    # --- truth: disturbances that caused a real regression ----------------
    regressions = []
    for s, st, en, tgt, applied in disturbances:
        start_p = 1.0
        # regression magnitude: did it push progress below 0.8 after completion?
        if applied and tgt < 0.8:
            regressions.append(s)
    n_reg = len(regressions)

    det = 0
    lat = []
    for s in regressions:
        # first alarm for s after its disturbance start (within 3 s)
        cand = [ta for (sa, ta) in alarms if sa == s and ta >= 0.0]
        # map to the specific disturbance: use earliest alarm after any start
        starts = [d[1] for d in disturbances if d[0] == s]
        if cand and starts:
            ta = min(cand)
            st = min(starts)
            if ta - st <= 3.0 and ta >= st:
                det += 1
                lat.append(ta - st)

    # false alarms: alarms for a step with no real regression, or far away
    false_alarms = 0
    for sa, ta in alarms:
        ok = False
        for s, st, en, tgt, applied in disturbances:
            if s == sa and applied and tgt < 0.8 and st - 1.0 <= ta <= en + 3.0:
                ok = True
                break
        if not ok:
            false_alarms += 1

    final_done = p >= 0.99
    score = float(np.dot(W, final_done.astype(float)))
    return EpisodeResult(
        success=float(np.all(final_done)),
        step_score=score,
        det_rate=(det / n_reg) if n_reg else float("nan"),
        det_latency=(float(np.mean(lat)) if lat else float("nan")),
        false_alarms=float(false_alarms),
        expensive_calls=expensive_calls,
        cheap_calls=cheap_calls,
        n_regressions=float(n_reg),
    )


def aggregate(mode: str, k: int, episodes: int, base_seed: int):
    """Paired design: all modes see the same episode seeds (same human undo
    schedule and same observation noise)."""
    rows = [run_episode(np.random.default_rng(base_seed + e), mode, k)
            for e in range(episodes)]
    out = {}
    for field in rows[0].__dataclass_fields__:
        vals = np.array([getattr(r, field) for r in rows], dtype=float)
        if field in ("det_rate", "det_latency"):
            out[field + "_mean"] = float(np.nanmean(vals))
            out[field + "_std"] = float(np.nanstd(vals))
        else:
            out[field + "_mean"] = float(vals.mean())
            out[field + "_std"] = float(vals.std())
    return out


def few_shot_toy(rng: np.random.Generator, episodes: int = 3000) -> dict:
    """Prototypical accuracy vs K on held-out (unseen) classes, and
    conformal false-alarm calibration vs calibration-set size."""
    dim = 24
    n_classes = 12
    centers = rng.normal(size=(n_classes, dim))
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)

    def sample(cls, n):
        x = centers[cls][None, :] + rng.normal(scale=0.35, size=(n, dim))
        return x / np.linalg.norm(x, axis=1, keepdims=True)

    acc = {}
    for kshot in (1, 3, 5, 10):
        correct = 0
        for _ in range(episodes):
            sup = np.stack([sample(c, kshot) for c in range(n_classes)])
            protos = sup.mean(axis=1)
            protos /= np.linalg.norm(protos, axis=1, keepdims=True)
            c = int(rng.integers(n_classes))
            q = sample(c, 1)[0]
            pred = int(np.argmax(protos @ q))
            correct += int(pred == c)
        acc[f"K={kshot}"] = correct / episodes

    # conformal: calibrate a threshold on normal (no-regression) scores
    alpha = 0.05
    conformal = {}
    for ncal in (10, 20, 50, 100, 200):
        fprs = []
        for _ in range(400):
            cal = rng.normal(0.0, 1.0, size=ncal)
            thr = np.quantile(cal, 1.0 - alpha)
            test = rng.normal(0.0, 1.0, size=2000)
            fprs.append(float(np.mean(test > thr)))
        fprs = np.array(fprs)
        conformal[f"ncal={ncal}"] = {
            "mean_fpr": float(fprs.mean()),
            "p05_fpr": float(np.quantile(fprs, 0.05)),
            "p95_fpr": float(np.quantile(fprs, 0.95)),
        }
    return {"prototype_accuracy": acc, "conformal_alpha_0.05": conformal}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=1000)
    ap.add_argument("--out", default="exp/efps_toy_results.json")
    args = ap.parse_args()

    results = {"config": {"episodes": args.episodes, "S": S, "T": T,
                          "DT": DT, "W": W.tolist(),
                          "note": "synthetic sanity check, not robot data"}}
    for k in (4, 8, 16):
        for mode in ("B0", "B1", "V3"):
            results[f"{mode}_k{k}"] = aggregate(
                mode, k, args.episodes, base_seed=20261113 + 1000 * k)

    rng = np.random.default_rng(20261113)
    results["few_shot"] = few_shot_toy(rng)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
