"""Round 16 evidence script: mine skill-event statistics from real UniBot-V1 parquet shards.

Question answered (B-level evidence, real data):
  Q1  Can skills be segmented deterministically from proprioception only
      (gripper aperture + base-frame EE motion), without any learned model?
  Q2  What is the per-task skill composition, and how much does the official
      frame-proportional sampling distort the skill mass?
  Q3  Do the two sampled tasks (short vs long horizon) share a skill vocabulary
      (i.e. is a shared skill library plausible across 32 tasks)?

Inputs (downloaded 2026-11-04, retrieved from the public HF dataset):
  G1_Dex1_HangCup       data/chunk-000/file-000.parquet   (short: 187 frames/ep)
  G1_Dex1_ToolboxStorage data/chunk-000/file-000.parquet  (long: 1127 frames/ep)
"""
import json
import os

import numpy as np
import pyarrow.parquet as pq

DATA = "/tmp/opencode/unibot/data"
OUT = "/home/runner/work/xuen/xuen/workspace/exp/profile_skills_results.json"
FPS = 30.0

SHARDS = {
    "HangCup": os.path.join(DATA, "hangcup_000.parquet"),
    "ToolboxStorage": os.path.join(DATA, "toolbox_000.parquet"),
}

# per-task episode/frame counts, verified from meta/info.json on 2026-11-04
TASK_STATS = {
    "ToolboxStorage": (1064, 1199136), "StorePaddle": (1047, 1072466),
    "SpellRobot": (1018, 951972), "PackPhone": (1016, 888914),
    "FoldTowel": (1053, 814363), "OrganizeTools": (1032, 774261),
    "OrganizeStationery": (1028, 738414), "StoreEarphones": (982, 709077),
    "ArrangePlates": (1069, 683859), "PourOutMedicine": (979, 640970),
    "OrganizePencilCase": (1024, 630494), "ColorArrangement": (1533, 625771),
    "PackDoll": (1060, 624447), "StoreCups": (1025, 609391),
    "RemovePinnedNote": (1026, 602619), "ArrangeTestTubes": (1004, 535169),
    "PlugInEthernet": (1009, 496037), "PackBag": (1067, 483831),
    "PickOutBatteries": (993, 479925), "SyringeWaterTransfer": (1034, 474353),
    "PlugCharger": (1022, 463451), "ZipUp": (1006, 426552),
    "Unlock": (970, 420522), "PaperCupStacking": (969, 402646),
    "ConveyorSorting": (1049, 383721), "PlacePhotoFrame": (1041, 348459),
    "FruitCollection": (1050, 340701), "FruitSorting": (1032, 330023),
    "DisconnectEthernet": (1025, 323878), "OrganizeBookshelf": (1027, 316651),
    "StackBowls": (979, 295609), "HangCup": (1043, 194564),
}

SKILLS = ["REACH", "CLOSE", "HOLD", "CARRY", "OPEN", "REGROUP"]


def col(table, name):
    return np.asarray(table.column(name).to_pylist())


def segment_arm(grip, pos, g_closed=1.1, v_thresh=0.03):
    """Deterministic per-frame skill labels for one arm.

    grip: gripper aperture (open ~4.46, closed ~0.08 in this dataset)
    pos:  base-frame EE xyz per frame
    """
    n = len(grip)
    speed = np.zeros(n)
    speed[1:] = np.linalg.norm(np.diff(pos, axis=0), axis=1) * FPS
    closed = grip < g_closed
    labels = np.empty(n, dtype=object)
    prev_closed = False
    for t in range(n):
        if closed[t] and not prev_closed:
            lab = "CLOSE"
        elif not closed[t] and prev_closed:
            lab = "OPEN"
        elif closed[t]:
            lab = "CARRY" if speed[t] > v_thresh else "HOLD"
        else:
            lab = "REACH" if speed[t] > v_thresh else "REGROUP"
        labels[t] = lab
        prev_closed = bool(closed[t])
    return labels, speed


def events(labels, kind, min_gap=3):
    idx = [i for i, l in enumerate(labels) if l == kind]
    out = []
    for i in idx:
        if not out or i - out[-1] >= min_gap:
            out.append(i)
    return out


