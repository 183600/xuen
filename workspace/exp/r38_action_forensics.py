"""Round-38 · action-channel forensics on the official UniBot-V1 demo datasets.

Data source (already cached locally, retrieved 2026-11-02/03 via HF datasets-server):
    unitreerobotics/G1_Dex1_<Task>  (LeRobot v3.0), split=train
    fields: observation.state.*, action.*, episode_index, frame_index, timestamp

Questions this script answers (all offline, reproducible):

  M1  CHUNK SMOOTHNESS / "harmonic" compressibility
      Are action chunks low-frequency (DCT) compressible?  If a chunk of T_a
      steps is described by K << T_a DCT coefficients at 95% energy, a flow
      matching model can be trained in coefficient space instead of raw time
      steps.  Report energy-compaction curves per joint space and per task.

  M2  COMMAND vs STATE (actuator transmission signature)
      The action is a *command* (joint position target), the observation is the
      *realised* state.  Measure residual r_t = a_{t-1} - q_t per joint:
        - magnitude distribution (does the plant lag the command?)
        - is the lag directional (backlash-like hysteresis) or symmetric?
        - does |r| spike at contact events (grasp/insert)?

  M3  JOINT vs EE action channels
      Both are present in the datasets.  Measure: are they redundant (one
      derived from the other)?  Which is smoother / lower-noise?  How much
      dimension is actually used by the demos?

  M4  LOWER-BODY / PIVOT channel
      action.pivot[7], action.lower_body[15], action.base_command[4],
      action.waist_action_joint[3] are in the data but the submission API
      exposes only action.pivot[7].  Are demos stationary?  If the waist never
      moves, that channel is a free DoF (reach extension) rather than a burden.

  M5  ACTUATOR ENVELOPE
      Per-joint command range, per-frame step size, and implied speed limits.
      These bound any learned action prior.
"""
import glob
import json
import os
import re
from collections import defaultdict

import numpy as np

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "duo_rows_cache")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "r38_action_forensics.json")


def load_task(task):
    """Return list of episodes; each episode is a dict of stacked np arrays."""
    files = sorted(glob.glob(os.path.join(CACHE, f"{task}_*.json")),
                   key=lambda p: int(re.search(r"_(\d+)\.json$", p).group(1)))
    rows = []
    for f in files:
        try:
            d = json.load(open(f))
        except Exception:
            continue
        for r in d.get("rows", []):
            rows.append(r["row"])
    if not rows:
        return []
    # sort by (episode_index, frame_index)
    rows.sort(key=lambda r: (int(r["episode_index"]), int(r["frame_index"])))
    eps, cur, cur_idx = [], {}, None
    for r in rows:
        ei = int(r["episode_index"])
        if ei != cur_idx:
            if cur:
                eps.append(cur)
            cur, cur_idx = {}, ei
        for k, v in r.items():
            if isinstance(v, list):
                cur.setdefault(k, []).append(np.asarray(v, dtype=np.float32))
            elif isinstance(v, (int, float)):
                cur.setdefault(k, []).append(np.float32(v))
            else:
                cur.setdefault(k, []).append(v)
    if cur:
        eps.append(cur)
    out = []
    for e in eps:
        d = {}
        for k, v in e.items():
            if k in ("observation.language",):
                continue
            arr = np.stack(v) if isinstance(v[0], np.ndarray) else np.asarray(v)
            d[k] = arr
        out.append(d)
    return out


TASKS = ["HangCup", "ArrangePlates", "ArrangeTestTubes", "ZipUp", "ColorArrangement",
         "Unlock", "DisconnectEthernet", "ConveyorSorting", "FruitCollection",
         "FoldTowel", "OrganizeBookshelf", "FruitSorting", "SpellRobot",
         "OrganizePencilCase", "OrganizeStationery", "StackBowls", "StoreCups",
         "OrganizeTools", "PackDoll", "PackBag", "PackPhone", "StoreEarphones",
         "StorePaddle", "PaperCupStacking", "PickOutBatteries", "ToolboxStorage",
         "PlugCharger", "SyringeWaterTransfer", "PlugInEthernet", "PlacePhotoFrame",
         "RemovePinnedNote", "PourOutMedicine"]


