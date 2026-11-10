"""Round 41 / v18 audit: whole-body and end-effector-pose content of the
public G1_Dex1 v3.0 datasets.

This is NOT a benchmark result and NOT a robot experiment.  It only measures,
on released demonstrations, three quantities that the v18 design depends on:

  A. how much the mobile base is actually commanded (action.base_command),
  B. how much the waist moves (observation.state.waist_state_joint),
  C. the command->realized end-effector pose residual
         r_t = action.*_ee_pose_gripper_base(t)
             - observation.state.*_ee_pose_gripper_base(t+1)
     decomposed into a constant offset b_0 and a residual after removing it.
  D. joint-command tracking (action.*_arm(t) vs observation.state.*_arm(t+1)).
  E. how much of the EE delta variance is explained by arm joints alone vs
     arm+waist (linear least squares R^2).

Cache the first data parquet per repo under CACHE (downloaded once with curl).
Outputs exp/wbc_pose_audit_results.json.

Run (needs numpy + pyarrow):
    PYTHONPATH=<site-packages-with-pyarrow> python exp/wbc_pose_audit.py
"""
import json
import os
import subprocess
import urllib.request

import numpy as np
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wbc_pose_audit_results.json")
CACHE = os.environ.get("WBC_AUDIT_CACHE", "/tmp/opencode/pq")
REPOS = [
    "G1_Dex1_ZipUp",
    "G1_Dex1_Stack_Block",
    "G1_Dex1_Unlock",
    "G1_Dex1_HangCup",
]
COLS = [
    "observation.state.left_arm",
    "observation.state.right_arm",
    "observation.state.waist_state_joint",
    "observation.state.left_ee_pose_gripper_base",
    "observation.state.right_ee_pose_gripper_base",
    "action.left_arm",
    "action.right_arm",
    "action.left_ee_pose_gripper_base",
    "action.right_ee_pose_gripper_base",
    "action.base_command",
    "action.pivot",
    "episode_index",
    "frame_index",
]
EPS = 1e-3


def _download(repo, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    url = (f"https://huggingface.co/datasets/unitreerobotics/{repo}"
           "/resolve/main/data/chunk-000/file-000.parquet")
    try:
        subprocess.run(["curl", "-sL", "--retry", "2", "-o", dest, url],
                       check=True, timeout=600)
        return os.path.getsize(dest) > 1024
    except Exception:
        try:
            urllib.request.urlretrieve(url, dest)
            return os.path.getsize(dest) > 1024
        except Exception:
            return False


def _load(tb, col):
    a = tb.column(col).combine_chunks()
    if hasattr(a, "flatten"):
        v = np.asarray(a.flatten().to_pylist(), dtype=np.float64)
        return v.reshape(len(a), -1)
    return np.asarray(a.to_pylist(), dtype=np.float64).reshape(-1, 1)


def _r2(X, y):
    X = np.column_stack([np.ones(len(X)), X])
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean(0)) ** 2).sum())
    return 1.0 - ss_res / ss_tot


