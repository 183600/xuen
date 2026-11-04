"""Round-16 POSE-CONTRACT VLA: real-data analysis (E1-E4).

Sources
  - rows cache  : HF datasets-server rows for unitreerobotics/G1_Dex1_* (retrieved 2026-11-03)
  - statistics  : unitreerobotics/UnifoLM-WLA-1.0-Base/dataset_statistics.json (retrieved 2026-11-04)

Outputs
  - pc_vla_real_results.json

Everything here is measurement on public data; no model is trained.
"""
from __future__ import annotations

import glob
import json
import math
import os
from collections import defaultdict

import numpy as np
from scipy.spatial.transform import Rotation

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "duo_rows_cache")
STATS = "/tmp/opencode/ds_stats.json"

# Official statistics for the Dex1 embodiment (action module, 54 dims).
# dims [0:6] left EE relative pose, [6] left gripper, [13:19] right EE, [19] right gripper.
OFFSET = None
SCALE = None


def load_stats():
    global OFFSET, SCALE
    d = json.load(open(STATS))
    a = d["UnifoLM_G1_Dex1"]["action"]
    OFFSET = np.array(a["offset"], dtype=np.float64)
    SCALE = np.array(a["scale"], dtype=np.float64)


def se3_from_rpy(xyzrpy):
    xyzrpy = np.asarray(xyzrpy, dtype=np.float64)
    R = Rotation.from_euler("xyz", xyzrpy[3:]).as_matrix()
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = xyzrpy[:3]
    return T


def load_task(task):
    """Return dict of aligned per-frame arrays for one task (rows in index order)."""
    files = sorted(glob.glob(os.path.join(CACHE, f"{task}_*.json")),
                   key=lambda p: int(os.path.basename(p).rsplit("_", 1)[1].split(".")[0]))
    rec = defaultdict(list)
    for f in files:
        d = json.load(open(f))
        for r in d["rows"]:
            row = r["row"]
            rec["idx"].append(row["index"])
            rec["ep"].append(row["episode_index"])
            rec["fi"].append(row["frame_index"])
            rec["obs_l"].append(row["observation.state.left_ee_pose_gripper_base"])
            rec["obs_r"].append(row["observation.state.right_ee_pose_gripper_base"])
            rec["act_l"].append(row["action.left_ee_pose_gripper_base"])
            rec["act_r"].append(row["action.right_ee_pose_gripper_base"])
            rec["grip_l"].append(row["observation.state.left_gripper"])
            rec["grip_r"].append(row["observation.state.right_gripper"])
            rec["agrip_l"].append(row["action.left_gripper"])
    out = {}
    for k, v in rec.items():
        out[k] = np.array(v, dtype=np.float64) if k not in ("idx", "ep", "fi") else np.array(v)
    return out


def contiguous_runs(task_data, max_k=29):
    """Yield (i, j) index pairs inside the same episode with frame_index distance d<=max_k."""
    fi = task_data["fi"]
    ep = task_data["ep"]
    n = len(fi)
    runs = []
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ep[j + 1] == ep[i] and fi[j + 1] == fi[j] + 1:
            j += 1
        runs.append((i, j))
        i = j + 1
    return runs


def rel_action(T_ref, T_tgt):
    """Relative action exactly as the official spec: T_ref^{-1} T_tgt."""
    Rrel = T_ref[:3, :3].T @ T_tgt[:3, :3]
    prel = T_ref[:3, :3].T @ (T_tgt[:3, 3] - T_ref[:3, 3])
    rotvec = Rotation.from_matrix(Rrel).as_rotvec()
    return np.concatenate([prel, rotvec])


def geom_err(T_a, T_b):
    dp = np.linalg.norm(T_a[:3, 3] - T_b[:3, 3])
    dR = Rotation.from_matrix(T_a[:3, :3].T @ T_b[:3, :3]).magnitude()
    return dp, dR


# ---------------------------------------------------------------- E1 / E2 / E3


