"""Loader for cached UniBot-V1 demonstration rows (real HF data).

Source rows were fetched on 2026-11-03 from the HuggingFace datasets-server
``rows`` API for ``unitreerobotics/G1_Dex1_<Task>`` (LeRobot v3.0) and cached
under ``exp/duo_rows_cache`` by ``exp/fetch_rows.py``.  We only touch the local
cache: no network access is needed for round 29's experiments.

What we keep per frame (real values, no simulation):
  observation.state.left_ee_pose_gripper_base   (6)  xyz + rpy, base frame
  observation.state.right_ee_pose_gripper_base  (6)
  observation.state.left_gripper / right_gripper (1)  Dex1 opening (5.5 open)
  action.left_arm / action.right_arm            (7)  joint targets
  episode_index / frame_index / timestamp
"""

import glob
import json
import os

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "duo_rows_cache")

GRIP_CLOSED = 1.0  # Dex1 opening <= 1.0 out of 5.5 -> closed (same threshold as exp/duo_dataset_stats.py)


def available_tasks():
    tasks = {}
    for path in glob.glob(os.path.join(CACHE, "*.json")):
        base = os.path.basename(path)[:-5]
        task, offset = base.rsplit("_", 1)
        tasks.setdefault(task, []).append(int(offset))
    return {t: sorted(v) for t, v in tasks.items()}


def _cell(row, key, default=None):
    value = row.get(key, default)
    if value is None:
        return default
    return value


def _scalar(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return float(value[0]) if value else default
    return float(value)


def _vector(value, default):
    if value is None:
        return list(default)
    if isinstance(value, (int, float)):
        return list(default)
    return list(value)


def load_task(task):
    """Return a list of episodes; each episode is a list of frame dicts."""
    offsets = available_tasks().get(task)
    if not offsets:
        return []
    frames = []
    for off in offsets:
        with open(os.path.join(CACHE, f"{task}_{off}.json")) as handle:
            payload = json.load(handle)
        for item in payload.get("rows", []):
            row = item.get("row") or {}
            frames.append(
                {
                    "episode_index": int(row.get("episode_index", 0)),
                    "frame_index": int(row.get("frame_index", 0)),
                    "timestamp": float(row.get("timestamp", 0.0) or 0.0),
                    "L_ee": _vector(_cell(row, "observation.state.left_ee_pose_gripper_base"), [0.0] * 6),
                    "R_ee": _vector(_cell(row, "observation.state.right_ee_pose_gripper_base"), [0.0] * 6),
                    "L_grip": _scalar(_cell(row, "observation.state.left_gripper"), 5.5),
                    "R_grip": _scalar(_cell(row, "observation.state.right_gripper"), 5.5),
                    "a_L": _vector(_cell(row, "action.left_arm"), [0.0] * 7),
                    "a_R": _vector(_cell(row, "action.right_arm"), [0.0] * 7),
                }
            )
    frames.sort(key=lambda f: (f["episode_index"], f["frame_index"]))
    episodes = []
    current = []
    last = None
    for frame in frames:
        if last is not None and frame["episode_index"] != last:
            episodes.append(current)
            current = []
        current.append(frame)
        last = frame["episode_index"]
    if current:
        episodes.append(current)
    return episodes
