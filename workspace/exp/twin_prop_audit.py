"""Real-data audit (round 27): how exactly is the head-camera extrinsics recoverable
from the API-visible waist channel?

Source: cached official UniBot-V1 state rows (exp/unibot_states/*.npz; HF
datasets-server, fetched 2026-11-04).  API-visible inputs: lower_body[15].
Ground truth (dataset-only): state_d435 (head camera pose), state_torso, waist_state_joint.

Models compared (episode-disjoint / leave-one-task-out splits):
  B0  static offset                    (ignore the waist entirely)
  B1  rigid mount                      (head pose = R(q_waist) * const)   [round-26 assumption]
  B2  gain-compensated kinematic mount (head joints u = G * q_waist + c)  [proposed]

B2 has 15 interpretable parameters (3 gains, 3 offsets, 3 rot-offset, 3 trans-offset,
3 lever arm) and is the forward-kinematics form of the "body graph".

Also reports:
  E12-a channel identity  lower_body[12:15] == waist_state_joint ?
  E12-b regime             is the torso height ever commanded/changed?
  E12-c recoverability    translation / rotation error per model, per split
  E12-d self-consistency  r_body = ||log(T_prop^-1 T_d435)|| distribution -> gate threshold
  E12-e transfer          leave-one-task-out (calibration is a robot property, not a task property)

Output: exp/twin_prop_audit_results.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
DAT = EXP / "unibot_states"
OUT = EXP / "twin_prop_audit_results.json"

# channel conventions (verified in this file, E12-a / E12-f)
WAIST_COLS = (0, 1, 2)          # waist_state_joint = (yaw_z, roll_x, pitch_y)
D435_RPY_COLS = (3, 4, 5)       # state_d435 rpy = (roll_x, pitch_y, yaw_z)


def rot_zyx(yaw: float, roll: float, pitch: float) -> np.ndarray:
    Rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
    Ry = np.array([[np.cos(pitch), 0, np.sin(pitch)], [0, 1, 0], [-np.sin(pitch), 0, np.cos(pitch)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(roll), -np.sin(roll)], [0, np.sin(roll), np.cos(roll)]])
    return Rz @ Ry @ Rx


def rot_batch(q_xyz: np.ndarray) -> np.ndarray:
    """q_xyz = (x-roll, y-pitch, z-yaw) -> Rz(yaw) Ry(pitch) Rx(roll)."""
    return np.stack([rot_zyx(float(q[2]), float(q[0]), float(q[1])) for q in q_xyz])


def log_so3(R: np.ndarray) -> np.ndarray:
    c = float(np.clip((np.trace(R) - 1.0) / 2.0, -1.0, 1.0))
    th = np.arccos(c)
    if th < 1e-9:
        return np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / 2.0
    w = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2.0 * np.sin(th))
    return w * th


def exp_so3(w: np.ndarray) -> np.ndarray:
    th = float(np.linalg.norm(w))
    if th < 1e-12:
        return np.eye(3)
    k = w / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * (K @ K)


def rot_geodesic(Ra: np.ndarray, Rb: np.ndarray) -> float:
    return float(np.linalg.norm(log_so3(Ra.T @ Rb)))


# ---------------------------------------------------------------- B2 model --
def unpack_params(p: np.ndarray):
    g = p[0:3]            # gains on (roll_x, pitch_y, yaw_z)
    c = p[3:6]            # offsets
    R_off = exp_so3(p[6:9])
    t_off = p[9:12]
    p_off = p[12:15]
    return g, c, R_off, t_off, p_off


def head_joints(w_xyz: np.ndarray, g: np.ndarray, c: np.ndarray) -> np.ndarray:
    return w_xyz * g[None, :] + c[None, :]


def predict_B2(w_xyz: np.ndarray, p: np.ndarray):
    g, c, R_off, t_off, p_off = unpack_params(p)
    u = head_joints(w_xyz, g, c)
    Ru = rot_batch(u)
    t = t_off[None, :] + np.einsum("nij,j->ni", Ru, p_off)
    R = np.stack([Ru[i] @ R_off for i in range(len(Ru))])
    return t, R


def fit_B2(w_xyz: np.ndarray, t_obs: np.ndarray, R_obs: np.ndarray, p0: np.ndarray):
    def resid(p):
        t, R = predict_B2(w_xyz, p)
        ang = np.array([log_so3(R[i].T @ R_obs[i]) for i in range(len(R))])
        return np.concatenate([(t - t_obs).ravel(), ang.ravel()])

    sol = least_squares(resid, p0, method="lm", max_nfev=200)
    return sol.x, float(np.sqrt((sol.fun ** 2).mean()))


def init_params(w_xyz: np.ndarray, t_obs: np.ndarray, R_obs: np.ndarray) -> np.ndarray:
    """Crude per-axis linear initialisation: d435 rpy ~ a * w + b."""
    g = np.ones(3)
    c = np.zeros(3)
    for i in range(3):
        A = np.vstack([w_xyz[:, i], np.ones(len(w_xyz))]).T
        a, b = np.linalg.lstsq(A, R_obs[:, i] if False else None, rcond=None)[0] if False else (None, None)
    # rotation residual in euler of d435 is awkward; use least_squares from identity init instead
    p0 = np.zeros(15)
    p0[0:3] = np.array([1.8, 1.0, 0.95])   # coarse gains seen in the audit
    p0[6:9] = np.zeros(3)
    p0[9:12] = t_obs.mean(axis=0)
    p0[12:15] = np.zeros(3)
    return p0


def fit_B1(w_xyz: np.ndarray, t_obs: np.ndarray, R_obs: np.ndarray):
    """Rigid mount: gains fixed to 1, offsets free (9 params)."""
    def resid(p):
        g = np.ones(3)
        c = p[0:3]
        R_off = exp_so3(p[3:6])
        t_off = p[6:9]
        p_off = p[9:12]
        u = head_joints(w_xyz, g, c)
        Ru = rot_batch(u)
        t = t_off[None, :] + np.einsum("nij,j->ni", Ru, p_off)
        R = np.stack([Ru[i] @ R_off for i in range(len(Ru))])
        ang = np.array([log_so3(R[i].T @ R_obs[i]) for i in range(len(R))])
        return np.concatenate([(t - t_obs).ravel(), ang.ravel()])

    sol = least_squares(resid, np.zeros(12), method="lm", max_nfev=200)
    return sol.x, float(np.sqrt((sol.fun ** 2).mean()))


def fit_B0(t_obs: np.ndarray, R_obs: np.ndarray):
    t = t_obs.mean(axis=0)
    M = np.sum(R_obs, axis=0)
    U, _, Vt = np.linalg.svd(M)
    D = np.eye(3)
    if np.linalg.det(U @ Vt) < 0:
        D[2, 2] = -1
    return t, U @ D @ Vt


def main() -> None:
    res = {
        "source": "exp/unibot_states/*.npz (official G1_Dex1_* rows via HF datasets-server, fetched 2026-11-04)",
        "api_visible_input": "observation.state.lower_body[15]",
        "ground_truth": ["observation.state.state_d435", "observation.state.state_torso"],
        "conventions": {"waist_state_joint": "(yaw_z, roll_x, pitch_y)",
                        "state_d435": "(x,y,z, roll_x, pitch_y, yaw_z)"},
        "tasks": {},
    }
    data = {}
    for npz in sorted(DAT.glob("*.npz")):
        task = npz.stem
        z = np.load(npz, allow_pickle=True)

        def unpack(key):
            arr = z[key]
            return arr.item() if arr.dtype == object else {k: arr[k] for k in arr.files}

        lbs, ws, ts, ds, es = [], [], [], [], []
        for grp in ("random", "contig"):
            sub = unpack(grp)
            if len(sub.get("frame_index", [])) == 0:
                continue
            lbs.append(sub["observation.state.lower_body"])
            ws.append(sub["observation.state.waist_state_joint"])
            ts.append(sub["observation.state.state_torso"])
            ds.append(sub["observation.state.state_d435"])
            es.append(sub["episode_index"])
        lb = np.concatenate(lbs); w = np.concatenate(ws)
        t = np.concatenate(ts); d = np.concatenate(ds); epi = np.concatenate(es)
        data[task] = dict(lb=lb, w=w, t=t, d=d, epi=epi)

        # E12-a channel identity
        dmax = float(np.abs(lb[:, 12:15] - w).max())
        # E12-b regime
        tz = np.unique(np.round(t[:, 2], 6))
        # E12-f per-axis gains (diagnostic)
        gains = {}
        for nm, wc, dc in (("roll_x", 1, 3), ("pitch_y", 2, 4), ("yaw_z", 0, 5)):
            A = np.vstack([w[:, wc], np.ones(len(w))]).T
            a, b = np.linalg.lstsq(A, d[:, dc], rcond=None)[0]
            gains[nm] = {"slope": float(a), "intercept": float(b),
                         "resid_std_rad": float((d[:, dc] - (a * w[:, wc] + b)).std())}
        res["tasks"][task] = {
            "frames": int(len(lb)),
            "n_episodes": int(len(np.unique(epi))),
            "E12a_lower_body_12_15_equals_waist_max_abs_diff": dmax,
            "E12b_torso_z_unique": [float(v) for v in tz],
            "E12b_waist_range_rad": {"yaw_z": float(np.ptp(w[:, 0])),
                                     "roll_x": float(np.ptp(w[:, 1])),
                                     "pitch_y": float(np.ptp(w[:, 2]))},
            "E12f_per_axis_gain": gains,
        }

    def xyzd(task):
        D = data[task]
        return (D["w"][:, [1, 2, 0]], D["d"][:, :3], rot_batch(D["d"][:, 3:6]), D["epi"])

    tasks = sorted(data)
    rng = np.random.default_rng(20261107)

    # ---------------- global calibration + leave-one-task-out --------------
    def collect(sel_tasks):
        W, T, R = [], [], []
        for tk in sel_tasks:
            w, t, r, _ = xyzd(tk)
            W.append(w); T.append(t); R.append(r)
        return np.concatenate(W), np.concatenate(T), np.concatenate(R)

    loto = {}
    for held in tasks:
        tr = [tk for tk in tasks if tk != held]
        W, T, R = collect(tr)
        p2, _ = fit_B2(W, T, R, init_params(W, T, R))
        w, t, r, _ = xyzd(held)
        t2, R2 = predict_B2(w, p2)
        err_t = np.linalg.norm(t2 - t, axis=1)
        err_R = np.array([rot_geodesic(R2[i], r[i]) for i in range(len(R2))])
        g, c, R_off, t_off, p_off = unpack_params(p2)
        loto[held] = {
            "B2_t_rmse_m": float(np.sqrt((err_t ** 2).mean())),
            "B2_t_p95_m": float(np.percentile(err_t, 95)),
            "B2_R_rmse_rad": float(np.sqrt((err_R ** 2).mean())),
            "B2_R_p95_rad": float(np.percentile(err_R, 95)),
            "gains": {"roll_x": float(g[0]), "pitch_y": float(g[1]), "yaw_z": float(g[2])},
        }
    res["E12e_leave_one_task_out_B2"] = loto
    res["E12e_LOTO_median_t_rmse_m"] = float(np.median([v["B2_t_rmse_m"] for v in loto.values()]))
    res["E12e_LOTO_max_t_rmse_m"] = float(max(v["B2_t_rmse_m"] for v in loto.values()))
    res["E12e_LOTO_max_R_rmse_rad"] = float(max(v["B2_R_rmse_rad"] for v in loto.values()))
    res["E12e_gain_stability_across_folds"] = {
        k: [round(loto[t]["gains"][k], 4) for t in tasks] for k in ("roll_x", "pitch_y", "yaw_z")}

    # ---------------- episode-disjoint comparison, all tasks pooled --------
    W, T, R, EP = collect(tasks)
    epi = np.concatenate([data[tk]["epi"] for tk in tasks])
    task_id = np.concatenate([np.full(len(data[tk]["epi"]), i) for i, tk in enumerate(tasks)])
    # split: per task, half of the episodes -> train
    tr_mask = np.zeros(len(W), dtype=bool)
    for i, tk in enumerate(tasks):
        eps = np.unique(data[tk]["epi"])
        half = set(rng.permutation(eps)[: max(1, len(eps) // 2)].tolist())
        m = data[tk]["epi"]
        tr_mask |= np.where(task_id == i)[0][np.isin(m, list(half))]
    te_mask = ~tr_mask

    p2, _ = fit_B2(W[tr_mask], T[tr_mask], R[tr_mask], init_params(W[tr_mask], T[tr_mask], R[tr_mask]))
    p1, _ = fit_B1(W[tr_mask], T[tr_mask], R[tr_mask])
    t0s, R0s = fit_B0(T[tr_mask], R[tr_mask])

    def eval_model(name, predict_fn):
        t_h, R_h = predict_fn(W[te_mask])
        et = np.linalg.norm(t_h - T[te_mask], axis=1)
        eR = np.array([rot_geodesic(R_h[i], R[te_mask][i]) for i in range(len(R_h))])
        res.setdefault("E12c_episode_disjoint", {})[name] = {
            "t_rmse_m": float(np.sqrt((et ** 2).mean())),
            "t_p95_m": float(np.percentile(et, 95)),
            "t_max_m": float(et.max()),
            "R_rmse_rad": float(np.sqrt((eR ** 2).mean())),
            "R_p95_rad": float(np.percentile(eR, 95)),
            "R_max_rad": float(eR.max()),
        }

    eval_model("B0_static", lambda w: (np.repeat(t0s[None, :], len(w), 0),
                                       np.repeat(R0s[None, :, :], len(w), 0)))
    eval_model("B1_rigid_mount", lambda w: predict_B2(w, np.concatenate([np.ones(3), p1[0:3], p1[3:6], p1[6:9], p1[9:12]])))
    eval_model("B2_gain_kinematic", lambda w: predict_B2(w, p2))

    # per-task B2 (calibrated on other tasks) for error attribution
    res["E12c_per_task_B2"] = {tk: {"t_rmse_m": loto[tk]["B2_t_rmse_m"], "R_rmse_rad": loto[tk]["B2_R_rmse_rad"]}
                               for tk in tasks}

    # ---------------- E12-d self-consistency residual ----------------------
    t_all, R_all = predict_B2(W, p2)
    rt = np.linalg.norm(t_all - T, axis=1)
    rR = np.array([rot_geodesic(R_all[i], R[i]) for i in range(len(R))])
    res["E12d_self_consistency"] = {
        "t_rmse_m": float(np.sqrt((rt ** 2).mean())),
        "t_p95_m": float(np.percentile(rt, 95)),
        "t_max_m": float(rt.max()),
        "R_rmse_rad": float(np.sqrt((rR ** 2).mean())),
        "R_p95_rad": float(np.percentile(rR, 95)),
        "R_max_rad": float(rR.max()),
        "gate_3sigma_translation_m": float(3 * np.sqrt((rt ** 2).mean())),
        "gate_3sigma_rotation_rad": float(3 * np.sqrt((rR ** 2).mean())),
    }

    # ---------------- global parameters of the calibration ------------------
    g, c, R_off, t_off, p_off = unpack_params(p2)
    res["calibration_B2_global"] = {
        "gains": {"roll_x": float(g[0]), "pitch_y": float(g[1]), "yaw_z": float(g[2])},
        "joint_offsets_rad": {"roll_x": float(c[0]), "pitch_y": float(c[1]), "yaw_z": float(c[2])},
        "lever_arm_p_off_m": [float(v) for v in p_off],
        "lever_arm_norm_m": float(np.linalg.norm(p_off)),
        "t_off_m": [float(v) for v in t_off],
        "R_off_rotvec_rad": [float(v) for v in log_so3(R_off)],
        "n_parameters": 15,
        "n_fit_frames": int(tr_mask.sum()),
    }
    res["aggregate"] = {
        "n_tasks": len(tasks),
        "all_tasks_lower_body_12_15_equals_waist": all(
            v["E12a_lower_body_12_15_equals_waist_max_abs_diff"] == 0.0 for v in res["tasks"].values()),
        "torso_z_constant_all_tasks": all(len(v["E12b_torso_z_unique"]) == 1 for v in res["tasks"].values()),
        "torso_z_values": sorted({v["E12b_torso_z_unique"][0] for v in res["tasks"].values()}),
        "max_waist_range_rad": {k: max(v["E12b_waist_range_rad"][k] for v in res["tasks"].values())
                                for k in ("yaw_z", "roll_x", "pitch_y")},
        "B0_t_rmse_m": res["E12c_episode_disjoint"]["B0_static"]["t_rmse_m"],
        "B1_t_rmse_m": res["E12c_episode_disjoint"]["B1_rigid_mount"]["t_rmse_m"],
        "B2_t_rmse_m": res["E12c_episode_disjoint"]["B2_gain_kinematic"]["t_rmse_m"],
        "B0_R_rmse_rad": res["E12c_episode_disjoint"]["B0_static"]["R_rmse_rad"],
        "B1_R_rmse_rad": res["E12c_episode_disjoint"]["B1_rigid_mount"]["R_rmse_rad"],
        "B2_R_rmse_rad": res["E12c_episode_disjoint"]["B2_gain_kinematic"]["R_rmse_rad"],
        "B2_LOTO_median_t_rmse_m": res["E12e_LOTO_median_t_rmse_m"],
        "B2_LOTO_max_t_rmse_m": res["E12e_LOTO_max_t_rmse_m"],
        "B2_LOTO_max_R_rmse_rad": res["E12e_LOTO_max_R_rmse_rad"],
    }
    OUT.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res["aggregate"], indent=2, ensure_ascii=False))
    print(json.dumps(res["calibration_B2_global"], indent=2, ensure_ascii=False))
    print(json.dumps(res["E12c_episode_disjoint"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