def analyse_task(task, max_k=29):
    d = load_task(task)
    runs = contiguous_runs(d)
    Tobs_l = [se3_from_rpy(p) for p in d["obs_l"]]
    Tobs_r = [se3_from_rpy(p) for p in d["obs_r"]]
    Tact_l = [se3_from_rpy(p) for p in d["act_l"]]
    Tact_r = [se3_from_rpy(p) for p in d["act_r"]]

    e1 = {"pos_mm": defaultdict(list), "rot_deg": defaultdict(list)}
    e2 = {"dp_mm": defaultdict(list), "drot_deg": defaultdict(list)}
    for (i, j) in runs:
        for arm, To, Ta in (("L", Tobs_l, Tact_l), ("R", Tobs_r, Tact_r)):
            for k in range(1, max_k + 1):
                if i + k > j:
                    break
                ra = rel_action(To[i], To[i + k])
                e1["pos_mm"][k].append(np.linalg.norm(ra[:3]) * 1000.0)
                e1["rot_deg"][k].append(np.linalg.norm(ra[3:]) * 180.0 / math.pi)
                dp, dr = geom_err(Ta[i + k], To[i + k])
                e2["dp_mm"][k].append(dp * 1000.0)
                e2["drot_deg"][k].append(dr * 180.0 / math.pi)

    def q(a, p):
        return float(np.percentile(np.asarray(a, dtype=np.float64), p)) if len(a) else float("nan")

    E1 = {
        "k": [],
        "median_pos_mm": {}, "p90_pos_mm": {},
        "median_rot_deg": {}, "p90_rot_deg": {},
        "median_norm_pos": {}, "median_norm_rot": {},
    }
    scale_t = float(np.mean(SCALE[0:3]))
    scale_r = float(np.mean(SCALE[3:6]))
    for k in range(1, max_k + 1):
        p = e1["pos_mm"][k]
        r = e1["rot_deg"][k]
        if not p:
            continue
        E1["k"].append(k)
        E1["median_pos_mm"][k] = q(p, 50)
        E1["p90_pos_mm"][k] = q(p, 90)
        E1["median_rot_deg"][k] = q(r, 50)
        E1["p90_rot_deg"][k] = q(r, 90)
        E1["median_norm_pos"][k] = q(p, 50) / 1000.0 / scale_t
        E1["median_norm_rot"][k] = q(r, 50) / 180.0 * math.pi / scale_r

    E2 = {"dp_mm": {}, "drot_deg": {}}
    for k in range(1, max_k + 1):
        E2["dp_mm"][k] = q(e2["dp_mm"][k], 50)
        E2["drot_deg"][k] = q(e2["drot_deg"][k], 50)
    E2["p90_dp_mm"] = {k: q(e2["dp_mm"][k], 90) for k in range(1, max_k + 1)}
    E2["p90_drot_deg"] = {k: q(e2["drot_deg"][k], 90) for k in range(1, max_k + 1)}

    # first k whose median drift crosses thresholds
    cross = {}
    for thr_mm, key in ((5.0, "dp_mm"), (10.0, "dp_mm"), (20.0, "dp_mm")):
        kk = None
        for k in range(1, max_k + 1):
            if E2[key][k] == E2[key][k] and E2[key][k] > thr_mm:
                kk = k
                break
        cross[f"med_pos>{thr_mm}mm"] = kk
    for thr_deg in (5.0, 10.0, 20.0):
        kk = None
        for k in range(1, max_k + 1):
            if E2["drot_deg"][k] == E2["drot_deg"][k] and E2["drot_deg"][k] > thr_deg:
                kk = k
                break
        cross[f"med_rot>{thr_deg}deg"] = kk

    # gripper statistics
    grip = {
        "obs_min": float(d["grip_l"].min()), "obs_max": float(d["grip_l"].max()),
        "act_min": float(d["agrip_l"].min()), "act_max": float(d["agrip_l"].max()),
        "frac_act_at_max": float(np.mean(d["agrip_l"] > d["agrip_l"].max() - 1e-3)),
    }
    return {"n_frames": int(len(d["fi"])), "n_episodes": int(len(set(d["ep"].tolist()))),
            "E1": E1, "E2": E2, "cross": cross, "gripper": grip,
            "scale_t_m": scale_t, "scale_r_rad": scale_r}


# ---------------------------------------------------------------- E3


def chunk_localisation(task, sigmas=(0.0, 0.001, 0.005, 0.02), n_trials=400, seed=0):
    """Recover the chunk index from the observed EE pose (E3)."""
    rng = np.random.default_rng(seed)
    d = load_task(task)
    runs = contiguous_runs(d)
    Tact_l = [se3_from_rpy(p) for p in d["act_l"]]
    Tobs_l = [se3_from_rpy(p) for p in d["obs_l"]]
    starts = []
    for (i, j) in runs:
        if j - i > 29:
            starts.append(i)
    rng.shuffle(starts)
    starts = starts[:n_trials]
    res = {}
    for sig in sigmas:
        ok = 0
        err = []
        for i in starts:
            m = int(rng.integers(0, 30))
            if i + m >= len(Tobs_l):
                continue
            chunk = [Tact_l[i + j] for j in range(30)]
            T = Tobs_l[i + m].copy()
            if sig > 0:
                T[:3, 3] += rng.normal(0, sig, 3)
                T[:3, :3] = Rotation.from_rotvec(
                    rng.normal(0, sig / 0.05, 3)).as_matrix() @ T[:3, :3]
            best, bi = 1e9, 0
            for j, Tc in enumerate(chunk):
                dp, dr = geom_err(T, Tc)
                c = dp / 0.01 + dr / 0.05
                if c < best:
                    best, bi = c, j
            err.append(abs(bi - m))
            ok += int(bi == m)
        res[f"sigma_{sig}"] = {"exact": ok / max(1, len(err)),
                               "mae_steps": float(np.mean(err)) if err else float("nan")}
    # semantics probe: is the next observed pose closer to chunk[0] or chunk[-1]?
    votes = {"first": 0, "last": 0, "middle": 0}
    for i in starts[:200]:
        chunk = [Tact_l[i + j] for j in range(30)]
        if i + 30 >= len(Tobs_l):
            continue
        T = Tobs_l[i + 30]
        costs = []
        for Tc in chunk:
            dp, dr = geom_err(T, Tc)
            costs.append(dp / 0.01 + dr / 0.05)
        costs = np.array(costs)
        if costs[0] < costs[-1]:
            votes["first"] += 1
        elif costs[-1] < costs[0]:
            votes["last"] += 1
        else:
            votes["middle"] += 1
    return {"localisation": res, "semantics_probe": votes}


