"""BiCoord prototype probe (round 17).

E619 (DATA-GROUNDED): measure the bimanual coordination profile of the public
G1_Dex1 demonstrations from the cached HF rows, and test whether a task's
coordination demand predicts its (teaser) leaderboard success.

E620 (SYNTHETIC): controlled prototype test of an absolute-pose vs a
relative-pose action parameterisation under common-mode base drift.

Everything here is a *prototype validation*: cheap, falsifiable, and explicitly
labelled as (a) demonstration-data evidence or (b) synthetic mechanism check.
It is NOT real-robot task success.
"""
import glob
import json
import os
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHES = [os.path.join(HERE, "duo_rows_cache"), os.path.join(HERE, "r16_rows_cache")]

# cached dataset name -> leaderboard task id
TASK_MAP = {
    "HangCup": "T01", "FruitCollection": "T02", "DisconnectEthernet": "T05",
    "ColorArrangement": "T06", "PlacePhotoFrame": "T07", "OrganizeBookshelf": "T08",
    "PlugCharger": "T10", "PickOutBatteries": "T11", "Unlock": "T12",
    "ArrangeTestTubes": "T13", "PourOutMedicine": "T14", "FoldTowel": "T16",
    "ZipUp": "T19", "ArrangePlates": "T21", "SpellRobot": "T22",
    "ConveyorSorting": "T24", "PlugInEthernet": "T26", "StackBowls": "T27",
    "SyringeWaterTransfer": "T32",
}


def load_rows(ds):
    rows = []
    for root in CACHES:
        for f in glob.glob(os.path.join(root, f"{ds}_*.json")):
            payload = json.load(open(f))
            for item in payload.get("rows", []):
                rows.append(item["row"])
    seen = {}
    for r in rows:
        seen[(int(r.get("episode_index", 0)), int(r.get("index", 0)))] = r
    rows = list(seen.values())
    rows.sort(key=lambda r: (int(r.get("episode_index", 0)), int(r.get("index", 0))))
    return rows


def split_episodes(rows, min_frames=20):
    eps = defaultdict(list)
    for r in rows:
        eps[int(r.get("episode_index", 0))].append(r)
    out = []
    for e in sorted(eps):
        rr = sorted(eps[e], key=lambda r: int(r.get("index", 0)))
        if len(rr) >= min_frames:
            out.append(rr)
    return out


def arr(rr, key, dim=None):
    v = np.array([np.atleast_1d(r[key]).astype(float) for r in rr])
    if dim is not None:
        v = v[:, :dim]
    return v


def quant(a, qs=(10, 50, 90, 99)):
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    return {f"q{q}": float(np.percentile(a, q)) for q in qs}


