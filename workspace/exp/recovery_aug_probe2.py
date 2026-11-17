"""Round-2 probe v2: checkpoint density, rewind coverage, admissible perturbation tube.

Real data: exp/unibot_states/*.npz (contiguous 800-frame windows from official HF).
Adds (a) pause-based subgoal checkpoints, (b) all-close holds, (c) per-step action
noise / cross-episode checkpoint dispersion for augmentation radius.
"""
import glob, json, os
import numpy as np

EXP = "/home/runner/work/xuen/xuen/workspace/exp"
FPS = 30.0
SETTLE, MIN_HOLD, MOVE_EPS = 9, 8, 0.02
PAUSE_V, PAUSE_MIN = 0.03, 6


def medfilt(x, k=5):
    if len(x) < k: return x.copy()
    pad = k // 2
    xp = np.pad(x, pad, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(xp, k), axis=-1)


def segs(mask):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]: j += 1
            out.append((i, j)); i = j
        else: i += 1
    return out


def coverage(T, cps, B):
    if not cps: return 0.0
    cov, last, ci = 0, -10**9, 0
    for t in range(T):
        while ci < len(cps) and cps[ci] <= t:
            last = cps[ci]; ci += 1
        if t - last <= B: cov += 1
    return cov / T


def rewind_stats(T, cps):
    if not cps: return None, None, None
    rew, ci, last = [], 0, None
    for t in range(T):
        while ci < len(cps) and cps[ci] <= t:
            last = cps[ci]; ci += 1
        if last is not None: rew.append((t - last) / FPS)
    return float(np.median(rew)), float(np.percentile(rew, 90)), float(np.mean(np.array(rew) <= 2.0))


def analyse(pos, grip, actpos):
    g = medfilt(np.asarray(grip, float), 5)
    q10, q90 = np.nanpercentile(g, 10), np.nanpercentile(g, 90)
    if not np.isfinite(q10 + q90) or q90 - q10 < 1e-6: return None
    thr = q10 + 0.5 * (q90 - q10)
    v = np.r_[0.0, np.linalg.norm(np.diff(pos, axis=0), axis=1) * FPS]
    T = len(g)
    grasp_cps, allhold_cps, holds = [], [], []
    for a, b in segs(g < thr):
        if b - a < MIN_HOLD: continue
        c = min(a + SETTLE, b - 1)
        disp = float(np.linalg.norm(pos[b - 1] - pos[a]))
        holds.append((a, b, disp))
        allhold_cps.append(c)
        if disp >= MOVE_EPS: grasp_cps.append(c)
    pause_cps, i = [], 0
    slow = medfilt((v < PAUSE_V).astype(float), 3) > 0.5
    for a, b in segs(slow):
        if b - a >= PAUSE_MIN: pause_cps.append(a)
    # action increments (EE position deltas actually commanded)
    da = np.diff(np.asarray(actpos, float), axis=0)
    step_norm = np.linalg.norm(da, axis=1) if da.size else np.array([np.nan])
    return dict(
        thr=float(thr), T=T,
        n_grasp=len(grasp_cps), n_hold=len(allhold_cps), n_pause=len(pause_cps),
        grasp_per_10s=len(grasp_cps) / (T / FPS) * 10,
        hold_per_10s=len(allhold_cps) / (T / FPS) * 10,
        pause_per_10s=len(pause_cps) / (T / FPS) * 10,
        cov_grasp=coverage(T, grasp_cps, 60), cov_hold=coverage(T, allhold_cps, 60),
        cov_pause=coverage(T, pause_cps, 60),
        cov_grasp2=coverage(T, grasp_cps, 30), cov_hold2=coverage(T, allhold_cps, 30),
        cov_pause2=coverage(T, pause_cps, 30),
        rew_grasp=rewind_stats(T, grasp_cps), rew_hold=rewind_stats(T, allhold_cps),
        step_delta_med=float(np.nanmedian(step_norm)),
        step_delta_p90=float(np.nanpercentile(step_norm, 90)),
        hold_durs=[(b - a) / FPS for a, b, _ in holds],
        grasp_poses=[pos[min(a + SETTLE, b - 1)].tolist() for a, b, d in holds if d >= MOVE_EPS],
    )


def main():
    per, agg = [], {k: [] for k in ["grasp_per_10s", "hold_per_10s", "pause_per_10s",
                                     "cov_grasp", "cov_hold", "cov_pause",
                                     "cov_grasp2", "cov_hold2", "cov_pause2",
                                     "step_delta_med", "step_delta_p90"]}
    rew = {"grasp": [], "hold": []}
    all_poses = {}
    for p in sorted(glob.glob(os.path.join(EXP, "unibot_states", "*.npz"))):
        task = os.path.basename(p)[:-4].replace("G1_Dex1_", "")
        d = np.load(p, allow_pickle=True)["contig"].item()
        for e in np.unique(d["episode_index"]):
            m = d["episode_index"] == e
            if m.sum() < 120: continue
            for hand in ["left", "right"]:
                r = analyse(d[f"observation.state.{hand}_ee_pose_gripper_base"][m][:, :3],
                            d[f"observation.state.{hand}_gripper"][m],
                            d[f"action.{hand}_ee_pose_gripper_base"][m][:, :3])
                if r is None: continue
                row = dict(task=task, hand=hand, n_frames=int(m.sum()),
                           **{k: r[k] for k in agg})
                row["rew_grasp"] = r["rew_grasp"]; row["rew_hold"] = r["rew_hold"]
                per.append(row)
                for k in agg: agg[k].append(r[k])
                if r["rew_grasp"] and r["rew_grasp"][0] is not None: rew["grasp"].append(r["rew_grasp"][0])
                if r["rew_hold"] and r["rew_hold"][0] is not None: rew["hold"].append(r["rew_hold"][0])
                all_poses.setdefault((task, hand), []).extend(r["grasp_poses"])
    # cross-episode dispersion at carried-grasp checkpoints (per task/hand)
    disp = []
    for (t, h), P in all_poses.items():
        P = np.array(P)
        if len(P) >= 3:
            s = np.linalg.norm(P - P.mean(0), axis=1)
            disp.append(dict(task=t, hand=h, n=len(P), rms=float(np.sqrt((s**2).mean())),
                             p90=float(np.percentile(s, 90))))
    out = dict(n_episode_hand=len(per),
               mean={k: float(np.mean(v)) for k, v in agg.items()},
               median={k: float(np.median(v)) for k, v in agg.items()},
               rewind_median_s={k: float(np.median(v)) for k, v in rew.items() if v},
               checkpoint_dispersion_m=dict(
                   n_groups=len(disp), median_rms=float(np.median([d["rms"] for d in disp])) if disp else None,
                   median_p90=float(np.median([d["p90"] for d in disp])) if disp else None),
               per_eps=per, dispersion=disp)
    json.dump(out, open(os.path.join(EXP, "recovery_aug_results2.json"), "w"), indent=1)
    print(json.dumps({k: out[k] for k in ["n_episode_hand", "mean", "median",
                                          "rewind_median_s", "checkpoint_dispersion_m"]}, indent=1))


if __name__ == "__main__":
    main()