# ---------------------------------------------------------------- E4


def loss_geometry(task, k=5, ridge=1e-3, n_test=400, seed=0):
    """Closed-form comparison of training-loss geometries on real trajectories.

    target y: k-step relative EE action (6 dims) in metric units.
    features x: [1, p_rel_1(3), theta_1(3), gripper, |p_rel_1|, gripper_d]
    weights:
      W_norm   : official normalized-space MSE  (w_d = 1/scale_d^2)
      W_metric : plain metric MSE                (w_d = 1)
      W_tol    : metric MSE weighted by per-task tolerance (tight tasks get larger w)
    """
    rng = np.random.default_rng(seed)
    d = load_task(task)
    runs = contiguous_runs(d)
    X, Y = [], []
    grip_o = d["grip_l"]
    grip_a = d["agrip_l"]
    for (i, j) in runs:
        if i + k > j:
            continue
        T0 = se3_from_rpy(d["obs_l"][i])
        Tk = se3_from_rpy(d["obs_l"][i + k])
        y = rel_action(T0, Tk)
        x = np.concatenate([[1.0], y[:3], y[3:], [grip_o[i]],
                            [np.linalg.norm(y[:3])], [grip_a[i] - grip_o[i]]])
        X.append(x)
        Y.append(y)
    X = np.array(X)
    Y = np.array(Y)
    if len(X) < 200:
        return None
    perm = rng.permutation(len(X))
    ntr = int(0.8 * len(X))
    tr, te = perm[:ntr], perm[ntr:]
    Xtr, Ytr, Xte, Yte = X[tr], Y[tr], X[te], Y[te]

    scale = np.array([SCALE[0], SCALE[1], SCALE[2], SCALE[3], SCALE[4], SCALE[5]])
    tol = np.array([0.002, 0.002, 0.002, 0.087, 0.087, 0.087])  # 2mm / 5deg tolerance
    w_norm = 1.0 / scale ** 2
    w_metric = np.ones(6)
    w_tol = 1.0 / tol ** 2

    out = {}
    for name, w in (("norm", w_norm), ("metric", w_metric), ("tol", w_tol)):
        # weighted ridge: minimise sum w_d (y_d - x_d theta)^2
        Xw = Xtr * w ** 0.5
        Yw = Ytr * w ** 0.5
        A = Xw.T @ Xw + ridge * np.eye(Xtr.shape[1])
        theta = np.linalg.solve(A, Xw.T @ Yw)
        pred = Xte @ theta
        ep = np.linalg.norm(pred[:, :3] - Yte[:, :3], axis=1) * 1000.0
        er = np.linalg.norm(pred[:, 3:] - Yte[:, 3:], axis=1) * 180.0 / math.pi
        out[name] = {
            "pos_med_mm": float(np.median(ep)), "pos_p90_mm": float(np.percentile(ep, 90)),
            "rot_med_deg": float(np.median(er)), "rot_p90_deg": float(np.percentile(er, 90)),
            "P(prec:5mm&5deg)": float(np.mean((ep < 5) & (er < 5))),
            "P(loose:20mm&15deg)": float(np.mean((ep < 20) & (er < 15))),
        }
    return {"n": int(len(X)), "k": k, "results": out}


def main():
    load_stats()
    tasks = sorted({os.path.basename(f).rsplit("_", 1)[0]
                    for f in glob.glob(os.path.join(CACHE, "*.json"))})
    res = {"tasks": {}, "official_scale": {
        "left_ee_trans_m": [float(x) for x in SCALE[0:3]],
        "left_ee_rot_rad": [float(x) for x in SCALE[3:6]],
        "left_gripper": float(SCALE[6]),
        "right_ee_trans_m": [float(x) for x in SCALE[13:16]],
        "right_ee_rot_rad": [float(x) for x in SCALE[16:19]],
    }}
    for t in tasks:
        a = analyse_task(t)
        res["tasks"][t] = a
        print(t, a["n_frames"], "cross", a["cross"], flush=True)
    res["E3_localisation"] = chunk_localisation("PlugInEthernet")
    res["E3_localisation_2"] = chunk_localisation("HangCup")
    res["E4_loss_geometry"] = {t: loss_geometry(t) for t in
                               ("PlugInEthernet", "Unlock", "ArrangePlates", "HangCup",
                                "ZipUp", "OrganizeBookshelf")}
    json.dump(res, open(os.path.join(HERE, "pc_vla_real_results.json"), "w"),
              indent=1, ensure_ascii=False)
    print("saved")


if __name__ == "__main__":
    main()