def profile(ds):
    rows = load_rows(ds)
    eps = split_episodes(rows)
    # pooled per-frame signals
    gL_all, gR_all = [], []
    spL_all, spR_all = [], []
    both, holdact, relmove, commove = [], [], [], []
    relshare, commshare, actdiff = [], [], []
    n_frames = 0
    for rr in eps:
        pL = arr(rr, "observation.state.left_ee_pose_gripper_base", 3)
        pR = arr(rr, "observation.state.right_ee_pose_gripper_base", 3)
        gL = arr(rr, "observation.state.left_gripper").ravel()
        gR = arr(rr, "observation.state.right_gripper").ravel()
        if len(rr) < 2:
            continue
        dpL = np.linalg.norm(np.diff(pL, axis=0), axis=1)
        dpR = np.linalg.norm(np.diff(pR, axis=0), axis=1)
        d = pR - pL
        dd = np.linalg.norm(np.diff(d, axis=0), axis=1)
        dc = np.linalg.norm(np.diff((pL + pR) / 2.0, axis=0), axis=1)
        gLm, gRm = gL[1:], gR[1:]
        glc, grc = gLm < 1.0, gRm < 1.0
        n_frames += len(dd)
        gL_all.append(gLm); gR_all.append(gRm)
        spL_all.append(dpL); spR_all.append(dpR)
        relshare.append(dd / (dpL + dpR + 1e-9))
        commshare.append(dc / (dpL + dpR + 1e-9))
        actdiff.append(dpR - dpL)
    gL_all = np.concatenate(gL_all); gR_all = np.concatenate(gR_all)
    spL_all = np.concatenate(spL_all); spR_all = np.concatenate(spR_all)
    relshare = np.concatenate(relshare); commshare = np.concatenate(commshare)
    # frame thresholds are absolute (m/frame @30 fps); 0.002 m/frame ~ 6 cm/s
    t_move = 0.002
    t_still = 0.001
    # recompute boolean arrays consistently from pooled data
    glc = gL_all < 1.0; grc = gR_all < 1.0
    mvL = spL_all > t_move; mvR = spR_all > t_move
    stillL = spL_all < t_still; stillR = spR_all < t_still
    anchorL = glc & stillL
    anchorR = grc & stillR
    holdact = (anchorL & mvR) | (anchorR & mvL)
    both = mvL & mvR
    profile = {
        "n_frames": int(n_frames), "n_episodes": len(eps),
        "gripL": quant(gL_all), "gripR": quant(gR_all),
        "speedL": quant(spL_all), "speedR": quant(spR_all),
        "frac_grip_closed_L": float(np.mean(glc)),
        "frac_grip_closed_R": float(np.mean(grc)),
        "frac_both_moving": float(np.mean(both)),
        "frac_hold_and_act": float(np.mean(holdact)),
        "frac_anchorL_actR": float(np.mean(anchorL & mvR)),
        "frac_anchorR_actL": float(np.mean(anchorR & mvL)),
        "rel_share_mean": float(np.mean(relshare)),
        "common_share_mean": float(np.mean(commshare)),
        "asym_activity_ratio": float(np.mean(spR_all) / (np.mean(spL_all) + 1e-9)),
        "role_flip_rate_per100": float(np.mean(np.abs(np.diff(np.sign(actdiff))) > 0) * 100),
    }
    return profile


def load_lb():
    st = json.load(open(os.path.join(HERE, "r16_leaderboard_stats.json")))
    return {t["id"]: t for t in st["per_task"]}


def spearman(rho_pairs):
    x, y = zip(*rho_pairs)
    x = np.asarray(x, float); y = np.asarray(y, float)
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    return float(np.corrcoef(rx, ry)[0, 1])


def e619():
    lb = load_lb()
    prof = {}
    for ds, tid in TASK_MAP.items():
        try:
            prof[ds] = profile(ds)
        except Exception as exc:  # noqa: BLE001
            print("skip", ds, exc)
    rows = []
    for ds, p in sorted(prof.items()):
        tid = TASK_MAP[ds]
        t = lb[tid]
        demand = p["frac_hold_and_act"] + 0.5 * p["frac_both_moving"]
        rows.append(dict(dataset=ds, task_id=tid, task=t["task"], demand=demand,
                         mean_success=t["mean"], best_success=t["max"],
                         **{k: p[k] for k in ("n_frames", "n_episodes",
                            "frac_both_moving", "frac_hold_and_act",
                            "frac_anchorL_actR", "frac_anchorR_actL",
                            "rel_share_mean", "common_share_mean",
                            "asym_activity_ratio", "role_flip_rate_per100",
                            "frac_grip_closed_L", "frac_grip_closed_R")}))
    rows.sort(key=lambda r: -r["demand"])
    return rows


