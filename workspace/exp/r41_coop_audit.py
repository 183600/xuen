"""Round 41 / v18 audit: how bimanual and how *coupled* are the released
G1_Dex1 demonstrations?  This measures coordination content on real,
released state/action channels (exp/unibot_states/*.npz).  It is not a
benchmark result and not a robot experiment.

Why: a "cooperative control" layer is only worth its complexity if either
(a) both arms are simultaneously active, or (b) the arms form a closed chain
(both grippers closed on a common object / fixed relative pose).  If most
frames are single-arm + idle, the correct design is mode-gated: cooperative
control only on co-hold segments, independent/non-contact coordination else.

Outputs exp/r41_coop_audit_results.json
Run: PYTHONPATH=.pylibs python3 exp/r41_coop_audit.py
"""
import glob, json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "r41_coop_audit_results.json")
FPS = 30.0
V_MOVE = 0.02      # m/s, an arm counts as "moving"
V_IDLE = 0.01      # m/s
GRIP_CLOSED = 1.0  # Dex1: ~4.5 open -> ~0 closed
MIN_RUN = 30


def runs(ep, fr, min_len=MIN_RUN):
    out = []
    start = 0
    n = len(ep)
    for i in range(1, n + 1):
        if i == n or ep[i] != ep[i - 1] or fr[i] != fr[i - 1] + 1:
            if i - start >= min_len:
                out.append((start, i))
            start = i
    return out


def speed(p):
    d = np.diff(p, axis=0) * FPS
    s = np.linalg.norm(d, axis=1)
    return np.r_[s, s[-1] if len(s) else 0.0]


def main():
    tasks = {}
    agg = []
    for f in sorted(glob.glob(os.path.join(HERE, "unibot_states", "*.npz"))):
        name = os.path.basename(f).replace("G1_Dex1_", "").replace(".npz", "")
        d = np.load(f, allow_pickle=True)
        c = d["contig"].item()
        ep = c["episode_index"].astype(np.int64)
        fr = c["frame_index"].astype(np.int64)
        lg = c["observation.state.left_gripper"]
        rg = c["observation.state.right_gripper"]
        lp = c["observation.state.left_ee_pose_gripper_base"][:, :3]
        rp = c["observation.state.right_ee_pose_gripper_base"][:, :3]
        la = c["observation.state.left_arm"]
        ra = c["observation.state.right_arm"]

        n = 0; both_move = 0; both_closed = 0; left_only = 0
        right_only = 0; both_open = 0; idle_one = 0; rel = []
        corr = []; rs_err = []
        for a, b in runs(ep, fr):
            if b - a < 5:
                continue
            sl, sr = speed(lp[a:b]), speed(rp[a:b])
            gl, gr = lg[a:b], rg[a:b]
            m = b - a
            n += m
            both_move += int(np.sum((sl > V_MOVE) & (sr > V_MOVE)))
            both_closed += int(np.sum((gl < GRIP_CLOSED) & (gr < GRIP_CLOSED)))
            left_only += int(np.sum((gl < GRIP_CLOSED) & (gr >= GRIP_CLOSED)))
            right_only += int(np.sum((gr < GRIP_CLOSED) & (gl >= GRIP_CLOSED)))
            both_open += int(np.sum((gl >= GRIP_CLOSED) & (gr >= GRIP_CLOSED)))
            idle_one += int(np.sum(((sl < V_IDLE) & (sr > 3 * V_MOVE)) |
                                   ((sr < V_IDLE) & (sl > 3 * V_MOVE))))
            # relative EE speed during frames with both grippers closed
            cc = (gl < GRIP_CLOSED) & (gr < GRIP_CLOSED)
            if cc.sum() >= 5:
                dp = np.diff(rp[a:b] - lp[a:b], axis=0) * FPS
                rel.append(np.linalg.norm(dp, axis=1)[cc[1:]].tolist())
            if sl.std() > 1e-6 and sr.std() > 1e-6:
                corr.append(float(np.corrcoef(sl, sr)[0, 1]))
            # relative-pose "slip" proxy: variation of |pR-pL| while co-closed
            dist = np.linalg.norm(rp[a:b] - lp[a:b], axis=1)
            rs_err.append(float(np.std(dist[cc])) if cc.sum() >= 5 else np.nan)

        if n == 0:
            continue
        rel_flat = np.concatenate([np.asarray(x) for x in rel]) if rel else np.array([])
        t = dict(
            frames=n,
            both_moving=round(both_move / n, 4),
            both_closed=round(both_closed / n, 4),
            single_left=round(left_only / n, 4),
            single_right=round(right_only / n, 4),
            both_open=round(both_open / n, 4),
            one_idle_other_active=round(idle_one / n, 4),
            arm_speed_corr_mean=(round(float(np.nanmean(corr)), 4) if corr else None),
            cohold_rel_speed_p50=(round(float(np.median(rel_flat)), 4) if len(rel_flat) else None),
            cohold_rel_speed_p95=(round(float(np.percentile(rel_flat, 95)), 4) if len(rel_flat) else None),
            cohold_rel_dist_std_mm=(round(float(1000 * np.nanmean(rs_err)), 2)
                                    if np.isfinite(np.nanmean(rs_err)) else None),
        )
        tasks[name] = t
        agg.append(t)

    def mean(k):
        v = [x[k] for x in agg if x[k] is not None]
        return round(float(np.mean(v)), 4) if v else None

    summary = {k: mean(k) for k in [
        "both_moving", "both_closed", "single_left", "single_right",
        "both_open", "one_idle_other_active", "arm_speed_corr_mean",
        "cohold_rel_speed_p50", "cohold_rel_speed_p95",
        "cohold_rel_dist_std_mm"]}
    summary["n_tasks"] = len(tasks)
    summary["reading"] = (
        "both_closed = proxy for simultaneous two-gripper grasp; "
        "cohold_rel_* = relative EE motion while both grippers are closed "
        "(small = quasi-rigid closed chain, large = two independent grasps "
        "or slip). arm_speed_corr_mean near 0 = independent arms; near 1 = "
        "synchronised arms.")
    json.dump({"summary": summary, "per_task": tasks}, open(OUT, "w"),
              indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
