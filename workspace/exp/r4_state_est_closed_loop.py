#!/usr/bin/env python3
"""Round-4 mechanism checks for 状态估计 x 闭环控制.

D-level only: uses real UniBot state/action traces for *calibration* of
prediction/innovation scales, then a synthetic sampled-data phase-tracking
toy for the closed-loop mechanism. Nothing here is robot evidence.

Outputs exp/r4_state_est_closed_loop.json
"""
from __future__ import annotations
import glob, json, os
import numpy as np

EXP = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(EXP, "unibot_states")
OUT = os.path.join(EXP, "r4_state_est_closed_loop.json")
rng = np.random.default_rng(0)

# ---------------------------------------------------------------- real traces
def load_traces():
    traces = []
    for f in sorted(glob.glob(os.path.join(STATE, "*.npz"))):
        d = np.load(f, allow_pickle=True)
        for split in ("contig", "random"):
            if split not in d.files:
                continue
            ep = d[split].item()
            x = np.asarray(ep["observation.state.right_ee_pose_gripper_base"], float)
            a = np.asarray(ep["action.right_ee_pose_gripper_base"], float)
            idx = np.asarray(ep.get("episode_index", np.zeros(len(x))), int)
            for e in np.unique(idx):
                m = idx == e
                if m.sum() >= 120:
                    traces.append((os.path.basename(f)[: -4] + f"@{split}/{e}",
                                   x[m][:400], a[m][:400]))
    return traces


def rmse(p, q):
    return float(np.sqrt(np.mean((p - q) ** 2)))


def real_prediction(traces, horizons=(1, 2, 4, 8, 15, 30), w=5):
    """Open-loop prediction error vs horizon, normalized by state std.

    action_hold : predict x_{t+h} = a_t  (we issued the chunk, ZOH)
    velocity    : predict x_{t+h} = x_t + h * (x_t - x_{t-w}) / w
    """
    rows = {h: {"action_hold": [], "velocity": []} for h in horizons}
    for _, x, a in traces:
        sd = x.std(0) + 1e-6            # per-dim trajectory scale
        xn, an = x / sd, a / sd
        for h in horizons:
            if len(xn) <= h + w + 1:
                continue
            t = np.arange(w, len(xn) - h)
            target = xn[t + h]
            rows[h]["action_hold"].append(rmse(an[t], target))
            rows[h]["velocity"].append(rmse(xn[t] + h * (xn[t] - xn[t - w]) / w,
                                           target))
    return {
        str(h): {
            "action_hold_nrmse": round(float(np.mean(rows[h]["action_hold"])), 4),
            "velocity_nrmse": round(float(np.mean(rows[h]["velocity"])), 4),
        }
        for h in horizons
    }


# --------------------------------------------------- sampled phase-tracking toy
def run_phase_toy(T_a=8, mode="belief", m=4, dwell=25, horizon=300,
                  noise=0.30, rev_interval=70, rev_depth=1, seed=0,
                  z_thr=2.0):
    """Sampled-data phase tracking with external reversals.

    Q_true in [0, m] is true progress (integer phase + completion fraction).
    The policy acts on its belief Q_hat. True progress only advances when the
    believed phase equals the true phase (correct precondition); otherwise the
    robot is executing the wrong subgoal and makes no task progress.
    Observations arrive only at chunk boundaries every T_a control steps.
    """
    r = np.random.default_rng(seed)
    rho = 1.0 / dwell
    Q_true, Q_hat, P = 0.0, 0.0, 0.25
    last_obs = None
    resyncs = false_resyncs = 0
    det_delays, pending = [], None
    next_rev = r.integers(rev_interval // 2, rev_interval + 1)
    for t in range(horizon):
        if t >= next_rev and Q_true >= rev_depth:
            Q_true = max(0.0, Q_true - rev_depth)
            pending = t
            next_rev = t + r.integers(rev_interval // 2, rev_interval + 1)
        # action: advance the believed subgoal; true progress needs sync
        if int(np.floor(Q_hat)) == int(np.floor(Q_true)) and Q_true < m:
            Q_true = min(float(m), Q_true + rho)
        # belief prediction through the held chunk
        if mode in ("belief", "openloop"):
            if Q_hat < m:
                Q_hat = min(float(m), Q_hat + rho)
            P += 0.02
        triggered = False
        if (t + 1) % T_a == 0:
            y = float(np.clip(Q_true + r.normal(0, noise), 0, m))
            if mode == "openloop":
                pass                              # blindly trusts prediction
            elif mode == "memoryless":
                if last_obs is not None and y < last_obs - 0.5:
                    triggered = True
                    if pending is None or (t - pending) > 4 * T_a:
                        false_resyncs += 1
                    else:
                        det_delays.append(t - pending); pending = None
                Q_hat = y
                P = noise ** 2
                resyncs += int(triggered)
                last_obs = y
            else:                                 # belief: innovation-gated EKF
                S = P + noise ** 2
                innov = y - Q_hat
                z = abs(innov) / np.sqrt(S)
                if innov < 0 and z > z_thr:       # externally pushed backwards
                    triggered = True
                    if pending is None or (t - pending) > 4 * T_a:
                        false_resyncs += 1
                    else:
                        det_delays.append(t - pending); pending = None
                    Q_hat = y
                    P = noise ** 2
                    resyncs += 1
                else:
                    K = P / S
                    Q_hat = float(np.clip(Q_hat + K * innov, 0, m))
                    P = (1 - K) * P
                last_obs = y
    return {
        "final_progress": round(Q_true, 3),
        "final_score_frac": round(Q_true / m, 3),
        "resyncs": int(resyncs),
        "false_resyncs": int(false_resyncs),
        "mean_detect_delay": round(float(np.mean(det_delays)), 2) if det_delays else None,
        "detected": len(det_delays),
    }


def aggregate(mode, T_a, reps=120):
    rows = []
    for s in range(reps):
        rows.append(run_phase_toy(T_a=T_a, mode=mode, seed=1000 + s))
    out = {}
    for k in ("final_progress", "final_score_frac", "resyncs", "false_resyncs",
              "mean_detect_delay", "detected"):
        vals = [r[k] for r in rows if r[k] is not None]
        out[k] = round(float(np.mean(vals)), 3) if vals else None
    return out


def main():
    traces = load_traces()
    result = {
        "note": "D-level: real traces calibrate prediction error only; toy is synthetic",
        "n_traces": len(traces),
        "real_prediction_nrmse": real_prediction(traces),
        "phase_toy": {},
    }
    for T_a in (2, 4, 8, 15, 30):
        result["phase_toy"][str(T_a)] = {
            mode: aggregate(mode, T_a) for mode in ("openloop", "memoryless", "belief")
        }
    with open(OUT, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main()
