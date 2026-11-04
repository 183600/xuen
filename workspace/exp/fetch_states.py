"""Fetch real UniBot-V1 state/action channels from the official HF dataset.

Source: datasets-server rows API for unitreerobotics/G1_Dex1_* datasets
(LeRobot v3, 30 fps, rectified head stereo + wrist color cameras).
No depth stream exists in the dataset; the challenge API likewise exposes RGB only.

Output: exp/unibot_states/<TASK>.npz  (one file per task, incremental)
"""
from __future__ import annotations

import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROWS = "https://datasets-server.huggingface.co/rows?dataset={ds}&config=default&split=train&offset={off}&length=100"
INFO = "https://datasets-server.huggingface.co/info?dataset={ds}"
EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
OUTDIR = EXP / "unibot_states"
TASKS = [
    "G1_Dex1_HangCup", "G1_Dex1_PlugInEthernet", "G1_Dex1_StackBowls", "G1_Dex1_FoldTowel",
    "G1_Dex1_Unlock", "G1_Dex1_ArrangeTestTubes", "G1_Dex1_ToolboxStorage", "G1_Dex1_SpellRobot",
    "G1_Dex1_ConveyorSorting", "G1_Dex1_ZipUp", "G1_Dex1_PackDoll", "G1_Dex1_OrganizeTools",
]
K_BATCH = 10
CONTIG = 8
FIELDS = [
    "observation.state.left_gripper", "observation.state.right_gripper",
    "observation.state.left_arm", "observation.state.right_arm",
    "observation.state.lower_body",
    "observation.state.left_ee_pose_gripper_base", "observation.state.right_ee_pose_gripper_base",
    "observation.state.state_torso", "observation.state.state_d435",
    "observation.state.waist_state_joint", "observation.state.left_leg",
    "action.left_gripper", "action.right_gripper", "action.gripper_controls",
    "action.left_ee_pose_gripper_base", "action.right_ee_pose_gripper_base",
    "episode_index", "frame_index", "task_index",
]


def get(url: str, tries: int = 6) -> dict | None:
    for t in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "unibot-research/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1.5 * (t + 1))
    return None


def fetch_batch(ds: str, off: int) -> list[dict] | None:
    d = get(ROWS.format(ds=f"unitreerobotics/{ds}", off=off))
    if not d or "rows" not in d:
        return None
    return [row["row"] for row in d["rows"]]


def pack(rows: list[dict]) -> dict:
    out = {}
    for f in FIELDS:
        vals = [r.get(f) for r in rows]
        if vals and isinstance(vals[0], (list, tuple)):
            out[f] = np.asarray(vals, dtype=np.float64)
        else:
            out[f] = np.asarray([np.nan if v is None else float(v) for v in vals], dtype=np.float64)
    return out


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261104)
    for ds in TASKS:
        target = OUTDIR / f"{ds}.npz"
        if target.exists():
            print(f"{ds}: cached", flush=True)
            continue
        info = get(INFO.format(ds=f"unitreerobotics/{ds}"))
        total = None
        try:
            total = int(info["dataset_info"]["default"]["num_rows"]) if info and "dataset_info" in info else None
        except Exception:
            total = None
        if total is None:
            probe = get(ROWS.format(ds=f"unitreerobotics/{ds}", off=0))
            total = int(probe.get("num_rows_total", 200_000)) if probe else 200_000
        offsets = [int(x) for x in rng.integers(0, max(total - 120, 1), size=K_BATCH)]
        offsets += [100 * i for i in range(CONTIG)]
        got = {}
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(fetch_batch, ds, o): i for i, o in enumerate(offsets)}
            for fut, i in futs.items():
                r = fut.result()
                if r:
                    got[i] = r
        random_rows, contig_rows = [], []
        for i in range(len(offsets)):
            if i not in got:
                continue
            (random_rows if i < K_BATCH else contig_rows).extend(got[i])
        if not random_rows:
            print(f"{ds}: FAILED (no rows)", flush=True)
            continue
        np.savez_compressed(target, random=pack(random_rows), contig=pack(contig_rows))
        print(f"{ds}: total_rows={total} random={len(random_rows)} contig={len(contig_rows)}", flush=True)


if __name__ == "__main__":
    main()
