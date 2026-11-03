"""MOBEX audit: base-motion content of every public G1_Dex1 dataset.

Reads the first LeRobot data parquet of each dataset (states/actions only) and
measures how much *mobile* manipulation signal the released demonstrations
actually contain, plus the geometric cost of a moving base (yaw-slip).

Outputs: exp/mobex_audit_results.json
"""
import json
import os
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pyarrow.parquet as pq

CACHE = "/tmp/opencode/pq"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mobex_audit_results.json")
EPS = 0.02
FPS = 30.0

COLS = [
    "action.pivot",
    "action.base_command",
    "observation.state.lower_body",
    "observation.state.left_ee_pose_gripper_base",
    "observation.state.right_ee_pose_gripper_base",
    "observation.state.waist_state_joint",
    "episode_index",
    "frame_index",
]


def flat(col):
    """Flatten a (possibly ragged) Arrow list column to (n*dim,) float64."""
    arr = col.combine_chunks()
    if hasattr(arr, "flatten"):
        try:
            return np.asarray(arr.flatten().to_pylist(), dtype=np.float64)
        except Exception:
            pass
    vals = arr.to_pylist()
    return np.asarray([v for row in vals for v in (row if isinstance(row, (list, tuple)) else [row])],
                      dtype=np.float64)


def first_data_file(repo, files):
    cand = sorted(f for f in files if f.startswith("data/chunk-000/") and f.endswith(".parquet"))
    return cand[0] if cand else None


def download(repo, path, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return True
    url = f"https://huggingface.co/datasets/{repo}/resolve/main/{path}"
    try:
        subprocess.run(["curl", "-sL", "--retry", "2", "-o", dest, url], check=True, timeout=600)
        return os.path.getsize(dest) > 1024
    except Exception:
        return False


def audit(repo):
    name = repo.split("/")[-1]
    out = {"repo": repo, "ok": False}
    try:
        with urllib.request.urlopen(f"https://huggingface.co/api/datasets/{repo}", timeout=60) as r:
            meta = json.load(r)
    except Exception as e:
        out["err"] = f"api:{e}"
        return out
    files = [s["rfilename"] for s in meta.get("siblings", [])]
    path = first_data_file(repo, files)
    out["total_episodes"] = meta.get("cardData", {}).get("total_episodes")
    out["files"] = len(files)
    if path is None:
        out["err"] = "no-data-file"
        return out
    os.makedirs(CACHE, exist_ok=True)
    dest = os.path.join(CACHE, f"{name}.parquet")
    if not download(repo, path, dest):
        out["err"] = "download"
        return out
    try:
        pf = pq.ParquetFile(dest)
        have = set(pf.schema_arrow.names)
        cols = [c for c in COLS if c in have]
        tb = pf.read(columns=cols)
    except Exception as e:
        out["err"] = f"read:{e}"
        return out

    d = {c: flat(tb.column(c)) for c in cols}
    n = len(d[cols[0]])
    out.update({"ok": True, "sampled_rows": n, "file": path})

    piv = d.get("action.pivot")
    if piv is not None and piv.size >= 7 * n:
        piv = piv.reshape(n, -1)[:, :7]
        vx, vy, wz = piv[:, 0], piv[:, 1], piv[:, 2]
        height = piv[:, 6]
        out["pivot_vx_absmean"] = float(np.abs(vx).mean())
        out["pivot_vy_absmean"] = float(np.abs(vy).mean())
        out["pivot_wz_absmean"] = float(np.abs(wz).mean())
        out["pivot_wz_absmax"] = float(np.abs(wz).max())
        out["frac_frame_vx"] = float((np.abs(vx) > EPS).mean())
        out["frac_frame_vy"] = float((np.abs(vy) > EPS).mean())
        out["frac_frame_wz"] = float((np.abs(wz) > EPS).mean())
        out["height_cmd_mean"] = float(height.mean())
        out["height_cmd_std"] = float(height.std())
        ep = d["episode_index"]
        mobile_ep = set()
        for e in np.unique(ep):
            m = ep == e
            if (np.abs(vx[m]) > EPS).any() or (np.abs(vy[m]) > EPS).any() or (np.abs(wz[m]) > EPS).any():
                mobile_ep.add(int(e))
        out["mobile_episodes"] = len(mobile_ep)
        out["n_episodes_sampled"] = int(len(np.unique(ep)))
        out["frac_mobile_episodes"] = len(mobile_ep) / max(1, len(np.unique(ep)))
        # yaw-slip: lateral world-frame error if a base-frame EE plan is kept while base yaws
        # lever arm from the base-frame EE xy; dtheta per frame = |wz| / fps
        lee = d.get("observation.state.left_ee_pose_gripper_base")
        r = None
        if lee is not None and lee.size >= 3 * n:
            lee = lee.reshape(n, -1)
            r = np.linalg.norm(lee[:, :2], axis=1)
            out["ee_r_mean"] = float(r.mean())
            out["ee_r_p95"] = float(np.percentile(r, 95))
        if r is not None:
            dtheta = np.abs(wz) / FPS
            slip_step = r * dtheta
            out["slip_step_mean_mm"] = float(slip_step.mean() * 1000)
            out["slip_step_p95_mm"] = float(np.percentile(slip_step, 95) * 1000)
            out["slip_chunk30_mean_mm"] = float(slip_step[:30].sum() * 1000)
            out["slip_episode_sum_mm"] = float(slip_step.sum() * 1000)
    bc = d.get("action.base_command")
    if bc is not None and bc.size >= 3 * n:
        bc = bc.reshape(n, -1)
        out["basecmd_wz_absmean"] = float(np.abs(bc[:, 2]).mean())
        out["frac_frame_basecmd_wz"] = float((np.abs(bc[:, 2]) > EPS).mean())
    lb = d.get("observation.state.lower_body")
    if lb is not None and lb.size >= 15 * n:
        lb = lb.reshape(n, -1)
        waist = lb[:, 12:15]
        hipyaw = np.concatenate([lb[:, 2:3], lb[:, 8:9]], axis=1)
        out["waist_std_max"] = float(waist.std(axis=0).max())
        out["waist_range_yaw_deg"] = float(np.degrees(waist[:, 0].max() - waist[:, 0].min()))
        out["hipyaw_std_max"] = float(hipyaw.std(axis=0).max())
        out["knee_mean"] = float(lb[:, 3].mean())
    return out


def main():
    ids = [x["id"] for x in json.load(open("/tmp/opencode/hf_list.json"))]
    repos = [i for i in ids if i.split("/")[-1].startswith("G1_Dex1")]
    res = {}
    with ThreadPoolExecutor(8) as ex:
        for r in ex.map(audit, repos):
            res[r["repo"].split("/")[-1]] = r
            print(("OK " if r.get("ok") else "ERR"), r["repo"].split("/")[-1],
                  r.get("sampled_rows"), r.get("frac_frame_wz"), r.get("frac_frame_vx"), flush=True)
    json.dump(res, open(OUT, "w"), indent=1)
    ok = [v for v in res.values() if v.get("ok")]
    print(f"\naudited {len(ok)}/{len(res)} datasets")
    print("mobile datasets (any episode with |vx| or |vy| or |wz| > 0.02):",
          sum(1 for v in ok if v.get("frac_mobile_episodes", 0) > 0))
    print("datasets with nonzero yaw command at all:",
          sum(1 for v in ok if v.get("frac_frame_wz", 0) > 0))


if __name__ == "__main__":
    main()