def analyse(path):
    t = pq.read_table(path, columns=[
        "episode_index", "frame_index",
        "observation.state.left_gripper", "observation.state.right_gripper",
        "observation.state.left_ee_pose_gripper_base",
        "observation.state.right_ee_pose_gripper_base",
    ])
    ep = col(t, "episode_index")
    fi = col(t, "frame_index")
    lg = col(t, "observation.state.left_gripper")
    rg = col(t, "observation.state.right_gripper")
    lp = np.asarray(col(t, "observation.state.left_ee_pose_gripper_base"), dtype=float)
    rp = np.asarray(col(t, "observation.state.right_ee_pose_gripper_base"), dtype=float)

    # episodes are contiguous in LeRobot parquet; segment by frame_index resets
    starts = [0] + [i for i in range(1, len(ep)) if fi[i] == 0]
    bounds = starts + [len(ep)]

    per_ep = []
    comp = {s: 0 for s in SKILLS}
    total = 0
    for a, b in zip(starts, bounds):
        n = b - a
        if n < 2:
            continue
        l_lab, l_spd = segment_arm(np.asarray(lg[a:b], float), lp[a:b, :3])
        r_lab, r_spd = segment_arm(np.asarray(rg[a:b], float), rp[a:b, :3])
        close_ev = len(events(l_lab, "CLOSE")) + len(events(r_lab, "CLOSE"))
        open_ev = len(events(l_lab, "OPEN")) + len(events(r_lab, "OPEN"))
        labels = list(l_lab) + list(r_lab)
        cnt = {s: labels.count(s) for s in SKILLS}
        for s in SKILLS:
            comp[s] += cnt[s]
        total += 2 * n
        per_ep.append({
            "len": n, "close_events": close_ev, "open_events": open_ev,
            "comp": cnt, "max_speed": float(max(l_spd.max(), r_spd.max())),
        })
    return per_ep, comp, total, {
        "episodes": len(per_ep),
        "frames": int(sum(e["len"] for e in per_ep)),
        "mean_len": float(np.mean([e["len"] for e in per_ep])),
        "median_len": float(np.median([e["len"] for e in per_ep])),
        "median_close_events": float(np.median([e["close_events"] for e in per_ep])),
        "median_open_events": float(np.median([e["open_events"] for e in per_ep])),
        "median_close_per_100f": float(np.median(
            [100.0 * e["close_events"] / max(e["len"], 1) for e in per_ep])),
        "median_open_per_100f": float(np.median(
            [100.0 * e["open_events"] / max(e["len"], 1) for e in per_ep])),
        "frac_ep_with_close": float(np.mean([e["close_events"] > 0 for e in per_ep])),
        "frac_ep_with_open": float(np.mean([e["open_events"] > 0 for e in per_ep])),
    }


def main():
    out = {"source": "HF unitreerobotics/G1_Dex1_{HangCup,ToolboxStorage} "
                     "data/chunk-000/file-000.parquet, retrieved 2026-11-04",
           "fps": FPS, "tasks": {}}
    comps = {}
    for name, path in SHARDS.items():
        per_ep, comp, total, summary = analyse(path)
        comps[name] = comp
        out["tasks"][name] = {
            "summary": summary,
            "composition_pct": {s: round(100.0 * comp[s] / total, 3) for s in SKILLS},
        }
        print(name, json.dumps(out["tasks"][name], indent=1))

    # Q2: sampling distortion. task-level mass under the official loader
    # (ConcatDataset, proportional to number of samples = frames) vs episode-uniform.
    eps = sum(v[0] for v in TASK_STATS.values())
    frames = sum(v[1] for v in TASK_STATS.values())
    frame_mass = {k: v[1] / frames for k, v in TASK_STATS.items()}
    ep_mass = {k: v[0] / eps for k, v in TASK_STATS.items()}
    skew = {k: frame_mass[k] / ep_mass[k] for k in TASK_STATS}
    out["sampling"] = {
        "total_episodes": eps, "total_frames": frames,
        "hours_at_30fps": round(frames / FPS / 3600.0, 2),
        "task_frame_mass_min": round(min(frame_mass.values()), 4),
        "task_frame_mass_max": round(max(frame_mass.values()), 4),
        "task_skew_min": round(min(skew.values()), 3),
        "task_skew_max": round(max(skew.values()), 3),
        "worst_skew_task": max(skew, key=skew.get),
        "best_skew_task": min(skew, key=skew.get),
        "frame_mass": {k: round(v, 4) for k, v in sorted(
            frame_mass.items(), key=lambda x: -x[1])},
    }

    # skill-mass distortion on the two measured tasks, under three samplers
    # (a) frame-proportional (what the official loader does),
    # (b) episode-uniform,
    # (c) skill-balanced (equal mass per skill, then proportional inside a skill).
    meas = {}
    for name in SHARDS:
        n_ep = TASK_STATS[name][0]
        n_fr = TASK_STATS[name][1]
        f_frac = {s: comps[name][s] / sum(comps[name].values()) for s in SKILLS}
        meas[name] = {"frame_prop": f_frac, "ep_uniform": f_frac}

    # global frame-prop skill mass: weight each measured task by its global frame mass
    # and extrapolate the same composition to the other 30 tasks (assumption stated).
    w_meas = sum(frame_mass[n] for n in SHARDS)
    rest = 1.0 - w_meas
    mean_comp = {s: float(np.mean([comps[n][s] / sum(comps[n].values()) for n in SHARDS]))
                 for s in SKILLS}
    global_fp = {s: sum(frame_mass[n] * (comps[n][s] / sum(comps[n].values()))
                         for n in SHARDS) + rest * mean_comp[s] for s in SKILLS}
    global_ep = {s: sum(ep_mass[n] * (comps[n][s] / sum(comps[n].values()))
                        for n in SHARDS) + (1 - sum(ep_mass[n] for n in SHARDS)) * mean_comp[s]
                 for s in SKILLS}
    balanced = {s: 1.0 / len(SKILLS) for s in SKILLS}
    out["skill_mass"] = {
        "note": "global frame-prop / episode-uniform skill mass uses measured "
                "composition on 2 tasks and the mean composition on the other 30",
        "frame_proportional_pct": {s: round(100 * global_fp[s], 2) for s in SKILLS},
        "episode_uniform_pct": {s: round(100 * global_ep[s], 2) for s in SKILLS},
        "skill_balanced_pct": {s: round(100 * balanced[s], 2) for s in SKILLS},
        "frame_prop_max_min_ratio": round(max(global_fp.values()) / min(global_fp.values()), 2),
        "skill_balanced_max_min_ratio": 1.0,
    }
    print(json.dumps(out["skill_mass"], indent=1))
    print(json.dumps(out["sampling"], indent=1)[:1200])

    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
