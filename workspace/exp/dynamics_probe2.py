"""Second dynamics/joint-space probe for UniBot.

Adds:
  * closed-loop tracking-error decay time constant (error -> 0 after a step)
  * chunk interpolation error split by slow (contact-ish) vs fast frames
  * 6-D joint->EE Jacobian conditioning and redundancy (null-space) usage
  * action-hold / pause fraction

Data: exp/duo_rows_cache/*.json. Output: exp/dynamics_probe2_results.json.
"""
import glob
import json
import os
import re
from collections import defaultdict

import numpy as np
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
                if len(cur) >= 12:
                    segs.append(cur)
                cur = []
            cur.append(r)
        if len(cur) >= 12:
            segs.append(cur)
    return segs


def arr(rows, key, dim=None):
    a = np.array([r[key] for r in rows], float)
    return a[:, :dim] if dim is not None else a


def chunk_err_mask(a, mask, L):
    n = len(a)
    if n < L + 2 or mask.sum() < 3:
        return float("nan")
    idx = np.arange(0, n, L)
    if idx[-1] != n - 1:
        idx = np.append(idx, n - 1)
    rec = np.empty_like(a)
    for j in range(a.shape[1]):
        rec[:, j] = np.interp(np.arange(n), idx, a[idx, j])
    denom = np.std(a, axis=0) + 1e-8
    err = np.sqrt(np.mean(((a - rec) / denom) ** 2, axis=1))
    return float(np.mean(err[mask]))


def analyze(task):
    segs = load_segments(task)
    tau, decay_a = [], []
    slow_err = {L: [] for L in (2, 4, 8, 16)}
    fast_err = {L: [] for L in (2, 4, 8, 16)}
    jac6_cond, jac6_mnp, null_frac = [], [], []
    hold_frac = []
    for rows in segs:
        n = len(rows)
        for side in ("left", "right"):
            A = arr(rows, f"action.{side}_arm")
            S = arr(rows, f"observation.state.{side}_arm")
            # tracking error relative to the command that produced it (lag 3)
            lag = 3
            if n > lag + 5:
                e = S[lag:] - A[:n - lag]
                x0, x1 = e[:-1], e[1:]
                for j in range(7):
                    X = np.column_stack([x0[:, j], np.ones(len(x0))])
                    coef, *_ = np.linalg.lstsq(X, x1[:, j], rcond=None)
                    a = coef[0]
                    decay_a.append(a)
                    if 0 < a < 1:
                        tau.append(-1.0 / (FPS * np.log(a)))
            # slow vs fast chunk error, using observed EE speed
            Epos = arr(rows, f"observation.state.{side}_ee_pose_gripper_base", 3)
            vEE = np.linalg.norm(np.diff(Epos, axis=0), axis=1) * FPS
            # align to action frames (n-1 velocities); pad last
            vv = np.append(vEE, vEE[-1] if len(vEE) else 0.0)
            if len(vv) == len(A):
                lo = np.percentile(vv, 30)
                mask_slow = vv <= lo
                mask_fast = vv >= np.percentile(vv, 70)
                for L in slow_err:
                    slow_err[L].append(chunk_err_mask(A, mask_slow, L))
                    fast_err[L].append(chunk_err_mask(A, mask_fast, L))
            # 6-D Jacobian: xyz + axis-angle difference (small-angle approx)
            E6 = arr(rows, f"observation.state.{side}_ee_pose_gripper_base", 6)
            d6 = np.diff(E6, axis=0) * FPS
            vJ = np.diff(S, axis=0) * FPS
            valid = np.linalg.norm(vJ, axis=1) > 0.02
            if valid.sum() >= 30:
                J, *_ = np.linalg.lstsq(vJ[valid], d6[valid], rcond=None)  # 7x6
                sv = np.linalg.svd(J.T, compute_uv=False)
                jac6_cond.append(float(sv[0] / (sv[-1] + 1e-9)))
                jac6_mnp.append(float(np.prod(sv)))  # sqrt(det(JJ^T))
                # redundancy: fraction of joint velocity energy in null(J)
                u, s, vt = np.linalg.svd(J.T)
                nvec = vt[-1]
                vv2 = vJ[valid]
                num = (vv2 @ nvec) ** 2
                den = np.sum(vv2 ** 2, axis=1) + 1e-12
                null_frac.append(float(np.median(num / den)))
            # hold fraction: action step smaller than 0.5% of joint range
            dA = np.linalg.norm(np.diff(A, axis=0), axis=1)
            hold_frac.append(float(np.mean(dA < 1e-3)))
    lb = LB_BY[NAME2LB[task]]
    return {
        "task": task, "lb_task": NAME2LB[task], "lb_mean": lb["mean"],
        "tau_err_med_s": float(np.nanmedian(tau)) if tau else float("nan"),
        "err_decay_a_med": float(np.nanmedian(decay_a)) if decay_a else float("nan"),
        "chunk_slow": {str(L): float(np.nanmedian(slow_err[L])) for L in slow_err},
        "chunk_fast": {str(L): float(np.nanmedian(fast_err[L])) for L in fast_err},
        "jac6_cond_med": float(np.nanmedian(jac6_cond)) if jac6_cond else float("nan"),
        "jac6_mnp_med": float(np.nanmedian(jac6_mnp)) if jac6_mnp else float("nan"),
        "null_frac_med": float(np.nanmedian(null_frac)) if null_frac else float("nan"),
        "hold_frac_med": float(np.nanmedian(hold_frac)) if hold_frac else float("nan"),
    }


