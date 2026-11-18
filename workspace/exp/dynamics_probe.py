"""UniBot round 1 (dynamics x joint-space-control line): offline probe.

Data: exp/duo_rows_cache/*.json (HF datasets-server rows; 15 of 32 tasks,
91 episodes, ~42.8k frames, 30 Hz; state/action only, no images).

Questions:
  1) How does the hidden low-level controller lag the commanded joint
     position?  (action->state response, per joint and per task)
  2) How rough is the teleoperated joint trajectory (velocity/accel/jerk,
     high-frequency fraction), and are contact-rich tasks rougher?
  3) How much joint-space detail is lost if a trajectory is represented by
     a chunk of length L (linear interpolation between waypoints)?
  4) Is the empirical joint->end-effector Jacobian ill-conditioned in the
     tasks that the teaser leaderboard says are hardest?

Outputs exp/dynamics_probe_results.json.  No network access.
"""
import glob
import json
import os
import re
from collections import defaultdict

import numpy as np
from scipy.signal import welch
from scipy.stats import spearmanr

CACHE = "exp/duo_rows_cache"
LB = json.load(open("exp/r16_leaderboard_stats.json"))["per_task"]
NAME2LB = {
    "ArrangePlates": "Clear Plates", "ArrangeTestTubes": "Arrange Test Tubes",
    "ColorArrangement": "Color Arrangement", "ConveyorSorting": "Conveyor Food Sorting",
    "DisconnectEthernet": "Disconnect Ethernet", "FoldTowel": "Fold Towel",
    "FruitCollection": "Fruit Basket Collection", "HangCup": "Hang the Cup",
    "OrganizeBookshelf": "Organize Bookshelf", "PlugCharger": "Plug Charger",
    "PlugInEthernet": "Plug In Ethernet", "PourOutMedicine": "Open Pill Bottle",
    "SyringeWaterTransfer": "Syringe Water Transfer", "Unlock": "Unlock", "ZipUp": "Zip Up",
}
LB_BY = {t["task"]: t for t in LB}
HARD = {"PlugInEthernet", "DisconnectEthernet", "PlugCharger", "Unlock",
        "SyringeWaterTransfer", "PourOutMedicine", "ZipUp", "ArrangeTestTubes"}
EASY = {"ArrangePlates", "FruitCollection", "FoldTowel", "HangCup"}
FPS = 30.0


def task_of(f):
    return re.match(r"(.+)_(\d+)\.json$", os.path.basename(f)).group(1)


def load_segments(task):
    by = defaultdict(list)
    for f in sorted(glob.glob(f"{CACHE}/{task}_*.json")):
        for it in json.load(open(f)).get("rows", []):
            by[it["row"]["episode_index"]].append(it["row"])
    segs = []
    for ep, rows in sorted(by.items()):
        rows.sort(key=lambda r: r["frame_index"])
        cur = []
        for r in rows:
            if cur and r["frame_index"] != cur[-1]["frame_index"] + 1:
                if len(cur) >= 8:
                    segs.append(cur)
                cur = []
            cur.append(r)
        if len(cur) >= 8:
            segs.append(cur)
    return segs


def arr(rows, key, dim=None):
    a = np.array([r[key] for r in rows], float)
    if dim is not None:
        a = a[:, :dim]
    return a


def hf_fraction(v, fps=FPS, cutoff=2.0):
    """Fraction of velocity power above cutoff Hz (mean over joints)."""
    if len(v) < 16:
        return float("nan")
    fr, p = welch(v, fs=fps, axis=0, nperseg=min(64, len(v)))
    tot = p.sum(axis=0)
    hi = p[fr >= cutoff].sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = hi / tot
    return float(np.nanmean(r))


def chunk_error(a, L):
    """Normalized RMS error of linear interpolation through every L-th sample."""
    n = len(a)
    if n < L + 2:
        return float("nan")
    idx = np.arange(0, n, L)
    if idx[-1] != n - 1:
        idx = np.append(idx, n - 1)
    rec = np.empty_like(a)
    for j in range(a.shape[1]):
        rec[:, j] = np.interp(np.arange(n), idx, a[idx, j])
    denom = np.std(a, axis=0) + 1e-8
    return float(np.mean(np.sqrt(np.mean(((a - rec) / denom) ** 2, axis=0))))