def e620(seed=20261118, n=200000):
    rng = np.random.default_rng(seed)
    tol = 0.005  # 5 mm insertion tolerance (per-axis tolerance box, 3-D norm)
    # common-mode base drift sigma vs anchor(relative) estimation sigma
    sig_b = np.array([0.0, 0.002, 0.005, 0.010, 0.020])
    sig_a = 0.002
    sig_n = 0.001
    out = []
    for sb in sig_b:
        # slow base drift: one random common offset per trial (frozen during insert)
        b = rng.normal(0, sb, size=(n, 3)) if sb > 0 else np.zeros((n, 3))
        n_a = rng.normal(0, sig_a, size=(n, 3))
        n_act = rng.normal(0, sig_n, size=(n, 3))
        e_abs = np.linalg.norm(b + n_act, axis=1)
        e_rel = np.linalg.norm(n_a + n_act, axis=1)
        out.append(dict(sigma_base_mm=sb * 1000,
                        abs_success=float(np.mean(e_abs < tol)),
                        rel_success=float(np.mean(e_rel < tol)),
                        abs_med_err_mm=float(np.median(e_abs) * 1000),
                        rel_med_err_mm=float(np.median(e_rel) * 1000)))
    # random-walk drift during a 40-step insertion, compare final accumulated
    steps = 40
    rw = 0.0015
    trial = 50000
    drift = np.cumsum(rng.normal(0, rw, size=(trial, steps, 3)), axis=1)
    e_abs_rw = np.linalg.norm(drift[:, -1] + rng.normal(0, sig_n, (trial, 3)), axis=1)
    e_rel_rw = np.linalg.norm(rng.normal(0, sig_a, (trial, 3)) + rng.normal(0, sig_n, (trial, 3)), axis=1)
    rw_out = dict(abs_success=float(np.mean(e_abs_rw < tol)),
                  rel_success=float(np.mean(e_rel_rw < tol)),
                  abs_med_err_mm=float(np.median(e_abs_rw) * 1000),
                  rel_med_err_mm=float(np.median(e_rel_rw) * 1000))
    return dict(tol_mm=tol * 1000, sigma_anchor_mm=sig_a * 1000,
                sigma_action_mm=sig_n * 1000, common_mode=out, random_walk=rw_out)


def main():
    print("=" * 78)
    print("E619  data-grounded bimanual coordination profile (cached public demos)")
    print("=" * 78)
    rows = e619()
    print(f"{'dataset':22s} {'task':26s} {'demand':>6s} {'holdAct':>7s} {'both':>5s} {'relShare':>8s} {'succ':>5s}")
    for r in rows:
        print(f"{r['dataset']:22s} {r['task'][:26]:26s} {r['demand']:6.3f} "
              f"{r['frac_hold_and_act']:7.3f} {r['frac_both_moving']:5.3f} "
              f"{r['rel_share_mean']:8.3f} {r['mean_success']:5.1f}")
    pairs = [(r["demand"], r["mean_success"]) for r in rows]
    pairs_best = [(r["demand"], r["best_success"]) for r in rows]
    print("\nSpearman(demand, teaser mean success) =", round(spearman(pairs), 3),
          " n =", len(rows))
    print("Spearman(demand, teaser best success) =", round(spearman(pairs_best), 3))
    pr = [(r["frac_hold_and_act"], r["mean_success"]) for r in rows]
    print("Spearman(hold&act, teaser mean success) =", round(spearman(pr), 3))

    print("\n" + "=" * 78)
    print("E620  synthetic prototype: absolute vs relative pose under base drift")
    print("=" * 78)
    sim = e620()
    for c in sim["common_mode"]:
        print(f"sigma_base={c['sigma_base_mm']:5.1f} mm  "
              f"P(success) abs={c['abs_success']:.3f} rel={c['rel_success']:.3f}  "
              f"median err abs={c['abs_med_err_mm']:6.2f} mm rel={c['rel_med_err_mm']:5.2f} mm")
    print("random-walk drift (40 steps, 1.5 mm/step):", json.dumps(sim["random_walk"]))

    json.dump(dict(e619=rows, e620=sim), open(os.path.join(HERE, "bicoord_probe_results.json"), "w"), indent=1)
    print("\nwrote exp/bicoord_probe_results.json")


if __name__ == "__main__":
    main()
