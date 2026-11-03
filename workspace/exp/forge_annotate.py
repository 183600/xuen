"""FORGE-DA evidence, part 1: can we auto-annotate the 32 public demo sets
into task-agnostic *phase* structure from proprioception alone -- no human
labels, no images, no second deployed model?

Source: HF datasets-server rows API for unitreerobotics/G1_Dex1_<Task>
        (LeRobot v3.0). Retrieved 2026-11-03 (UTC).

This is a DESCRIPTIVE measurement of the released demonstrations. It is NOT
benchmark evidence about our own policy.

Questions (each maps to a FORGE-DA claim):
  Q1  Are grasp / release events recoverable from gripper + EE kinematics in
      all 32 tasks?                                   [annotation feasibility]
  Q2  How long are the resulting phases (approach / grasp / transport /
      release), per task, in frames?                  [annotation feasibility]
  Q3  Is the APPROACH phase more cross-task similar (shape) than the
      MANIPULATION phase?  If so, "go-to-pose geometry" is separable from
      "what to do" semantics.                         [factorization]
  Q4  Which tasks are structurally bimanual (two grippers closed at once /
      alternating)?                                   [multi-arm annotation]

Output: exp/forge_annotate_results.json
"""
import json
import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

API = "https://datasets-server.huggingface.co/rows"
PAGE = 100
PAGES = 8
CACHE = "/tmp/opencode/hf_rows_cache_annot"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forge_annotate_results.json")

GRIP_OPEN = 4.5
GRIP_CLOSED_EVENT = 2.0     # opening at/below this counts as "closed"
RISE = 1.5                  # open->close must cross this much

TASKS = [
    "HangCup", "FruitCollection", "PackDoll", "FruitSorting",
    "DisconnectEthernet", "ColorArrangement", "PlacePhotoFrame",
    "OrganizeBookshelf", "ToolboxStorage", "PlugCharger", "PickOutBatteries",
    "Unlock", "ArrangeTestTubes", "PourOutMedicine", "OrganizeTools",
    "FoldTowel", "OrganizeStationery", "PackBag", "ZipUp",
    "PaperCupStacking", "ArrangePlates", "SpellRobot", "StorePaddle",
    "ConveyorSorting", "StoreCups", "PlugInEthernet", "StackBowls",
    "StoreEarphones", "PackPhone", "RemovePinnedNote",
    "OrganizePencilCase", "SyringeWaterTransfer",
]


def _get(url, dest, timeout=40):
    if os.path.exists(dest) and os.path.getsize(dest) > 64:
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def fetch_page(task, offset):
    q = urllib.parse.urlencode({
        "dataset": f"unitreerobotics/G1_Dex1_{task}",
        "config": "default", "split": "train",
        "offset": offset, "length": PAGE})
    url = f"{API}?{q}"
    dest = os.path.join(CACHE, f"{task}_{offset}.json")
    if not _get(url, dest):
        return None
    try:
        with open(dest) as f:
            return json.load(f)
    except Exception:
        return None


def col(rows, name):
    out = []
    for r in rows:
        v = r["row"].get(name)
        out.append(v)
    return out


def ascending_events(g, thr=GRIP_CLOSED_EVENT, rise=RISE):
    """Return frame indices of close (open->closed) and open (closed->open)."""
    g = np.asarray(g, dtype=float)
    closed = g <= thr
    closes, opens = [], []
    state = closed[0]
    last = 0.0
    for i in range(1, len(g)):
        if state and g[i] > thr + rise:
            state = False
            opens.append(i)
        elif (not state) and g[i] <= thr:
            # require the arm actually moved / stayed; simple crossing
            state = True
            closes.append(i)
    return closes, opens


def phase_durations(ep):
    """ep: dict arm -> arrays. Returns list of (approach, grasp, transport,
    release) frame lengths around the first grasp/release pair."""
    g = np.asarray(ep["grip"], dtype=float)
    closes, opens = ascending_events(g)
    if not closes:
        return None
    c = closes[0]
    o = next((x for x in opens if x > c), None)
    n = len(g)
    approach = c
    grasp = 4
    transport = (o - c) if o is not None else (n - c)
    release = (n - o) if o is not None else 0
    return approach, grasp, transport, release


def resample(x, k=16):
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return np.zeros((k, x.shape[1] if x.ndim > 1 else 1), dtype=float)
    idx = np.linspace(0, len(x) - 1, k).astype(int)
    return x[idx]


def arm_ee(rows, side):
    key = f"observation.state.{side}_ee_pose_gripper_base"
    return np.array([r["row"][key][:3] for r in rows], dtype=float)


def arm_grip(rows, side):
    key = f"observation.state.{side}_gripper"
    return np.array([r["row"][key] for r in rows], dtype=float)


def episodes_of(rows):
    ep = [r["row"]["episode_index"] for r in rows]
    bounds = [0]
    for i in range(1, len(ep)):
        if ep[i] != ep[i - 1]:
            bounds.append(i)
    bounds.append(len(ep))
    out = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a >= 8:
            out.append(rows[a:b])
    return out


def load_task(task):
    pages = [fetch_page(task, o) for o in range(0, PAGE * PAGES, PAGE)]
    rows = []
    for p in pages:
        if p and p.get("rows"):
            rows.extend(p["rows"])
    return rows