def analyze_task(task):
    segs = load_segments(task)
    E, CMD, PERP = [], [], []
    lags = {k: [] for k in range(6)}
    lag_by_joint = {k: [] for k in range(6)}
    tau, r2 = [], []
    vel, acc, jerk, hf = [], [], [], []
    ch = {L: [] for L in (1, 2, 4, 8, 16)}
    jac_cond, jac_sv = [], []
    for rows in segs:
        n = len(rows)
        t = np.arange(n) / FPS
        for side in ("left", "right"):
            S = arr(rows, f"observation.state.{side}_arm")
            A = arr(rows, f"action.{side}_arm")
            # action -> state lag: median joint-space error for command at t
            for k in range(6):
                if n - k >= 8:
                    d = np.linalg.norm(S[k:] - A[:n - k], axis=1)
                    lags[k].append(float(np.median(d)))
                    lag_by_joint[k].append(np.median(np.abs(S[k:] - A[:n - k]), axis=0))
            # second-order ARX: S[t+1] = a*S[t] + b*A[t] + c, per joint
            x0, x1, x2 = S[:-2], S[1:-1], S[2:]
            aa, bb, rr = [], [], []
            for j in range(7):
                X = np.column_stack([x1[:, j], x0[:, j], np.ones(len(x0))])
                coef, *_ = np.linalg.lstsq(X, x2[:, j], rcond=None)
                pred = X @ coef
                ss = np.sum((x2[:, j] - x2[:, j].mean()) ** 2) + 1e-12
                rr.append(1.0 - np.sum((x2[:, j] - pred) ** 2) / ss)
                aa.append(coef[0]); bb.append(coef[1])
            aa = np.array(aa)
            with np.errstate(invalid="ignore", divide="ignore"):
                tt = -1.0 / (FPS * np.log(np.clip(aa, 1e-4, 1 - 1e-4)))
            tau.extend(np.where((aa > 0) & (aa < 1), tt, np.nan).tolist())
            r2.append(float(np.nanmean(rr)))
            # roughness of the commanded joint trajectory
            v = np.diff(A, axis=0) * FPS
            ac = np.diff(v, axis=0) * FPS
            jk = np.diff(ac, axis=0) * FPS
            vel.append(float(np.median(np.linalg.norm(v, axis=1))))
            acc.append(float(np.median(np.linalg.norm(ac, axis=1))))
            jerk.append(float(np.median(np.linalg.norm(jk, axis=1))))
            hf.append(hf_fraction(v))
            for L in ch:
                ch[L].append(chunk_error(A, L))
            # empirical joint -> EE linear velocity Jacobian
            Epos = arr(rows, f"observation.state.{side}_ee_pose_gripper_base", 3)
            vEE = np.diff(Epos, axis=0) * FPS
            vJ = np.diff(S, axis=0) * FPS
            valid = np.linalg.norm(vJ, axis=1) > 0.02
            if valid.sum() >= 20:
                J, *_ = np.linalg.lstsq(vJ[valid], vEE[valid], rcond=None)  # 7x3
                sv = np.linalg.svd(J.T, compute_uv=False)
                jac_sv.append(float(np.median(sv)))
                jac_cond.append(float(sv[0] / (sv[-1] + 1e-9)))
    lb = LB_BY[NAME2LB[task]]
    return {
        "task": task, "lb_task": NAME2LB[task],
        "lb_mean": lb["mean"], "difficulty": lb["difficulty"],
        "n_episodes": len(segs), "n_frames": int(sum(len(s) for s in segs)),
        "lag_err_med": [float(np.median(lags[k])) for k in range(6)],
        "lag_best": int(np.argmin([np.median(lags[k]) for k in range(6)])),
        "lag_joint_med": np.nanmedian(np.array(lag_by_joint[0]), axis=0).tolist() if lag_by_joint[0] else [],
        "arx_r2": float(np.nanmean(r2)),
        "tau_med_s": float(np.nanmedian(tau)),
        "vel_med": float(np.median(vel)), "acc_med": float(np.median(acc)),
        "jerk_med": float(np.median(jerk)), "hf_frac": float(np.nanmedian(hf)),
        "chunk_err": {str(L): float(np.nanmedian(ch[L])) for L in ch},
        "jac_cond_med": float(np.nanmedian(jac_cond)) if jac_cond else float("nan"),
        "jac_sv_med": float(np.nanmedian(jac_sv)) if jac_sv else float("nan"),
    }


def main():
    tasks = sorted({task_of(f) for f in glob.glob(f"{CACHE}/*.json")})
    out = {"tasks": {}, "meta": {"n_tasks": len(tasks)}}
    for task in tasks:
        out["tasks"][task] = analyze_task(task)
        r = out["tasks"][task]
        print(f"{task:22s} eps={r['n_episodes']:2d} frames={r['n_frames']:5d} "
              f"lag={r['lag_best']} jerk={r['jerk_med']:.2f} hf={r['hf_frac']:.3f} "
              f"L8err={r['chunk_err']['8']:.3f} cond={r['jac_cond_med']:.1f}")

    hard = [out["tasks"][t] for t in HARD if t in out["tasks"]]
    easy = [out["tasks"][t] for t in EASY if t in out["tasks"]]
    agg = {}
    for name, group in (("hard", hard), ("easy", easy)):
        if not group:
            continue
        agg[name] = {
            "n": len(group),
            "jerk_med": float(np.nanmedian([g["jerk_med"] for g in group])),
            "hf_frac": float(np.nanmedian([g["hf_frac"] for g in group])),
            "chunk_err": {L: float(np.nanmedian([g["chunk_err"][L] for g in group]))
                          for L in ("1", "2", "4", "8", "16")},
            "lag_best": float(np.nanmedian([g["lag_best"] for g in group])),
            "jac_cond_med": float(np.nanmedian([g["jac_cond_med"] for g in group])),
        }
    out["groups"] = agg

    xs = list(out["tasks"].values())
    for key in ("jerk_med", "hf_frac", "jac_cond_med", "tau_med_s"):
        rho, p = spearmanr([g[key] for g in xs], [g["lb_mean"] for g in xs])
        out.setdefault("corr_vs_lb_mean", {})[key] = {"rho": float(rho), "p": float(p)}
    for L in ("2", "4", "8", "16"):
        rho, p = spearmanr([g["chunk_err"][L] for g in xs], [g["lb_mean"] for g in xs])
        out.setdefault("corr_vs_lb_mean", {})[f"chunk_err_{L}"] = {"rho": float(rho), "p": float(p)}

    json.dump(out, open("exp/dynamics_probe_results.json", "w"), indent=2)
    print("\nGROUPS", json.dumps(agg, indent=2))
    print("\nCORR", json.dumps(out["corr_vs_lb_mean"], indent=2))


if __name__ == "__main__":
    main()