def main():
    tasks = sorted({task_of(f) for f in glob.glob(f"{CACHE}/*.json")})
    out = {"tasks": {}}
    for task in tasks:
        out["tasks"][task] = analyze(task)
        r = out["tasks"][task]
        print(f"{task:22s} tau={r['tau_err_med_s']:.3f}s slow8={r['chunk_slow']['8']:.3f} "
              f"fast8={r['chunk_fast']['8']:.3f} cond6={r['jac6_cond_med']:.1f} "
              f"null={r['null_frac_med']:.3f} hold={r['hold_frac_med']:.3f}")
    hard = [out["tasks"][t] for t in HARD if t in out["tasks"]]
    easy = [out["tasks"][t] for t in EASY if t in out["tasks"]]
    for name, group in (("hard", hard), ("easy", easy)):
        if not group:
            continue
        out.setdefault("groups", {})[name] = {
            "n": len(group),
            "tau_err_med_s": float(np.nanmedian([g["tau_err_med_s"] for g in group])),
            "chunk_slow": {L: float(np.nanmedian([g["chunk_slow"][L] for g in group]))
                           for L in ("2", "4", "8", "16")},
            "chunk_fast": {L: float(np.nanmedian([g["chunk_fast"][L] for g in group]))
                           for L in ("2", "4", "8", "16")},
            "jac6_cond_med": float(np.nanmedian([g["jac6_cond_med"] for g in group])),
            "null_frac_med": float(np.nanmedian([g["null_frac_med"] for g in group])),
            "hold_frac_med": float(np.nanmedian([g["hold_frac_med"] for g in group])),
        }
    xs = list(out["tasks"].values())
    for key in ("tau_err_med_s", "jac6_cond_med", "jac6_mnp_med", "null_frac_med",
                "hold_frac_med", "chunk_slow"):
        if key == "chunk_slow":
            for L in ("2", "4", "8", "16"):
                rho, p = spearmanr([g[key][L] for g in xs], [g["lb_mean"] for g in xs])
                out.setdefault("corr_vs_lb_mean", {})[f"chunk_slow_{L}"] = {"rho": float(rho), "p": float(p)}
        else:
            rho, p = spearmanr([g[key] for g in xs], [g["lb_mean"] for g in xs])
            out.setdefault("corr_vs_lb_mean", {})[key] = {"rho": float(rho), "p": float(p)}
    json.dump(out, open("exp/dynamics_probe2_results.json", "w"), indent=2)
    print("\nGROUPS", json.dumps(out.get("groups", {}), indent=2))
    print("\nCORR", json.dumps(out.get("corr_vs_lb_mean", {}), indent=2))


if __name__ == "__main__":
    main()
