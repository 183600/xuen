"""Round-2 probe: tail coverage of grasp-only vs pause-based checkpoints.

Last-mile failures happen late. We therefore recompute the 2 s rewind coverage
restricted to the last 50% / last 25% of each real demo window, for
(a) carried-grasp checkpoints and (b) motion-pause subgoal checkpoints.

Outputs exp/recovery_tail_results.json
"""
import glob, json, os
import numpy as np

EXP = "/home/runner/work/xuen/xuen/workspace/exp"
FPS, SETTLE, MIN_HOLD, MOVE_EPS = 30.0, 9, 8, 0.02
PAUSE_V, PAUSE_MIN, B = 0.03, 6, 60          # B=60 frames = 2 s


def medfilt(x, k=5):
    if len(x) < k: return x.copy()
    p = k // 2
    xp = np.pad(x, p, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(xp, k), axis=-1)


def segs(m):
    o, i, n = [], 0, len(m)
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]: j += 1
            o.append((i, j)); i = j
        else: i += 1
    return o


def cov(T, cps, a, b):
    if not cps: return 0.0
    c = tot = 0; last = -10**9; ci = 0
    for t in range(T):
        while ci < len(cps) and cps[ci] <= t:
            last = cps[ci]; ci += 1
        if a <= t < b:
            tot += 1
            if t - last <= B: c += 1
    return c / tot if tot else 0.0


def main():
    out = {"grasp": {0.5: [], 0.25: []}, "pause": {0.5: [], 0.25: []}}
    for p in sorted(glob.glob(os.path.join(EXP, "unibot_states", "*.npz"))):
        d = np.load(p, allow_pickle=True)["contig"].item()
        for e in np.unique(d["episode_index"]):
            m = d["episode_index"] == e
            if m.sum() < 200: continue
            for h in ["left", "right"]:
                pos = d[f"observation.state.{h}_ee_pose_gripper_base"][m][:, :3]
                g = medfilt(d[f"observation.state.{h}_gripper"][m])
                q10, q90 = np.percentile(g, 10), np.percentile(g, 90)
                if q90 - q10 < 1e-6: continue
                thr = q10 + .5 * (q90 - q10); T = len(g)
                v = np.r_[0., np.linalg.norm(np.diff(pos, axis=0), axis=1) * FPS]
                gc = [min(a + SETTLE, b - 1) for a, b in segs(g < thr)
                      if b - a >= MIN_HOLD and np.linalg.norm(pos[b - 1] - pos[a]) >= MOVE_EPS]
                pc = [a for a, b in segs(medfilt((v < PAUSE_V).astype(float), 3) > .5)
                      if b - a >= PAUSE_MIN]
                for frac in [0.5, 0.25]:
                    a = int(T * (1 - frac))
                    out["grasp"][frac].append(cov(T, gc, a, T))
                    out["pause"][frac].append(cov(T, pc, a, T))
    summary = {}
    for k in ["grasp", "pause"]:
        summary[k] = {str(f): dict(mean=float(np.mean(v)), median=float(np.median(v)),
                                   p10=float(np.percentile(v, 10)))
                      for f, v in out[k].items()}
    json.dump(summary, open(os.path.join(EXP, "recovery_tail_results.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
