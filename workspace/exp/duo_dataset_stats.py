"""Dataset-grounded bimanual structure statistics for UniBot-V1 challenge datasets.

Source: HF datasets-server rows API for unitreerobotics/G1_Dex1_<Task> (LeRobot v3.0).
Retrieved: 2026-11-02 (UTC).

Purpose (evidence for the round-16 dual-arm transaction layer):
  1. Which of the 32 challenge tasks are structurally bimanual?
  2. How often do the two arms act in disjoint temporal windows
     ("one arm holds while the other manipulates")?
  3. Is there a systematic lead-lag between arms (handover-like structure)?

Everything here is measured from the official demonstration actions:
  action.left_arm / action.right_arm : 7 joint targets
  action.left_gripper / action.right_gripper : Dex1 opening, 5.5 (open) -> 0 (closed)
"""

import json
import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

API = "https://datasets-server.huggingface.co/rows"
PAGE = 100
PAGES_PER_DATASET = 30  # 3000 frames ~= 4-10 episodes for most tasks
ACTIVE_EPS = 0.002       # rad / frame  (~0.06 rad/s at 30 fps)
GRIP_CLOSED = 1.0        # Dex1 opening <= 1.0 out of 5.5 -> closed
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "duo_rows_cache")

DATASETS = [
    "HangCup",
    "Unlock",
    "DisconnectEthernet",
    "PlugInEthernet",
    "PlugCharger",
    "PourOutMedicine",
    "SyringeWaterTransfer",
    "RemovePinnedNote",
    "FoldTowel",
    "PlacePhotoFrame",
    "OrganizeStationery",
    "FruitSorting",
    "OrganizeTools",
    "ToolboxStorage",
    "PackDoll",
    "StackBowls",
    "SpellRobot",
    "PickOutBatteries",
    "StoreEarphones",
    "ArrangeTestTubes",
]


def fetch_page(ds, offset):
    key = f"{ds}_{offset}"
    path = os.path.join(CACHE, key + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    q = urllib.parse.urlencode(
        {
            "dataset": f"unitreerobotics/G1_Dex1_{ds}",
            "config": "default",
            "split": "train",
            "offset": offset,
            "length": PAGE,
        }
    )
    with urllib.request.urlopen(f"{API}?{q}", timeout=90) as r:
        data = json.load(r)
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return data


def collect(ds):
    offsets = [i * PAGE for i in range(PAGES_PER_DATASET)]
    rows = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for data in ex.map(lambda o: fetch_page(ds, o), offsets):
            for item in data.get("rows", []):
                rows.append(item["row"])
    rows.sort(key=lambda r: (r["episode_index"], r["frame_index"]))
    return rows


def stats_for(rows):
    if len(rows) < 20:
        return None
    L = np.array([r["action.left_arm"] for r in rows], dtype=np.float64)
    R = np.array([r["action.right_arm"] for r in rows], dtype=np.float64)
    gl = np.array([r["action.left_gripper"] for r in rows], dtype=np.float64)
    gr = np.array([r["action.right_gripper"] for r in rows], dtype=np.float64)
    ep = np.array([r["episode_index"] for r in rows])

    dL = np.abs(np.diff(L, axis=0)).sum(axis=1)
    dR = np.abs(np.diff(R, axis=0)).sum(axis=1)
    # cut episode boundaries: a discontinuity across episodes is not motion
    same = ep[1:] == ep[:-1]
    dL[~same] = 0.0
    dR[~same] = 0.0

    actL = dL > ACTIVE_EPS
    actR = dR > ACTIVE_EPS
    closedL = gl[1:] <= GRIP_CLOSED
    closedR = gr[1:] <= GRIP_CLOSED

    both = float(np.mean(actL & actR))
    onlyL = float(np.mean(actL & ~actR))
    onlyR = float(np.mean(~actL & actR))
    none = float(np.mean(~actL & ~actR))
    one = onlyL + onlyR

    # "hold-and-act": an arm keeps its gripper closed while it is (almost) still
    # and the other arm is actively moving -> the other arm is doing the work.
    holdL_actR = float(np.mean(closedL & ~actL & actR))
    holdR_actL = float(np.mean(closedR & ~actR & actL))
    hold_act = holdL_actR + holdR_actL

    # any closed gripper at all (grasp exists in the episode)
    graspL = float(np.mean(closedL))
    graspR = float(np.mean(closedR))

    # lead-lag between the two activity signals (frames)
    a = actL.astype(np.float64) - actL.mean()
    b = actR.astype(np.float64) - actR.mean()
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    maxlag = 20
    cors = []
    for lag in range(-maxlag, maxlag + 1):
        if lag < 0:
            x, y = a[-lag:], b[: n + lag]
        elif lag > 0:
            x, y = a[: n - lag], b[lag:]
        else:
            x, y = a, b
        denom = (np.linalg.norm(x) * np.linalg.norm(y)) or 1e-9
        cors.append(float(np.dot(x, y) / denom))
    cors = np.array(cors)
    lag = int(np.argmax(cors) - maxlag)

    return {
        "frames": int(len(rows)),
        "episodes": int(len(set(ep.tolist()))),
        "frac_both_active": both,
        "frac_one_active": one,
        "frac_none_active": none,
        "frac_left_only": onlyL,
        "frac_right_only": onlyR,
        "frac_hold_and_act": hold_act,
        "frac_holdL_actR": holdL_actR,
        "frac_holdR_actL": holdR_actL,
        "frac_gripper_closed_L": graspL,
        "frac_gripper_closed_R": graspR,
        "lead_lag_frames": lag,
        "max_activity_corr": float(cors.max()),
        "mean_arm_activity_L": float(np.mean(dL)),
        "mean_arm_activity_R": float(np.mean(dR)),
        "asym_activity_ratio": float(
            (np.mean(dL) + 1e-9) / (np.mean(dR) + 1e-9)
        ),
    }


def main():
    out = {}
    for ds in DATASETS:
        try:
            rows = collect(ds)
            s = stats_for(rows)
        except Exception as exc:  # network hiccup / missing config
            s = {"error": repr(exc)}
        out[ds] = s
        print(ds, json.dumps(s, ensure_ascii=False))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "duo_dataset_stats.json"), "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
