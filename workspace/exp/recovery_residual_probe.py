"""Round-2 probe: detectability floor of a scalar tracking residual.

For every real successful demo window we compute the one-step tracking residual
vector v_t = a_t^pos - s_{t+1}^pos and its norm r_t = ||v_t||. We then inject a
persistent EE offset delta along +x and ask whether a *single-frame* threshold at
the nominal p95 / p99 of r separates injected frames from nominal frames. This
gives a lower bound on the slip magnitude visible to a scalar residual monitor.

Outputs exp/recovery_residual_results.json
"""
import glob, json, os
import numpy as np

EXP = "/home/runner/work/xuen/xuen/workspace/exp"


def collect():
    vecs = []
    for p in sorted(glob.glob(os.path.join(EXP, "unibot_states", "*.npz"))):
        d = np.load(p, allow_pickle=True)["contig"].item()
        for e in np.unique(d["episode_index"]):
            m = d["episode_index"] == e
            if m.sum() < 200:
                continue
            for hand in ["left", "right"]:
                s = d[f"observation.state.{hand}_ee_pose_gripper_base"][m][:, :3]
                a = d[f"action.{hand}_ee_pose_gripper_base"][m][:, :3]
                if len(s) < 200:
                    continue
                vecs.append(a[:-1] - s[1:])
    return np.concatenate(vecs, axis=0)


def main():
    V = collect()
    R = np.linalg.norm(V, axis=1)
    q = {p: float(np.percentile(R, p)) for p in [50, 75, 90, 95, 99]}
    # per-axis dispersion and lag-1 autocorrelation (diagnostic for sequential tests)
    axis_std = V.std(axis=0).tolist()
    ac1 = []
    for k in range(3):
        x = V[:, k]
        if x.std() > 1e-9:
            ac1.append(float(np.corrcoef(x[:-1], x[1:])[0, 1]))
    out = {"n_residuals": int(R.size), "nominal_quantiles_m": q,
           "per_axis_std_m": axis_std, "lag1_autocorr": ac1,
           "detectability": {}}
    for delta in [0.01, 0.02, 0.03, 0.05, 0.10]:
        V2 = V - np.array([delta, 0.0, 0.0])
        R2 = np.linalg.norm(V2, axis=1)
        row = {"median_injected_m": float(np.median(R2))}
        for pct in [95, 99]:
            row[f"recall_at_nominal_p{pct}"] = float(np.mean(R2 > q[pct]))
        out["detectability"][str(delta)] = row
    json.dump(out, open(os.path.join(EXP, "recovery_residual_results.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
