"""Round-v3 mechanism check for UniBot UIP-16..20.

Inspiration words: 「关节驱动」 (joint-space actuation) and 「实时推理」.

Q1 TIMING.  The harness executes a whole action chunk open-loop, then calls
   get_action again.  Synchronously, every chunk of k actions pays the full
   inference latency L, so effective per-step cost is dt + L/k.  A no-stall
   contract needs L <= (1-margin)*k*dt.  Reactivity (small k) and real-time
   (large k) are therefore in direct tension.  Speculative PREFETCH predicts
   the next proprioceptive state with a kinematic model while the current
   chunk runs; if the prediction gate passes, chunk cost is max(k*dt, L).

Q2 DETECTION.  Human disturbances are reversals ("zip up then pull apart").
   We watch the progress potential of the most recently completed scoring
   step and ask: how fast a reversal is caught, at what false-alarm rate,
   and how detection delay trades against the wall-clock cost of inference
   paid every k control steps.

THIS IS A MECHANISM CHECK ON SYNTHETIC SIGNALS, NOT A BENCHMARK RESULT.
All parameters are declared below; none is measured on the real robot.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
OUT = EXP / "rt_joint_sim_results.json"

# ----------------------------- declared model -----------------------------
DT = 1.0 / 30.0          # control period [s] (WORKING ASSUMPTION; manual pending)
LAT_MED = 0.045          # median inference latency [s]
LAT_SIG = 0.45           # lognormal sigma
KAPPA = 12.0             # kinematic-prediction horizon constant (chunks)
P_CONTACT = 0.10         # prob a chunk contains a contact event that breaks prediction

N_EP = 600
RNG_SEED = 20261113

# detection / episode model
N_STEPS = 5              # T16/T17-like ordered scoring steps
STEP_COST = 50           # control steps to complete one scoring step nominally
T_MAX = 11.0             # wall-clock episode budget [s]
P_REV = 0.60             # prob a completed step is later reversed
REV_DELAY = (2, 18)      # steps after completion before reversal starts
REV_LEN = (8, 26)        # reversal duration in control steps
REV_RATE = 1.0 / 48.0    # progress removed per control step during reversal
ADV_RATE = 1.0 / STEP_COST
SIGMA_OBS = 0.020        # observation noise on the progress potential
W_STEP = 20              # score weight per step (5 steps => 100)
DELTA_LEVEL = 0.08       # level detector: alarm if progress < 1 - delta
CUSUM_NU = 0.006
CUSUM_H = 0.10
RAW_THR = 0.050


def lognormal_latency(rng, n):
    return rng.lognormal(mean=np.log(LAT_MED), sigma=LAT_SIG, size=n)


def p_pred(k):
    """Prob. the kinematic prediction over a k-step horizon passes the gate."""
    return (1.0 - P_CONTACT) * np.exp(-(k - 1) / KAPPA)


def chunk_extra(k, L, gate):
    """Extra wall time beyond the k execution steps.
    Sync: pay L.  Prefetch: pay only the part of L that overruns execution
    when the prediction gate passes; otherwise pay L in full."""
    te = k * DT
    gate = np.asarray(gate)
    return np.where(gate, np.maximum(0.0, L - te), L)


def timing_sweep(rng):
    rows = []
    n = 200000
    for k in range(1, 17):
        te = k * DT
        L = lognormal_latency(rng, n)
        g = rng.random(n) < p_pred(k)

        extra_sync = np.full(n, 0.0) + L
        extra_pf = chunk_extra(k, L, g)

        rows.append({
            "k": k,
            "T_e_ms": round(te * 1e3, 1),
            "duty_sync": round(float(np.mean(te / (te + extra_sync))), 4),
            "stall_sync_ms": round(float(np.mean(L) * 1e3), 1),
            "p95_cycle_sync_ms": round(float(np.percentile(te + extra_sync, 95) * 1e3), 1),
            "p_pred": round(float(p_pred(k)), 3),
            "prefetch_hit": round(float(np.mean(g & (L <= te))), 4),
            "duty_prefetch": round(float(np.mean(te / (te + extra_pf))), 4),
            "stall_prefetch_ms": round(float(np.mean(extra_pf) * 1e3), 1),
            "step_cost_sync_ms": round(float(np.mean(DT + extra_sync / k) * 1e3), 2),
            "step_cost_prefetch_ms": round(float(np.mean(DT + extra_pf / k) * 1e3), 2),
        })

    L = lognormal_latency(rng, 400000)
    contract = {
        "L_p50_ms": round(float(np.median(L) * 1e3), 1),
        "L_p95_ms": round(float(np.percentile(L, 95) * 1e3), 1),
        "k_min_margin30_p50": int(np.ceil(np.median(L) / (0.7 * DT))),
        "k_min_margin30_p95": int(np.ceil(np.percentile(L, 95) / (0.7 * DT))),
    }
    return rows, contract


def run_episode(detector, k, mode, rng):
    """Return (score/100, detection_delays_steps, false_alarms, wall_s)."""
    prog = np.zeros(N_STEPS)
    completed = []
    sched = []                        # [start, end, step_idx, handled]
    cur = 0
    redo = None
    resume = 0
    det_state = 0.0
    last_y = None
    last_target = None
    delays = []
    false_alarms = 0

    t = 0
    wall = 0.0
    while wall < T_MAX and t < 100000:
        # ---- inference cost at each chunk boundary ----
        wall += DT
        if t % k == 0:
            L = float(lognormal_latency(rng, 1)[0])
            gate = rng.random() < p_pred(k)
            wall += float(chunk_extra(k, np.array([L]), np.array([gate]))[0])

        # ---- actuation ----
        if redo is not None:
            prog[redo] = min(1.0, prog[redo] + ADV_RATE)
            if prog[redo] >= 1.0 - 1e-9:
                redo = None
                cur = resume
        elif cur < N_STEPS:
            prog[cur] = min(1.0, prog[cur] + ADV_RATE)
            if prog[cur] >= 1.0 - 1e-9 and cur not in completed:
                completed.append(cur)
                if rng.random() < P_REV:
                    dl = int(rng.integers(REV_DELAY[0], REV_DELAY[1] + 1))
                    ln = int(rng.integers(REV_LEN[0], REV_LEN[1] + 1))
                    sched.append([t + dl, t + dl + ln, cur, False])
                cur += 1

        # ---- human reversal ----
        for ev in sched:
            s, e, j, handled = ev
            if s <= t < e and not handled:
                prog[j] = max(0.0, prog[j] - REV_RATE)

        # ---- observe every k control steps ----
        if completed and redo is None and t % k == 0:
            target = completed[-1]
            y = prog[target] + rng.normal(0.0, SIGMA_OBS)
            if last_target == target and last_y is not None:
                dy = (y - last_y) / k
                if detector == "level":
                    alarm = y < 1.0 - DELTA_LEVEL
                elif detector == "raw":
                    alarm = dy < -RAW_THR
                elif detector == "cusum":
                    det_state = max(0.0, det_state - dy - CUSUM_NU)
                    alarm = det_state > CUSUM_H
                else:
                    alarm = False

                if alarm:
                    ev = next((e for e in sched
                               if e[2] == target and not e[3] and t >= e[0] - k),
                              None)
                    if ev is not None:
                        ev[3] = True
                        delays.append(t - ev[0])
                        redo = target
                        resume = cur
                    else:
                        false_alarms += 1
                    det_state = 0.0
            last_y = y
            last_target = target

        t += 1

    score = W_STEP * sum(1 for j in range(N_STEPS) if prog[j] >= 0.99)
    return score, delays, false_alarms, wall


def detection_sweep(rng):
    out = []
    for mode in ["sync", "prefetch"]:
        for det in ["none", "level", "raw", "cusum"]:
            for k in [1, 2, 4, 8, 12]:
                scores, delays, fas = [], [], []
                for _ in range(N_EP):
                    sc, dl, fa, _ = run_episode(det, k, mode, rng)
                    scores.append(sc)
                    delays.extend(dl)
                    fas.append(fa)
                d = np.array(delays) if delays else np.array([np.nan])
                out.append({
                    "mode": mode,
                    "detector": det,
                    "k": k,
                    "score_mean": round(float(np.mean(scores)), 2),
                    "score_p25": round(float(np.percentile(scores, 25)), 1),
                    "detections": len(delays),
                    "delay_steps_med": round(float(np.nanmedian(d)), 1),
                    "delay_steps_p90": round(float(np.nanpercentile(d, 90)), 1),
                    "false_alarm_per_ep": round(float(np.mean(fas)), 3),
                })
    return out


def main():
    rng = np.random.default_rng(RNG_SEED)
    timing, contract = timing_sweep(rng)
    detection = detection_sweep(np.random.default_rng(RNG_SEED + 1))

    def wall_ms(d_steps, k, lat_ms):
        d = np.asarray(d_steps, dtype=float)
        return d * DT * 1e3 + np.ceil(d / k) * lat_ms

    coupling = []
    for k, d in [(1, 3), (2, 4), (4, 5), (8, 7), (12, 9)]:
        for lat in [20.0, 45.0, 95.0]:
            coupling.append({
                "k": k, "L_ms": lat, "delay_steps": d,
                "wall_detect_ms": round(float(wall_ms(d, k, lat)), 1),
            })

    result = {
        "_disclaimer": "Synthetic mechanism check; parameters are declared "
                       "assumptions, not measurements.",
        "model": {
            "dt": DT, "lat_median_ms": LAT_MED * 1e3, "lat_sigma": LAT_SIG,
            "kappa": KAPPA, "p_contact": P_CONTACT,
            "n_steps": N_STEPS, "step_cost": STEP_COST, "t_max": T_MAX,
            "p_rev": P_REV, "sigma_obs": SIGMA_OBS, "n_ep": N_EP,
            "delta_level": DELTA_LEVEL, "cusum_nu": CUSUM_NU,
            "cusum_h": CUSUM_H, "raw_thr": RAW_THR,
        },
        "timing_contract": contract,
        "timing": timing,
        "detection": detection,
        "coupling": coupling,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
