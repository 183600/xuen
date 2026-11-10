"""Round 41 / v18 audit: how much of released G1_Dex1 demonstrations is
"corrective interaction churn" rather than primary task motion?

The challenge scores success + steps.  If a large fraction of demonstrated
frames are dwell / direction reversal / re-grasp churn, then a policy that
*proactively* resolves the underlying uncertainty before committing may buy
back steps.  This script only measures released demonstration statistics; it
is not a benchmark result.

Inputs : exp/unibot_states/*.npz  (fetched by exp/fetch_states.py)
Outputs: exp/v41/active_interaction_audit_results.json

Run:
    PYTHONPATH=.pylibs python3 exp/v41/active_interaction_audit.py
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "active_interaction_audit_results.json")
FPS = 30.0
DWELL_SPEED = 0.010          # m/s: below this the end-effector is "not working"
DWELL_MIN_FRAMES = 5         # 0.17 s
REV_WIN = 5                  # frames used to estimate direction
REV_SPEED = 0.030            # m/s: ignore reversals in noise
REV_COS = -0.5               # >120 deg direction change
GRIPPER_OPEN = 2.0           # hysteresis: >2.0 = open
GRIPPER_CLOSE = 1.0          # <1.0 = closed
MIN_RUN = 30                 # frames


def contiguous_runs(ep, fr):
    """Indices of maximal runs with consecutive frame_index inside one episode."""
    idx = np.where((ep[1:] == ep[:-1]) & (fr[1:] == fr[:-1] + 1))[0]
    if len(idx) == 0:
        return []
    # split at breaks
    breaks = np.where(np.diff(idx) != 1)[0]
    starts = np.r_[0, breaks + 1]
    ends = np.r_[breaks, len(idx) - 1]
    runs = []
    for s, e in zip(starts, ends):
        ids = idx[s:e + 1]
        if len(ids) + 1 >= MIN_RUN:
            runs.append(np.r_[ids[0], ids + 1])
    return runs


def side_metrics(pos, grip):
    """pos: (n,3) end-effector position; grip: (n,) gripper scalar."""
    n = len(pos)
    dt = 1.0 / FPS
    d = np.diff(pos, axis=0)
    speed = np.linalg.norm(d, axis=1) / dt                    # (n-1,)
    speed_full = np.r_[speed, speed[-1]]

    # dwell: runs of low speed longer than DWELL_MIN_FRAMES
    low = speed_full < DWELL_SPEED
    dwell_frames = 0
    dwell_events = 0
    i = 0
    while i < n:
        if not low[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and low[j + 1]:
            j += 1
        if j - i + 1 >= DWELL_MIN_FRAMES:
            dwell_frames += j - i + 1
            dwell_events += 1
        i = j + 1

    # reversals: direction change between t and t+REV_WIN
    rev_frames = np.zeros(n, dtype=bool)
    rev_events = 0
    if n > 2 * REV_WIN:
        k = REV_WIN
        v1 = pos[k:-k] - pos[:-2 * k]
        v2 = pos[2 * k:] - pos[k:-k]
        s1 = np.linalg.norm(v1, axis=1) / (k * dt)
        s2 = np.linalg.norm(v2, axis=1) / (k * dt)
        denom = np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1) + 1e-12
        cosang = (v1 * v2).sum(1) / denom
        hit = (cosang < REV_COS) & (s1 > REV_SPEED) & (s2 > REV_SPEED)
        for t in np.where(hit)[0]:
            c = t + k
            rev_frames[max(0, c - k):min(n, c + k + 1)] = True
        rev_events = int(hit.sum())

    # gripper open/close cycles with hysteresis (state machine, not raw jumps)
    state = np.where(grip > GRIPPER_OPEN, 1, np.where(grip < GRIPPER_CLOSE, 0, -1))
    cur = None
    grip_events = 0
    grip_frames = np.zeros(n, dtype=bool)
    for t, s in enumerate(state):
        if s == -1:
            continue
        if cur is not None and s != cur:
            grip_events += 1
            grip_frames[max(0, t - 2):min(n, t + 3)] = True
        cur = s

    churn_core = low | rev_frames
    churn = churn_core | grip_frames
    path = float(speed.sum() * dt)
    net = float(np.linalg.norm(pos[-1] - pos[0]))
    excess = max(0.0, path - net)
    return {
        "n": int(n),
        "duration_s": float(n / FPS),
        "mean_speed": float(speed_full.mean()),
        "dwell_frac": float(dwell_frames / n),
        "dwell_events_per_10s": float(dwell_events / (n / FPS) * 10),
        "reversal_events_per_10s": float(rev_events / (n / FPS) * 10),
        "gripper_events_per_10s": float(grip_events / (n / FPS) * 10),
        "churn_core_frac": float(churn_core.mean()),
        "churn_frac": float(churn.mean()),
        "path_m": path,
        "net_m": net,
        "excess_path_ratio": float(excess / (net + 1e-6)),
    }


def audit(path):
    data = np.load(path, allow_pickle=True)
    rows = []
    for part in ("random", "contig"):
        d = data[part].item()
        ep = np.asarray(d["episode_index"]).astype(int)
        fr = np.asarray(d["frame_index"]).astype(int)
        for ids in contiguous_runs(ep, fr):
            rec = {"episode": int(ep[ids[0]]), "frames": int(len(ids))}
            for side in ("left", "right"):
                pos = np.asarray(d[f"observation.state.{side}_ee_pose_gripper_base"])[ids, :3]
                grip = np.asarray(d[f"observation.state.{side}_gripper"])[ids]
                rec[side] = side_metrics(pos, grip)
            rows.append(rec)
    task = os.path.basename(path).replace(".npz", "")
    if not rows:
        return {"task": task, "ok": False, "runs": 0}
    weighted = {}
    total_n = sum(r["frames"] for r in rows)
    for side in ("left", "right"):
        weighted[side] = {
            k: float(sum(r[side][k] * r["frames"] for r in rows) / total_n)
            for k in ("dwell_frac", "churn_core_frac", "churn_frac", "excess_path_ratio",
                      "dwell_events_per_10s", "reversal_events_per_10s",
                      "gripper_events_per_10s", "mean_speed")
        }
    return {
        "task": task, "ok": True, "runs": len(rows),
        "frames": int(total_n),
        "mean_duration_s": float(np.mean([r["frames"] for r in rows]) / FPS),
        "weighted": weighted,
        "runs_detail": rows,
    }


def main():
    results = []
    for f in sorted(glob.glob(os.path.join(ROOT, "exp", "unibot_states", "*.npz"))):
        r = audit(f)
        results.append(r)
        if r["ok"]:
            w = r["weighted"]
            print(f'{r["task"]:32s} runs={r["runs"]:2d} frames={r["frames"]:5d} '
                  f'core L/R={w["left"]["churn_core_frac"]:.3f}/{w["right"]["churn_core_frac"]:.3f} '
                  f'dwell L/R={w["left"]["dwell_frac"]:.3f}/{w["right"]["dwell_frac"]:.3f} '
                  f'rev/10s L={w["left"]["reversal_events_per_10s"]:.1f} '
                  f'excess L/R={w["left"]["excess_path_ratio"]:.2f}/{w["right"]["excess_path_ratio"]:.2f}')
        else:
            print(r["task"], "no contiguous run")
    ok = [r for r in results if r["ok"]]
    if ok:
        tn = sum(r["frames"] for r in ok)
        overall = {}
        for side in ("left", "right"):
            overall[side] = {
                k: float(sum(r["weighted"][side][k] * r["frames"] for r in ok) / tn)
                for k in ok[0]["weighted"][side]
            }
        summary = {
            "tasks": len(ok), "frames": int(tn),
            "overall_weighted": overall,
            # pooled run-level distribution (unweighted) for honesty
            "run_pool": {},
        }
        for side in ("left", "right"):
            summary["run_pool"][side] = {
                k: {
                    "p10": float(np.percentile([r["runs_detail"][i][side][k]
                                                for r in ok for i in range(len(r["runs_detail"]))], 10)),
                    "p50": float(np.percentile([r["runs_detail"][i][side][k]
                                                for r in ok for i in range(len(r["runs_detail"]))], 50)),
                    "p90": float(np.percentile([r["runs_detail"][i][side][k]
                                                for r in ok for i in range(len(r["runs_detail"]))], 90)),
                }
                for k in ("churn_core_frac", "churn_frac", "dwell_frac", "excess_path_ratio")
            }
    else:
        summary = {"tasks": 0}
    out = {"summary": summary, "per_task": results}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("\noverall:", json.dumps(summary.get("overall_weighted", {}), indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