def audit(repo):
    dest = os.path.join(CACHE, repo + ".parquet")
    out = {"repo": repo, "ok": False}
    if not _download(repo, dest):
        out["err"] = "download"
        return out
    pf = pq.ParquetFile(dest)
    have = set(pf.schema_arrow.names)
    cols = [c for c in COLS if c in have]
    if len(cols) != len(COLS):
        out["err"] = "missing-columns:" + ",".join(sorted(set(COLS) - have))
        return out
    tb = pf.read(columns=cols)
    d = {c: _load(tb, c) for c in cols}
    ep = d["episode_index"][:, 0].astype(int)
    fr = d["frame_index"][:, 0].astype(int)
    m = (ep[:-1] == ep[1:]) & (fr[:-1] + 1 == fr[1:])  # consecutive, same episode

    out.update({"ok": True, "rows": int(len(ep)),
                "episodes": int(len(np.unique(ep))),
                "consecutive_pairs": int(m.sum())})

    bc = d["action.base_command"]
    out["base_nonzero_frac"] = float(
        ((np.abs(bc[:, 0]) > EPS) | (np.abs(bc[:, 1]) > EPS)
         | (np.abs(bc[:, 2]) > EPS)).mean())
    out["base_vx_absmean"] = float(np.abs(bc[:, 0]).mean())
    out["base_vy_absmean"] = float(np.abs(bc[:, 1]).mean())
    out["base_wz_absmean"] = float(np.abs(bc[:, 2]).mean())

    piv = d["action.pivot"]
    out["pivot_xyz_nonzero_frac"] = float(
        ((np.abs(piv[:, 0]) > EPS) | (np.abs(piv[:, 1]) > EPS)
         | (np.abs(piv[:, 2]) > EPS)).mean())
    out["pivot_mean"] = np.round(piv.mean(0), 5).tolist()
    out["pivot_std"] = np.round(piv.std(0), 5).tolist()

    waist = d["observation.state.waist_state_joint"]
    out["waist_range_deg"] = np.round(
        np.degrees(waist.max(0) - waist.min(0)), 3).tolist()
    out["waist_std_deg"] = np.round(np.degrees(waist.std(0)), 3).tolist()

    for side in ("left", "right"):
        obs = d[f"observation.state.{side}_ee_pose_gripper_base"]
        act = d[f"action.{side}_ee_pose_gripper_base"]
        r = (act[:-1, :3] - obs[1:, :3])[m]
        out[f"{side}_ee_zoff_mm"] = float(r[:, 2].mean() * 1000)
        out[f"{side}_ee_xyoff_mm"] = np.round(r[:, :2].mean(0) * 1000, 3).tolist()
        out[f"{side}_ee_resid_after_offset_mm"] = float(
            np.linalg.norm(r - r.mean(0), axis=1).mean() * 1000)
        out[f"{side}_ee_resid_p95_mm"] = float(
            np.percentile(np.linalg.norm(r - r.mean(0), axis=1), 95) * 1000)
        jerr = np.abs(
            (d[f"action.{side}_arm"][:-1] - d[f"observation.state.{side}_arm"][1:])[m])
        out[f"{side}_joint_err_deg"] = float(np.degrees(jerr.mean()))
        out[f"{side}_joint_err_p95_deg"] = float(
            np.degrees(np.percentile(jerr, 95)))

        # lag scan: action[t] vs observation[t+k]; minimum reveals the target horizon
        n = len(ep)
        lag_err = []
        for k in range(0, 11):
            mk = (ep[:n - k] == ep[k:]) & (fr[:n - k] + k == fr[k:])
            lag_err.append(float(np.linalg.norm(
                act[:n - k, :3] - obs[k:, :3], axis=1)[mk].mean() * 1000))
        out[f"{side}_lag_err_mm_k0to10"] = np.round(lag_err, 3).tolist()
        out[f"{side}_best_lag_frames"] = int(np.argmin(lag_err))

        # E6: residual after removing the constant offset grows with motion speed
        speed = np.linalg.norm(obs[1:, :3] - obs[:-1, :3], axis=1)
        res_off = np.linalg.norm((act[:-1, :3] - obs[1:, :3]) - r.mean(0), axis=1)
        slow = m & (speed < 0.001)
        fast = m & (speed > np.percentile(speed[m], 80))
        out[f"{side}_resid_slow_mm"] = float(res_off[slow].mean() * 1000) if slow.any() else None
        out[f"{side}_resid_fast_mm"] = float(res_off[fast].mean() * 1000) if fast.any() else None

    # E7: variance of left-EE position delta explained by arm joints vs arm+waist
    oa = np.concatenate([d["observation.state.left_arm"],
                         d["observation.state.right_arm"]], axis=1)
    ee = d["observation.state.left_ee_pose_gripper_base"]
    y = (ee[1:, :3] - ee[:-1, :3])[m]
    xa = (oa[1:] - oa[:-1])[m]
    xw = (waist[1:] - waist[:-1])[m]
    out["R2_arm"] = float(_r2(xa, y))
    out["R2_arm_waist"] = float(_r2(np.column_stack([xa, xw]), y))
    return out


def main():
    res = {}
    for repo in REPOS:
        r = audit(repo)
        res[repo] = r
        if r.get("ok"):
            print(f"OK  {repo:28s} rows={r['rows']:7d} ep={r['episodes']:4d} "
                  f"base={r['base_nonzero_frac']*100:.3f}% "
                  f"zoff L/R={r['left_ee_zoff_mm']:.2f}/{r['right_ee_zoff_mm']:.2f}mm")
        else:
            print(f"ERR {repo:28s} {r.get('err')}")
    ok = [v for v in res.values() if v.get("ok")]
    agg = {}
    if ok:
        agg = {
            "tasks": len(ok),
            "episodes": int(sum(v["episodes"] for v in ok)),
            "rows": int(sum(v["rows"] for v in ok)),
            "base_nonzero_frac_mean": float(np.mean([v["base_nonzero_frac"] for v in ok])),
            "left_ee_zoff_mm_mean": float(np.mean([v["left_ee_zoff_mm"] for v in ok])),
            "right_ee_zoff_mm_mean": float(np.mean([v["right_ee_zoff_mm"] for v in ok])),
            "left_ee_resid_after_offset_mm_mean": float(np.mean(
                [v["left_ee_resid_after_offset_mm"] for v in ok])),
            "right_ee_resid_after_offset_mm_mean": float(np.mean(
                [v["right_ee_resid_after_offset_mm"] for v in ok])),
            "left_joint_err_deg_mean": float(np.mean([v["left_joint_err_deg"] for v in ok])),
            "right_joint_err_deg_mean": float(np.mean([v["right_joint_err_deg"] for v in ok])),
            "R2_arm_mean": float(np.mean([v["R2_arm"] for v in ok])),
            "R2_arm_waist_mean": float(np.mean([v["R2_arm_waist"] for v in ok])),
        }
    json.dump({"tasks": res, "aggregate": agg}, open(OUT, "w"),
              indent=1, ensure_ascii=False)
    print("\naggregate:", json.dumps(agg, ensure_ascii=False, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
