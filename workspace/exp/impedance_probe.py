"""UniBot round 1 (impedance-control line): offline probe of position-interface
tracking error as a sensorless contact/force proxy.

Data: exp/duo_rows_cache/*.json (HF datasets-server rows, 32 tasks, 30 pages x 100
frames each, 30 Hz). No images are cached; only state/action vectors are used.

Question: with a pure position/joint action interface (no torque, no F/T sensor),
is the commanded-vs-achieved end-effector discrepancy a usable contact signal?
And is the discrepancy concentrated in the contact-rich tasks that the teaser
leaderboard says are hardest?

Outputs exp/impedance_probe_results.json. Everything is recomputed from the
cached rows; no network access.
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

# tasks whose last-mile is dominated by insertion / rotation / fine alignment
INSERT_ROT = {
    "PlugInEthernet", "DisconnectEthernet", "PlugCharger", "Unlock",
    "SyringeWaterTransfer", "PourOutMedicine", "ZipUp", "ArrangeTestTubes",
}
CONTACT_HEAVY = INSERT_ROT | {"FoldTowel", "HangCup", "ArrangePlates", "StackBowls",
                              "PaperCupStacking", "StoreCups", "PlacePhotoFrame"}


def task_of(f):
    return re.match(r"(.+)_(\d+)\.json$", os.path.basename(f)).group(1)


def load_episodes(task):
    by = defaultdict(list)
    for f in sorted(glob.glob(f"{CACHE}/{task}_*.json")):
        for it in json.load(open(f)).get("rows", []):
            by[it["row"]["episode_index"]].append(it["row"])
    eps = []
    for ep, rows in sorted(by.items()):
        rows.sort(key=lambda r: r["frame_index"])
        eps.append(rows)
    return eps


def ee_positions(rows, key, frame):
    # 6-vector: xyz + rpy (or axis-angle); cache only needs xyz here
    return np.array([r[key][:3] for r in rows], float)


def analyze_task(task):
    eps = load_episodes(task)
    E, CMD, OBS, SP, GR, PERP, CLOSED = [], [], [], [], [], [], []
    lag_scores = {k: [] for k in (0, 1, 2, 3)}
    for rows in eps:
        if len(rows) < 5:
            continue
        for side in ("left", "right"):
            p = ee_positions(rows, f"observation.state.{side}_ee_pose_gripper_base", side)
            a = ee_positions(rows, f"action.{side}_ee_pose_gripper_base", side)
            g = np.array([r[f"observation.state.{side}_gripper"] for r in rows], float)
            idx = np.array([r["frame_index"] for r in rows], int)
            for t in range(1, len(rows)):
                if idx[t] - idx[t - 1] != 1:
                    continue
                for k in lag_scores:
                    if t - k >= 0:
                        lag_scores[k].append(np.linalg.norm(p[t] - a[t - k]))
                e = p[t] - a[t - 1]
                vc = a[t] - a[t - 1]
                vo = p[t] - p[t - 1]
                nv = np.linalg.norm(vc)
                if nv > 1e-4:
                    epar = (e @ vc) / nv
                    perp = np.linalg.norm(e - epar * vc / nv)
                else:
                    perp = np.linalg.norm(e)
                E.append(np.linalg.norm(e))
                CMD.append(nv)
                OBS.append(np.linalg.norm(vo))
                SP.append(np.linalg.norm(vc) * 30.0)      # m/s
                GR.append(g[t])
                PERP.append(perp)
                CLOSED.append(g[t] < np.percentile(g, 45))
    if not E:
        return None
    E = np.array(E); CMD = np.array(CMD); OBS = np.array(OBS)
    SP = np.array(SP); GR = np.array(GR); PERP = np.array(PERP); CLOSED = np.array(CLOSED)
    # free-space lag slope: e (m) vs commanded speed (m/s) -> seconds
    if SP.std() > 1e-6:
        slope = np.polyfit(SP, E, 1)[0]
    else:
        slope = float("nan")
    # contact-ish = low commanded speed, large orthogonal (unexpected) error
    slow = SP < np.percentile(SP, 35)
    contact = slow & (PERP > np.percentile(PERP, 80))
    # stall = command moves but robot mostly does not (force blockage signature)
    stall = (CMD > np.percentile(CMD, 60)) & (OBS / (CMD + 1e-9) < 0.35) & CLOSED
    lag_best = min(lag_scores, key=lambda k: np.median(lag_scores[k]) if lag_scores[k] else 1e9)
    lb = LB_BY[NAME2LB[task]]
    return {
        "task": task, "lb_task": NAME2LB[task], "lb_mean": lb["mean"],
        "difficulty": lb["difficulty"], "rubric_steps": lb["rubric_steps"],
        "n_pairs": int(len(E)),
        "err_mean_mm": float(1e3 * E.mean()),
        "err_p95_mm": float(1e3 * np.percentile(E, 95)),
        "perp_mean_mm": float(1e3 * PERP.mean()),
        "perp_p95_mm": float(1e3 * np.percentile(PERP, 95)),
        "lag_best_frames": int(lag_best),
        "lag_slope_ms": float(1e3 * slope) if np.isfinite(slope) else None,
        "sp_mean_m_s": float(SP.mean()),
        "contact_frac": float(contact.mean()),
        "stall_frac": float(stall.mean()),
        "gripper_closed_frac": float(CLOSED.mean()),
        "contact_closed_frac": float(CLOSED[contact].mean()) if contact.any() else None,
        "stall_closed_frac": float(CLOSED[stall].mean()) if stall.any() else None,
        "insert_rot": task in INSERT_ROT,
        "contact_heavy": task in CONTACT_HEAVY,
    }


def main():
    tasks = sorted({task_of(f) for f in glob.glob(f"{CACHE}/*.json")})
    res = {}
    for t in tasks:
        r = analyze_task(t)
        if r is not None:
            res[t] = r
    order = sorted(res, key=lambda t: res[t]["lb_mean"])
    print(f"{'task':22s} {'lb':>5s} {'err':>6s} {'p95':>6s} {'perp':>6s} {'perp95':>6s} "
          f"{'lag':>4s} {'slope':>6s} {'spd':>5s} {'contact':>7s} {'stall':>6s} {'cls':>5s}")
    for t in order:
        r = res[t]
        print(f"{t:22s} {r['lb_mean']:5.1f} {r['err_mean_mm']:6.1f} {r['err_p95_mm']:6.1f} "
              f"{r['perp_mean_mm']:6.2f} {r['perp_p95_mm']:6.1f} {r['lag_best_frames']:4d} "
              f"{(r['lag_slope_ms'] or 0):6.1f} {r['sp_mean_m_s']:5.2f} {r['contact_frac']:7.3f} "
              f"{r['stall_frac']:6.3f} {r['gripper_closed_frac']:5.2f}")

    succ = np.array([res[t]["lb_mean"] for t in res])
    print("\n--- Spearman vs teaser mean success (n=%d tasks) ---" % len(res))
    for k in ["err_mean_mm", "err_p95_mm", "perp_mean_mm", "perp_p95_mm",
              "lag_slope_ms", "sp_mean_m_s", "contact_frac", "stall_frac",
              "gripper_closed_frac", "rubric_steps"]:
        v = np.array([res[t][k] if res[t][k] is not None else np.nan for t in res])
        ok = np.isfinite(v)
        rho, p = spearmanr(v[ok], succ[ok])
        print(f"{k:20s} rho={rho:+.3f} p={p:.4f}")

    ins = np.array([res[t]["insert_rot"] for t in res])
    print("\n--- insert/rotate vs other (median) ---")
    for k in ["err_mean_mm", "perp_p95_mm", "contact_frac", "stall_frac", "lag_slope_ms"]:
        v = np.array([res[t][k] if res[t][k] is not None else np.nan for t in res])
        print(f"{k:16s} insert={np.nanmedian(v[ins]):8.2f}  other={np.nanmedian(v[~ins]):8.2f}")

    # combined contact-demand score
    perp = np.array([res[t]["perp_p95_mm"] for t in res])
    stall = np.array([res[t]["stall_frac"] for t in res])
    score = 0.5 * (perp - perp.min()) / (perp.max() - perp.min() + 1e-9) + 0.5 * (stall - stall.min()) / (stall.max() - stall.min() + 1e-9)
    print("\n--- top contact-demand tasks (perp95 + stall) ---")
    for i in np.argsort(-score)[:10]:
        t = list(res)[i]
        print(f"{t:22s} score={score[i]:.3f} perp95={perp[i]:5.1f}mm stall={stall[i]:.3f} lb={res[t]['lb_mean']:.1f}")

    out = {"n_tasks": len(res), "tasks": res, "insert_rot": sorted(INSERT_ROT)}
    json.dump(out, open("exp/impedance_probe_results.json", "w"), indent=1, ensure_ascii=False)
    print("\nwrote exp/impedance_probe_results.json")


if __name__ == "__main__":
    main()