def dct_energy_compaction(x, K_list=(1, 2, 3, 4, 6, 8, 12, 16)):
    """x: (T,d) chunk. Return {K: fraction of energy kept by first K DCT coeffs}."""
    T = x.shape[0]
    n = np.arange(T)
    # DCT-II style basis: basis[k, n] = cos(pi (n+0.5) k / T)
    basis = np.cos(np.pi * (n[None, :] + 0.5) * np.arange(K_list[-1] + 1)[:, None] / T)
    C = basis @ x                        # (Kmax+1, d)
    tot = (x ** 2).sum()
    out = {}
    for K in K_list:
        k = min(K + 1, basis.shape[0])
        keep = (C[:k] ** 2).sum()
        out[K] = float(keep / tot) if tot > 0 else 1.0
    return out


def analyse_task(task):
    eps = load_task(task)
    if not eps:
        return None
    res = {"n_episodes": len(eps),
           "ep_len": [], "fps": None,
           "dct_joint": [], "dct_ee": [],
           "resid": [], "resid_dir": [], "grip_events": [],
           "pivot_var": [], "base_var": [], "waist_var": [],
           "act_range": {}, "step_max": {}, "ee_step": [],
           "joint_ee_corr": [], "ee_action_vs_state": []}
    fps_samples = []
    for e in eps:
        n = len(e["frame_index"])
        res["ep_len"].append(n)
        ts = e.get("timestamp")
        if ts is not None and len(ts) > 3:
            dt = np.diff(ts.astype(np.float64))
            med = np.median(dt[dt > 0]) if np.any(dt > 0) else None
            if med:
                fps_samples.append(1.0 / med)
        aL = e["action.left_arm"]; aR = e["action.right_arm"]
        qL = e["observation.state.left_arm"]; qR = e["observation.state.right_arm"]
        gL = e["action.left_gripper"]; gR = e["action.right_gripper"]
        eL = e["action.left_ee_pose_gripper_base"]; eR = e["action.right_ee_pose_gripper_base"]
        sLe = e["observation.state.left_ee_pose_gripper_base"]
        sRe = e["observation.state.right_ee_pose_gripper_base"]

        # ---- M1 DCT compaction on joint and ee chunks --------------------------
        T = 16
        for i in range(0, n - T + 1, 8):
            res["dct_joint"].append(dct_energy_compaction(aL[i:i + T]))
            res["dct_ee"].append(dct_energy_compaction(eL[i:i + T]))

        # ---- M2 command-vs-state residual --------------------------------------
        rL = aL[:-1] - qL[1:]          # command at t-1 vs realised at t
        rR = aR[:-1] - qR[1:]
        res["resid"].append(np.concatenate([rL, rR], 0))
        # directional: residual vs commanded velocity sign
        dL = aL[1:] - aL[:-1]
        dR = aR[1:] - aR[:-1]
        res["resid_dir"].append(np.concatenate([rL * np.sign(dL), rR * np.sign(dR)], 0))
        # gripper close events -> residual magnitude around them
        for g, r in ((gL, rL), (gR, rR)):
            gv = g.reshape(len(g), -1)
            closed = gv[:, 0] <= 1.0
            idx = np.where(np.diff(closed.astype(int)) == 1)[0]
            for i in idx:
                lo, hi = max(0, i - 5), min(len(r), i + 6)
                if hi > lo:
                    res["grip_events"].append(float(np.abs(r[lo:hi]).mean()))

        # ---- M3 joint vs ee redundancy -----------------------------------------
        # does the ee command track the ee *state* (i.e. is ee action an absolute
        # pose target) or a delta?
        res["ee_action_vs_state"].append(np.abs(eL[:-1] - sLe[1:]).mean(axis=0))
        # correlation between ee translation command and joint command magnitude
        res["joint_ee_corr"].append([float(np.corrcoef(np.abs(eL[:, i]), np.abs(aL[:, j]))[0, 1])
                                     if np.std(eL[:, i]) > 1e-6 and np.std(aL[:, j]) > 1e-6 else 0.0
                                     for i in range(3) for j in range(7)])
        res["ee_step"].append(np.abs(np.diff(eL[:, :3], axis=0)).max(axis=0))

        # ---- M4 lower body ------------------------------------------------------
        if "action.pivot" in e:
            res["pivot_var"].append(np.abs(e["action.pivot"] - e["action.pivot"][:1]).mean())
        if "action.base_command" in e:
            res["base_var"].append(np.abs(e["action.base_command"] - e["action.base_command"][:1]).mean())
        if "action.waist_action_joint" in e:
            res["waist_var"].append(np.abs(e["action.waist_action_joint"] - e["action.waist_action_joint"][:1]).mean())

        # ---- M5 envelope --------------------------------------------------------
        for key, arr in (("left_arm", aL), ("right_arm", aR)):
            res["act_range"][key] = (arr.min(axis=0).tolist(), arr.max(axis=0).tolist())
            res["step_max"][key] = np.abs(np.diff(arr, axis=0)).max(axis=0).tolist()

    R = np.concatenate(res["resid"], 0)
    D = np.concatenate(res["resid_dir"], 0)
    out = {
        "task": task,
        "n_episodes": res["n_episodes"],
        "ep_len_mean": float(np.mean(res["ep_len"])),
        "ep_len_min": int(np.min(res["ep_len"])), "ep_len_max": int(np.max(res["ep_len"])),
        "fps_median": float(np.median(fps_samples)) if fps_samples else None,
        "resid_abs_mean": float(np.abs(R).mean()),
        "resid_abs_p95": float(np.percentile(np.abs(R), 95)),
        "resid_abs_max": float(np.abs(R).max()),
        "resid_dir_mean": float(D.mean()),
        "resid_dir_absmean": float(np.abs(D).mean()),
        "grip_event_resid": float(np.mean(res["grip_events"])) if res["grip_events"] else None,
        "pivot_var": float(np.mean(res["pivot_var"])) if res["pivot_var"] else None,
        "base_var": float(np.mean(res["base_var"])) if res["base_var"] else None,
        "waist_var": float(np.mean(res["waist_var"])) if res["waist_var"] else None,
        "ee_action_vs_state": np.mean(res["ee_action_vs_state"], axis=0).tolist(),
        "ee_step_max": np.mean(res["ee_step"], axis=0).tolist(),
        "act_range": res["act_range"],
        "step_max": res["step_max"],
    }
    # aggregate DCT curves
    def agg(store):
        if not store:
            return None
        keys = list(store[0].keys())
        arr = np.array([[d[k] for k in keys] for d in store])  # (n_chunks, n_K)
        return {str(K): float(arr[:, i].mean()) for i, K in enumerate(keys)}
    out["dct_joint_mean"] = agg(res["dct_joint"])
    out["dct_ee_mean"] = agg(res["dct_ee"])
    return out


if __name__ == "__main__":
    allres = []
    for t in TASKS:
        r = analyse_task(t)
        if r:
            allres.append(r)
            print(f"{t:<22} eps={r['n_episodes']:>3} len={r['ep_len_mean']:>6.1f} "
                  f"fps={r['fps_median']} |r|mean={r['resid_abs_mean']:.4f} "
                  f"p95={r['resid_abs_p95']:.4f} grip_res={r['grip_event_resid']} "
                  f"pivot_var={r['pivot_var']} base_var={r['base_var']}")
    json.dump(allres, open(OUT, "w"), indent=1)
    print("\nsaved", OUT)

    # aggregate DCT
    def avg_curve(key):
        cur = defaultdict(list)
        for r in allres:
            if r.get(key):
                for k, v in r[key].items():
                    cur[k].append(v)
        return {k: float(np.mean(v)) for k, v in cur.items()}
    print("\n[DCT energy kept, mean over tasks/chunks] joint:", avg_curve("dct_joint_mean"))
    print("[DCT energy kept] ee:", avg_curve("dct_ee_mean"))