def analyse_task(task, rows):
    eps = episodes_of(rows)
    rec = {"task": task, "frames": len(rows), "episodes": len(eps)}
    per_arm = {}
    all_phase = []
    ee_approach, ee_manip = [], []
    bimanual_frames = 0
    total_frames = 0
    active_arms = []
    for side in ("left", "right"):
        gc, oc = 0, 0
        durs = []
        rng = 0.0
        for e in eps:
            grip = arm_grip(e, side)
            rng = max(rng, float(np.max(grip) - np.min(grip)))
            closes, opens = ascending_events(grip)
            gc += len(closes)
            oc += len(opens)
            pd = phase_durations({"grip": grip})
            if pd:
                durs.append(pd)
        per_arm[side] = {
            "closes": gc, "opens": oc,
            "grip_range": round(rng, 2),
            "closes_per_ep": round(gc / max(1, len(eps)), 2),
            "median_phase": (np.median(np.array(durs), axis=0).tolist()
                             if durs else None)}
        if rng >= RISE:
            active_arms.append(side)
        for d in durs:
            all_phase.append(d)
    rec["per_arm"] = per_arm
    rec["active_arms"] = active_arms
    rec["n_active_arms"] = len(active_arms)
    # bimanual: both grippers closed in the same frame
    for e in eps:
        gl = np.asarray(arm_grip(e, "left"))
        gr = np.asarray(arm_grip(e, "right"))
        n = min(len(gl), len(gr))
        bimanual_frames += int(np.sum((gl[:n] <= GRIP_CLOSED_EVENT) &
                                      (gr[:n] <= GRIP_CLOSED_EVENT)))
        total_frames += n
    rec["bimanual_frame_frac"] = round(bimanual_frames / max(1, total_frames), 4)

    # trajectory shape samples for factorization: use whichever arm grasps
    for e in eps:
        for side in ("left", "right"):
            grip = arm_grip(e, side)
            closes, opens = ascending_events(grip)
            if not closes:
                continue
            c = closes[0]
            o = next((x for x in opens if x > c), None) or c
            ee = arm_ee(e, side)
            ee = ee - ee[0]
            if c >= 4:
                ee_approach.append(resample(ee[:c], 16))
            if o - c >= 4:
                ee_manip.append(resample(ee[c:o], 16))
            break
    rec["weak_median_phase"] = (
        np.median(np.array(all_phase), axis=0).tolist() if all_phase else None)
    return rec, (ee_approach, ee_manip)


def mean_pairwise_dist(samples):
    if len(samples) < 2:
        return None
    S = np.stack(samples)
    # normalise each sample by its own path length for shape-only comparison
    norms = np.linalg.norm(S[:, -1] - S[:, 0], axis=1, keepdims=True) + 1e-6
    S = S / norms[:, None, :]
    d = []
    n = len(S)
    step = max(1, n // 80)
    idx = list(range(0, n, step))
    for i in idx:
        diff = S - S[i]
        dd = np.linalg.norm(diff, axis=2).mean(axis=1)
        d.extend(dd.tolist())
    return float(np.mean(d))


def main():
    os.makedirs(CACHE, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        loaded = list(ex.map(load_task, TASKS))

    results, approach_samples, manip_samples, per_task_shapes = [], [], [], {}
    for task, rows in zip(TASKS, loaded):
        if not rows:
            results.append({"task": task, "error": "no rows"})
            continue
        rec, (ap, ma) = analyse_task(task, rows)
        results.append(rec)
        per_task_shapes[task] = (mean_pairwise_dist(ap), mean_pairwise_dist(ma))
        approach_samples.extend(ap)
        manip_samples.extend(ma)

    cross_task_approach = mean_pairwise_dist(approach_samples)
    cross_task_manip = mean_pairwise_dist(manip_samples)

    by_phase = {}
    for r in results:
        mp = r.get("weak_median_phase")
        if mp:
            by_phase[r["task"]] = mp

    def has_grasp(r):
        pa = r.get("per_arm", {})
        return any(pa.get(s, {}).get("closes", 0) > 0 for s in ("left", "right"))

    out = {
        "retrieved": "2026-11-03",
        "n_tasks": len(TASKS),
        "tasks_with_grasp": sum(1 for r in results if has_grasp(r)),
        "per_task": results,
        "cross_task_shape_dist_approach": cross_task_approach,
        "cross_task_shape_dist_manipulation": cross_task_manip,
        "note": "shape distance = mean pairwise L2 between path-length-normalised "
                "16-point EE displacement trajectories; lower = more similar.",
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)

    # printed summary
    print("=" * 78)
    print("FORGE-DA annotation feasibility (real public demos, no labels)")
    print("=" * 78)
    print(f"tasks parsed           : {out['n_tasks']}")
    print(f"tasks with grasp event : {out['tasks_with_grasp']}")
    print(f"cross-task APPROACH shape dist : {cross_task_approach:.4f}")
    print(f"cross-task MANIP    shape dist : {cross_task_manip:.4f}")
    if cross_task_approach and cross_task_manip:
        print(f"ratio manip/approach : {cross_task_manip/cross_task_approach:.3f}")
    print("-" * 78)
    print(f"{'task':22s} {'closes/ep':>9s} {'biman.f':>8s} "
          f"{'appr':>6s} {'transp':>7s} {'release':>8s}")
    for r in results:
        if "error" in r:
            print(f"{r['task']:22s}  ERROR")
            continue
        pa = r.get("per_arm", {})
        best = max((pa.get(s, {}).get("closes_per_ep", 0) for s in ("left", "right")),
                   default=0)
        mp = r.get("weak_median_phase") or [0, 0, 0, 0]
        print(f"{r['task']:22s} {best:9.2f} "
              f"{r['bimanual_frame_frac']:8.3f} "
              f"{mp[0]:6.0f} {mp[2]:7.0f} {mp[3]:8.0f} "
              f"arms={''.join(a[0] for a in r.get('active_arms', [])) or '-'}")
    print("=" * 78)
    return out


if __name__ == "__main__":
    main()
