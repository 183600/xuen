"""Round 1 (impedance line) probe 2: within-episode, event-aligned analysis.

Probe 1 showed raw EE tracking error is *not* a cross-task difficulty signal
(Spearman rho ~ -0.17 vs teaser success): it is dominated by task-wide
kinematic/controller offsets.  This probe asks the only question that matters
for deployment: within one episode, does the tracking-error signal change
systematically at gripper-closure / contact events?  If yes, a *self-calibrated*
force proxy is possible even though absolute thresholds are not.
"""
import glob
import json
import os
import re
from collections import defaultdict

import numpy as np

CACHE = "exp/duo_rows_cache"


def task_of(f):
    return re.match(r"(.+)_(\d+)\.json$", os.path.basename(f)).group(1)


def load_episodes(task):
    by = defaultdict(list)
    for f in sorted(glob.glob(f"{CACHE}/{task}_*.json")):
        for it in json.load(open(f)).get("rows", []):
            by[it["row"]["episode_index"]].append(it["row"])
    out = []
    for ep, rows in sorted(by.items()):
        rows.sort(key=lambda r: r["frame_index"])
        out.append(rows)
    return out


def robust_z(x):
    med = np.median(x)
    mad = np.median(np.abs(x - med)) + 1e-9
    return (x - med) / (1.4826 * mad)


def episode_signal(rows, side):
    p = np.array([r[f"observation.state.{side}_ee_pose_gripper_base"][:3] for r in rows], float)
    a = np.array([r[f"action.{side}_ee_pose_gripper_base"][:3] for r in rows], float)
    g = np.array([r[f"observation.state.{side}_gripper"] for r in rows], float)
    idx = np.array([r["frame_index"] for r in rows], int)
    ok = np.ones(len(rows), bool)
    ok[1:] = (idx[1:] - idx[:-1]) == 1
    e = np.full(len(rows), np.nan)
    perp = np.full(len(rows), np.nan)
    sp = np.full(len(rows), np.nan)
    for t in range(1, len(rows)):
        if not ok[t]:
            continue
        er = p[t] - a[t - 1]
        vc = a[t] - a[t - 1]
        nv = np.linalg.norm(vc)
        e[t] = np.linalg.norm(er)
        sp[t] = nv * 30.0
        if nv > 1e-4:
            par = (er @ vc) / nv
            perp[t] = np.linalg.norm(er - par * vc / nv)
        else:
            perp[t] = np.linalg.norm(er)
    return e, perp, sp, g, ok


def main():
    tasks = sorted({task_of(f) for f in glob.glob(f"{CACHE}/*.json")})
    win = np.arange(-10, 21)
    aligned_perp = []
    aligned_err = []
    aligned_sp = []
    aligned_g = []
    spike_perp = []
    free_perp = []
    event_counts = 0
    ep_count = 0
    # per-episode effect size: contact-window perp vs episode baseline
    effects = []
    for task in tasks:
        for rows in load_episodes(task):
            if len(rows) < 40:
                continue
            ep_count += 1
            for side in ("left", "right"):
                e, perp, sp, g, ok = episode_signal(rows, side)
                good = np.isfinite(perp)
                if good.sum() < 30:
                    continue
                z = robust_z(perp[good])
                zfull = np.full(len(rows), np.nan)
                zfull[good] = z
                # closure events: gripper goes down by >0.6 within one frame
                dg = np.diff(g, prepend=g[0])
                ev = np.where((dg < -0.6) & ok)[0]
                for t0 in ev:
                    lo, hi = t0 + win[0], t0 + win[-1]
                    if lo < 0 or hi >= len(rows):
                        continue
                    if not np.all(ok[lo:hi + 1]):
                        continue
                    aligned_perp.append(zfull[lo:hi + 1])
                    aligned_err.append(e[lo:hi + 1])
                    aligned_sp.append(sp[lo:hi + 1])
                    aligned_g.append(g[lo:hi + 1])
                    event_counts += 1
                    # contact window: +2..+12 after closure; baseline: -10..-2
                    cwin = zfull[t0 + 2:t0 + 13]
                    bwin = zfull[t0 - 10:t0 - 1]
                    if len(cwin) >= 5 and len(bwin) >= 5 and np.all(np.isfinite(cwin)) and np.all(np.isfinite(bwin)):
                        effects.append(float(np.nanmean(cwin) - np.nanmean(bwin)))
                # spikes: high perp at low speed = unexpected contact
                slow = sp < np.nanpercentile(sp[good], 40)
                spike = good & slow & (zfull > 3.0)
                spike_perp.extend(perp[spike].tolist())
                free_perp.extend(perp[good & ~spike].tolist())

    A = np.vstack([x for x in aligned_perp if len(x) == len(win)])
    E = np.vstack([x for x in aligned_err if len(x) == len(win)])
    S = np.vstack([x for x in aligned_sp if len(x) == len(win)])
    G = np.vstack([x for x in aligned_g if len(x) == len(win)])
    print(f"episodes={ep_count} closure_events={event_counts} aligned={len(A)}")
    print("\n frame   z_perp   err_mm   cmd_speed   gripper")
    for j, w in enumerate(win):
        print(f"{w:6d} {np.nanmean(A[:,j]):8.3f} {1e3*np.nanmean(E[:,j]):8.2f} "
              f"{np.nanmean(S[:,j]):9.3f} {np.nanmean(G[:,j]):8.2f}")
    effects = np.array(effects)
    print(f"\ncontact-window effect on z_perp: n={len(effects)} mean={effects.mean():+.3f} "
          f"median={np.median(effects):+.3f} frac>0={np.mean(effects>0):.3f}")
    print(f"spike vs free perp (mm): spike n={len(spike_perp)} median={1e3*np.median(spike_perp):.1f} "
          f"free n={len(free_perp)} median={1e3*np.median(free_perp):.1f}")
    out = {
        "episodes": ep_count,
        "closure_events": event_counts,
        "aligned_window": win.tolist(),
        "aligned_z_perp_mean": np.nanmean(A, axis=0).round(4).tolist(),
        "aligned_err_mm_mean": (1e3*np.nanmean(E, axis=0)).round(2).tolist(),
        "contact_window_effect": {
            "n": int(len(effects)), "mean": float(effects.mean()),
            "median": float(np.median(effects)), "frac_positive": float(np.mean(effects > 0)),
        },
        "spike_vs_free": {
            "spike_n": len(spike_perp), "free_n": len(free_perp),
            "spike_median_mm": float(1e3*np.median(spike_perp)),
            "free_median_mm": float(1e3*np.median(free_perp)),
        },
    }
    json.dump(out, open("exp/impedance_probe2_results.json", "w"), indent=1, ensure_ascii=False)
    print("\nwrote exp/impedance_probe2_results.json")


if __name__ == "__main__":
    main()
