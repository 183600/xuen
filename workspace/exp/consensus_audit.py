"""Reproduce the CONSENSUS-VLA data audit.

Usage:
  python exp/consensus_audit.py \
      --urdf /path/g1_body29_hand14.urdf \
      --parquet /path/G1_Dex1_HangCup.parquet /path/G1_Dex1_Unlock.parquet \
      --out exp/consensus_audit_results.json
"""
import argparse
import json
import xml.etree.ElementTree as ET

import numpy as np
import pyarrow.parquet as pq
from scipy.spatial.transform import Rotation as R
from scipy.stats import rankdata

LN = [
    "left_shoulder_pitch_joint", "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint", "left_elbow_joint",
    "left_wrist_roll_joint", "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
]
WN = ["waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint"]
TOOL_LINK = "left_hand_palm_link"


def parse_urdf(path):
    root = ET.parse(path).getroot()
    joints = {j.get("name"): j for j in root.findall("joint")}
    parents = {j.find("child").get("link"): j for j in root.findall("joint")}
    return joints, parents


def origin_t(j):
    o = j.find("origin")
    xyz = np.array([float(v) for v in (o.get("xyz", "0 0 0")).split()]) if o is not None else np.zeros(3)
    rpy = np.array([float(v) for v in (o.get("rpy", "0 0 0")).split()]) if o is not None else np.zeros(3)
    t = np.eye(4)
    t[:3, :3] = R.from_euler("xyz", rpy).as_matrix()
    t[:3, 3] = xyz
    return t


def axis_t(j, q):
    a = j.find("axis")
    ax = np.array([float(v) for v in (a.get("xyz", "0 0 1")).split()]) if a is not None else np.array([0.0, 0.0, 1.0])
    t = np.eye(4)
    t[:3, :3] = R.from_rotvec(ax / np.linalg.norm(ax) * q).as_matrix()
    return t


def fk(parents, link, qmap):
    chain = []
    cur = link
    while cur in parents:
        j = parents[cur]
        chain.append(j)
        cur = j.find("parent").get("link")
    t = np.eye(4)
    for j in reversed(chain):
        t = t @ origin_t(j)
        if j.get("type") == "revolute":
            t = t @ axis_t(j, qmap.get(j.get("name"), 0.0))
    return t


def audit(path, name, joints, parents, rng):
    cols = [
        "observation.state.left_arm", "observation.state.left_ee_pose_gripper_base",
        "observation.state.waist_state_joint", "action.left_arm", "episode_index",
    ]
    df = pq.read_table(path, columns=cols).to_pandas()
    q = np.stack(df["observation.state.left_arm"].values)
    w = np.stack(df["observation.state.waist_state_joint"].values)
    ee = np.stack(df["observation.state.left_ee_pose_gripper_base"].values)
    idx = rng.choice(len(df), min(4000, len(df)), replace=False)

    tools = []
    for k in idx:
        qm = {WN[i]: w[k, i] for i in range(3)}
        qm.update({LN[i]: q[k, i] for i in range(7)})
        t = fk(parents, TOOL_LINK, qm)
        rm, pm = t[:3, :3], t[:3, 3]
        rs = R.from_euler("xyz", ee[k, 3:]).as_matrix()
        tools.append(np.r_[rm.T @ (ee[k, :3] - pm), R.from_matrix(rm.T @ rs).as_rotvec()])
    tools = np.array(tools)

    a = np.stack(df["action.left_arm"].values)
    lead = []
    for lag in range(7):
        s = df.groupby("episode_index")["observation.state.left_arm"].shift(-lag)
        m = s.notna().values
        lead.append(float(np.abs(a[m] - np.stack(s.dropna().values)).mean()))

    outside = near = total = 0
    for i, n in enumerate(LN):
        lim = joints[n].find("limit")
        lo, hi = float(lim.get("lower")), float(lim.get("upper"))
        x = q[:, i]
        outside += int(np.sum((x < lo) | (x > hi)))
        near += int(np.sum((x < lo + 0.02 * (hi - lo)) | (x > hi - 0.02 * (hi - lo))))
        total += int(len(x))

    return {
        "dataset": name,
        "frames": int(len(df)),
        "episodes_chunk0": int(df["episode_index"].nunique()),
        "fps": float(1.0 / np.median(np.diff(pq.read_table(path, columns=["timestamp"]).to_pandas()["timestamp"].values))),
        "tool_offset_mm_mean": (tools[:, :3].mean(0) * 1000).round(3).tolist(),
        "tool_offset_mm_std": (tools[:, :3].std(0) * 1000).round(3).tolist(),
        "tool_rot_deg_mean": np.degrees(tools[:, 3:].mean(0)).round(5).tolist(),
        "action_lead_error_by_lag": [round(x, 5) for x in lead],
        "action_lead_best": int(np.argmin(lead)),
        "joint_outside_limit": outside,
        "joint_within_2pct_limit": near,
        "joint_values_checked": total,
    }


def monte_carlo(seed=0, n=200000):
    rng = np.random.default_rng(seed)
    u, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    v, _ = np.linalg.qr(rng.normal(size=(7, 7)))
    jac = u @ np.diag([0.5, 0.3, 0.2]) @ v[:3, :]
    sig_q, sig_x = 0.01, 0.002
    rows = []
    for rho in [0.0, 0.25, 0.5, 0.75, 1.0]:
        eq = rng.normal(0, sig_q, (n, 8, 7))
        ex = rng.normal(0, sig_x, (n, 8, 3))
        esh = rng.normal(0, sig_q, (n, 8, 7))
        esh_ee = esh @ jac.T
        eq = np.sqrt(1 - rho) * eq + np.sqrt(rho) * esh
        ex = np.sqrt(1 - rho) * ex + np.sqrt(rho) * esh_ee
        task = np.linalg.norm(eq @ jac.T, axis=2)
        cons = np.linalg.norm(eq @ jac.T - ex, axis=2)
        thr = np.quantile(task, 0.8)
        bad0 = task[:, 0] > np.quantile(task[:, 0], 0.8)
        r = rankdata(cons[:, 0])
        n1 = int(bad0.sum()); n0 = int(len(bad0) - n1)
        row = {"rho": rho, "auroc_consistency": round(float((r[bad0].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)), 4)}
        for k in [1, 4, 8]:
            if k == 1:
                chosen = task[:, 0]
            else:
                sel = np.argmin(cons[:, :k], axis=1)
                chosen = task[np.arange(n), sel]
            row[f"bad_rate_K{k}"] = round(float((chosen > thr).mean()), 4)
            row[f"mean_err_mm_K{k}"] = round(float(chosen.mean() * 1000), 3)
        row["oracle_mean_err_mm_K8"] = round(float(task[:, :8].min(axis=1).mean() * 1000), 3)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urdf", required=True)
    ap.add_argument("--parquet", nargs="+", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    joints, parents = parse_urdf(args.urdf)
    rng = np.random.default_rng(0)
    result = {
        "audit": [audit(p, p.split("/")[-1], joints, parents, rng) for p in args.parquet],
        "monte_carlo": monte_carlo(),
    }
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
