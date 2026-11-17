"""Round-2 probe: checkpoint density & recovery-window coverage from real UniBot states.

Uses exp/unibot_states/*.npz (contiguous 800-frame windows, fetched from the
official HF datasets on 2026-11-04). All demos are successful; we therefore
measure only *where recoverable checkpoints exist and how far a rewind would be*,
not real failure labels.

Outputs exp/recovery_aug_results.json
"""
import glob, json, os
import numpy as np

EXP = "/home/runner/work/xuen/xuen/workspace/exp"
FPS = 30.0
SETTLE = 9          # ~0.3 s after gripper closure -> grasp verified
MIN_HOLD = 8        # >=0.27 s closed
MOVE_EPS = 0.02     # 2 cm net EE displacement = object likely carried


def medfilt(x, k=5):
    if len(x) < k:
        return x.copy()
    pad = k // 2
    xp = np.pad(x, pad, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(xp, k), axis=-1)


def segments(mask):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def analyse_hand(pos, grip, fps=FPS):
    """pos: (T,3) EE position; grip: (T,) aperture. Returns checkpoints + coverage."""
    g = medfilt(np.asarray(grip, float), 5)
    q10, q90 = np.nanpercentile(g, 10), np.nanpercentile(g, 90)
    if not np.isfinite(q10 + q90) or q90 - q10 < 1e-6:
        return None
    thr = q10 + 0.5 * (q90 - q10)
    closed = g < thr
    v = np.linalg.norm(np.diff(np.asarray(pos, float), axis=0), axis=1) * fps
    v = np.concatenate([[0.0], v])                      # m/s

    cps, holds = [], []
    for a, b in segments(closed):
        if b - a < MIN_HOLD:
            continue
        c = min(a + SETTLE, b - 1)
        disp = np.linalg.norm(pos[b - 1] - pos[a])
        holds.append(dict(t0=a / fps, t1=b / fps, dur=(b - a) / fps,
                          disp=float(disp), mean_speed=float(np.nanmean(v[a:b])),
                          carried=bool(disp >= MOVE_EPS)))
        if disp >= MOVE_EPS:                            # carried while closed -> usable checkpoint
            cps.append(c)

    T = len(g)
    # coverage(B): fraction of frames whose most-recent checkpoint is <= B frames old
    cover = {}
    for B in [15, 30, 45, 60, 90, 120]:
        covered, last = 0, -10**9
        ci = 0
        for t in range(T):
            while ci < len(cps) and cps[ci] <= t:
                last = cps[ci]; ci += 1
            if t - last <= B:
                covered += 1
        cover[str(B)] = covered / T
    # rewind distance if a failure occurs at a uniformly random frame after a checkpoint
    rew = []
    ci = 0; last = None
    for t in range(T):
        while ci < len(cps) and cps[ci] <= t:
            last = cps[ci]; ci += 1
        if last is not None:
            rew.append((t - last) / fps)
    return dict(thr=float(thr), n_checkpoints=len(cps), n_holds=len(holds),
                cp_per_10s=len(cps) / (T / fps) * 10,
                hold_dur=float(np.mean([h["dur"] for h in holds])) if holds else None,
                carried_frac=float(np.mean([h["carried"] for h in holds])) if holds else None,
                coverage=cover,
                rewind_median=float(np.median(rew)) if rew else None,
                rewind_p90=float(np.percentile(rew, 90)) if rew else None,
                frac_covered_2s=float(np.mean([r <= 2.0 for r in rew])) if rew else None)


def main():
    rows, all_cov = [], {str(b): [] for b in [15, 30, 45, 60, 90, 120]}
    all_rew, all_cp10 = [], []
    for p in sorted(glob.glob(os.path.join(EXP, "unibot_states", "*.npz"))):
        task = os.path.basename(p)[:-4].replace("G1_Dex1_", "")
        d = np.load(p, allow_pickle=True)["contig"].item()
        eps = np.unique(d["episode_index"])
        for e in eps:
            m = d["episode_index"] == e
            if m.sum() < 120:
                continue
            for hand in ["left", "right"]:
                pos = d[f"observation.state.{hand}_ee_pose_gripper_base"][m][:, :3]
                grip = d[f"observation.state.{hand}_gripper"][m]
                r = analyse_hand(pos, grip)
                if r is None:
                    continue
                rows.append(dict(task=task, hand=hand, n_frames=int(m.sum()), **{
                    k: r[k] for k in ["n_checkpoints", "cp_per_10s", "hold_dur",
                                      "carried_frac", "rewind_median", "rewind_p90",
                                      "frac_covered_2s"]}))
                for b in all_cov:
                    all_cov[b].append(r["coverage"][b])
                if r["rewind_median"] is not None:
                    all_rew.append(r["rewind_median"])
                all_cp10.append(r["cp_per_10s"])
    out = dict(n_episode_hand=int(len(rows)),
               checkpoint_per_10s=dict(mean=float(np.mean(all_cp10)), median=float(np.median(all_cp10)),
                                       p10=float(np.percentile(all_cp10, 10)), p90=float(np.percentile(all_cp10, 90))),
               rewind_median_s=dict(mean=float(np.mean(all_rew)), median=float(np.median(all_rew)),
                                    p90=float(np.percentile(all_rew, 90))),
               coverage_by_budget={b: dict(mean=float(np.mean(v)), p10=float(np.percentile(v, 10)))
                                   for b, v in all_cov.items()},
               per_eps=rows)
    with open(os.path.join(EXP, "recovery_aug_results.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "per_eps"}, indent=1))


if __name__ == "__main__":
    main()
