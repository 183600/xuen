"""Real-data feasibility analysis of the round-16 components on official UniBot-V1 data.

All inputs are the official G1_Dex1_* LeRobot datasets (HF datasets-server),
which carry the same proprioception channels the challenge API exposes, plus
`state_d435` / `state_torso` / `waist_state_joint` (NOT exposed by the API).

E1  camera-pose recoverability from API-visible channels (waist) + fixed offsets
E2  metric stability of the base frame
E3  proprioceptive gesture codebook: separability + contact/stall width
E4  episode-boundary discontinuity (state-isolation requirement)
E5  commanded-vs-measured gripper gap (contact witness)
E6  cross-task consistency of the interaction-modality vocabulary

Output: exp/state_witness_results.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
DAT = EXP / "unibot_states"
OUT = EXP / "state_witness_results.json"

DT = 1.0 / 30.0


def rot_zyx(yaw: float, roll: float, pitch: float) -> np.ndarray:
    Rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
    Ry = np.array([[np.cos(pitch), 0, np.sin(pitch)], [0, 1, 0], [-np.sin(pitch), 0, np.cos(pitch)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(roll), -np.sin(roll)], [0, np.sin(roll), np.cos(roll)]])
    return Rz @ Ry @ Rx


def camera_pose_model(params: np.ndarray, waist: np.ndarray) -> np.ndarray:
    """p_cam = t + R(waist) @ off  ;  waist = (yaw, roll, pitch)."""
    t = params[:3]
    off = params[3:]
    out = np.empty((waist.shape[0], 3))
    for i, (yaw, roll, pitch) in enumerate(waist):
        out[i] = t + rot_zyx(yaw, roll, pitch) @ off
    return out


def episode_mask(contig: dict) -> tuple[np.ndarray, np.ndarray]:
    """Return (valid_index_mask, boundary_index_set) for a contiguous bundle."""
    fi = contig["frame_index"]
    ei = contig["episode_index"]
    valid = np.ones(len(fi), dtype=bool)
    bnd = []
    for i in range(1, len(fi)):
        if fi[i] <= fi[i - 1] or ei[i] != ei[i - 1]:
            bnd.append(i)
            valid[i] = False
            if i + 1 < len(fi):
                valid[i + 1] = False
    return valid, set(bnd)


def robust_scale(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return 1.0
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    return max(1.4826 * mad, 1e-6)


def gesture_labels(o: np.ndarray, dp: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, dict]:
    """Deterministic interaction-modality codebook from proprioception only.

    o   : gripper opening (Dex1: 5.5 open -> 0 closed), shape (T,)
    dp  : |delta ee position| per frame (m), shape (T,)
    """
    finite = o[np.isfinite(o)]
    o_open = np.percentile(finite, 99.0)
    o_closed = np.percentile(finite, 1.0)
    span = max(o_open - o_closed, 1e-3)
    w = (o - o_closed) / span                      # normalized width in [0,1]
    do = np.gradient(o) / DT
    thr = 0.15 * robust_scale(do[valid])
    v_thr = 0.004                                   # 4 mm / frame ~ 12 cm/s at 30 fps
    lab = np.array(["unknown"] * len(o), dtype=object)
    for i in range(len(o)):
        if not valid[i] or not np.isfinite(w[i]):
            continue
        moving = dp[i] > v_thr
        if do[i] < -thr:
            lab[i] = "close"
        elif do[i] > thr:
            lab[i] = "open"
        elif w[i] > 0.85:
            lab[i] = "reach" if moving else "idle_open"
        elif w[i] < 0.15:
            lab[i] = "carry" if moving else "hold_closed"
        else:
            lab[i] = "partial_motion" if moving else "partial_hold"
    stats = {"o_open": float(o_open), "o_closed": float(o_closed),
             "do_threshold_per_s": float(thr)}
    return lab, stats


def stall_widths(o: np.ndarray, lab: np.ndarray, valid: np.ndarray) -> list[float]:
    """Width (normalized) at which a closing motion stalls: vision-independent
    object-width measurement from the gripper encoder alone."""
    out = []
    T = len(o)
    i = 0
    while i < T:
        if lab[i] == "close":
            j = i
            while j + 1 < T and lab[j + 1] == "close":
                j += 1
            # stall = last width before the run ends (the gripper stopped shrinking)
            if j + 1 < T and valid[j + 1] and o[j] > 0:
                out.append(float(o[j]))
            i = j + 1
        else:
            i += 1
    return out


def main() -> None:
    res = {"source": "unitreerobotics/G1_Dex1_* on HF (datasets-server rows API), fetched 2026-11-04",
           "notes": "state_d435/state_torso/waist_state_joint are dataset-only channels; the challenge API exposes lower_body(15) which contains waist yaw/roll/pitch",
           "tasks": {}}

    all_stalls, all_labels, all_bound = [], {}, []
    for npz in sorted(DAT.glob("*.npz")):
        task = npz.stem
        z = np.load(npz, allow_pickle=True)

        def unpack(key: str) -> dict:
            arr = z[key]
            if arr.dtype == object:
                return arr.item()
            return {k: arr[k] for k in arr.files}

        C = unpack("contig")
        R = unpack("random")
        if len(C.get("frame_index", [])) == 0:
            print(f"{task}: skipped (empty contiguous bundle)")
            continue
        valid, bnd = episode_mask(C)

        # ---- E1 camera pose recoverability ------------------------------------
        waist = C["observation.state.waist_state_joint"]      # (yaw, roll, pitch)
        d435 = C["observation.state.state_d435"]               # (x,y,z,roll,pitch,yaw)
        d_off = {
            "roll_minus_waist_roll": d435[:, 3] - waist[:, 1],
            "pitch_minus_waist_pitch": d435[:, 4] - waist[:, 2],
            "yaw_minus_waist_yaw": d435[:, 5] - waist[:, 0],
        }
        ang = {k: {"mean": float(np.mean(v)), "std": float(np.std(v)), "max_abs": float(np.max(np.abs(v - np.mean(v))))}
               for k, v in d_off.items()}
        sol = least_squares(
            lambda p: (camera_pose_model(p, waist) - d435[:, :3]).ravel(),
            x0=np.concatenate([d435[:, :3].mean(axis=0), np.zeros(3)]),
            max_nfev=400)
        pos_res = sol.fun.reshape(-1, 3)
        pos_std = float(np.sqrt((pos_res ** 2).sum(axis=1).mean()))

        # ---- E2 base-frame metric stability -----------------------------------
        ee_l = C["observation.state.left_ee_pose_gripper_base"]
        ee_r = C["observation.state.right_ee_pose_gripper_base"]
        dp_l = np.zeros(len(ee_l)); dp_l[1:] = np.linalg.norm(np.diff(ee_l[:, :3], axis=0), axis=1)
        dp_r = np.zeros(len(ee_r)); dp_r[1:] = np.linalg.norm(np.diff(ee_r[:, :3], axis=0), axis=1)
        ee_span_l = float(np.ptp(ee_l[valid][:, :3], axis=0).max())

        # ---- E3 gesture codebook ------------------------------------------------
        lab_l, gstats = gesture_labels(C["observation.state.left_gripper"], dp_l, valid)
        lab_r, _ = gesture_labels(C["observation.state.right_gripper"], dp_r, valid)
        stalls_l = stall_widths(C["observation.state.left_gripper"], lab_l, valid)
        stalls_r = stall_widths(C["observation.state.right_gripper"], lab_r, valid)
        lab_counts = {}
        for v in lab_l:
            lab_counts[v] = lab_counts.get(v, 0) + 1
        n_lab = max(sum(lab_counts.values()), 1)
        all_labels[task] = {k: v / n_lab for k, v in lab_counts.items()}
        all_stalls += stalls_l + stalls_r

        # ---- E4 episode boundary discontinuity ---------------------------------
        bnd_jump = []
        for i in sorted(bnd):
            if i - 1 >= 0:
                bnd_jump.append(float(np.linalg.norm(ee_l[i, :3] - ee_l[i - 1, :3])))
        within = dp_l[1:][valid[1:] & valid[:-1]] if len(dp_l) > 1 else np.array([])
        # ---- E5 commanded vs measured gripper ----------------------------------
        cmd = C["action.left_gripper"]
        meas = C["observation.state.left_gripper"]
        gap = np.abs(cmd - meas)

        res["tasks"][task] = {
            "frames_contig": int(len(C["frame_index"])),
            "frames_random": int(len(R["frame_index"])),
            "n_episodes_in_contig": int(len(bnd) + 1),
            "E1_camera_angle_offset": ang,
            "E1_camera_translation_residual_m": {"rmse": pos_std,
                                                 "p95": float(np.percentile(np.linalg.norm(pos_res, axis=1), 95))},
            "E2_ee_span_m": ee_span_l,
            "E2_median_frame_step_m": float(np.median(within)) if within.size else None,
            "E3_gripper_range": gstats,
            "E3_label_mix_left": {k: round(v / n_lab, 4) for k, v in lab_counts.items()},
            "E3_stall_width_n": len(stalls_l) + len(stalls_r),
            "E3_stall_width_median": float(np.median(stalls_l + stalls_r)) if (stalls_l + stalls_r) else None,
            "E3_stall_width_quantiles": {q: float(np.quantile(stalls_l + stalls_r, q))
                                         for q in (0.1, 0.25, 0.5, 0.75, 0.9)} if (stalls_l + stalls_r) else None,
            "E4_boundary_ee_jump_m": {"n": len(bnd_jump),
                                      "median": float(np.median(bnd_jump)) if bnd_jump else None,
                                      "within_episode_p99_m": float(np.percentile(within, 99)) if within.size else None},
            "E5_cmd_meas_gripper_gap": {"mean": float(np.mean(gap)), "p95": float(np.percentile(gap, 95))},
        }
        all_bound.append(len(bnd_jump))

    # aggregate
    stalls = np.array(all_stalls) if all_stalls else np.array([])
    mix_keys = sorted({k for t in all_labels.values() for k in t})
    mean_mix = {k: float(np.mean([t.get(k, 0.0) for t in all_labels.values()])) for k in mix_keys}
    res["aggregate"] = {
        "n_tasks": len(res["tasks"]),
        "gesture_label_mix_mean_over_tasks": {k: round(v, 4) for k, v in mean_mix.items()},
        "gesture_label_mix_std_over_tasks": {k: round(float(np.std([t.get(k, 0.0) for t in all_labels.values()])), 4) for k in mix_keys},
        "stall_width_count": int(stalls.size),
        "stall_width_hist": {f"{lo:.2f}-{lo+0.5:.2f}": int(((stalls >= lo) & (stalls < lo + 0.5)).sum())
                             for lo in np.arange(0.0, 6.0, 0.5)} if stalls.size else {},
        "camera_translation_rmse_m_max_over_tasks": max(v["E1_camera_translation_residual_m"]["rmse"] for v in res["tasks"].values()),
        "camera_angle_offset_max_std_rad": max(max(abs(v["E1_camera_angle_offset"][k]["std"]) for k in v["E1_camera_angle_offset"])
                                               for v in res["tasks"].values()),
    }
    OUT.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res["aggregate"], indent=2, ensure_ascii=False))
    t0 = list(res["tasks"].values())[0]
    print(json.dumps(t0, indent=2, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()
