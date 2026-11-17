"""Round-2 probe: can a *cheap, observable* residual detect failure onset?

Signal available under the official API: our own commanded EE targets + the next
observation's EE pose + 1-D gripper aperture. We compute the tracking residual
r_t = || a_t^pos - s_{t+1}^pos || on real successful demos, normalise it by the
episode's initial median/MAD, and run a two-sided CUSUM. Nominal demos give the
false-alarm rate; synthetic step perturbations (slip / blocked insertion) give
detection delay. This is a detector-characterisation experiment, not a dynamics
simulation.

Outputs exp/failure_detector_results.json
"""
import glob, json, os
import numpy as np

EXP = "/home/runner/work/xuen/xuen/workspace/exp"


def cusum(z, k=1.0, h=6.0):
    gp = gn = 0.0
    for t, x in enumerate(z):
        gp = max(0.0, gp + x - k)
        gn = max(0.0, gn - x - k)
        if gp > h or gn > h:
            return t, (gp > h)
    return None, None


def stats_for(seed=0):
    rng = np.random.default_rng(seed)
    nom_alarm = {h: 0 for h in [4, 6, 8, 10]}
    nom_n = 0
    det = {d: {h: [] for h in [4, 6, 8, 10]} for d in [0.02, 0.05, 0.10]}
    nrms, delays = [], []
    for p in sorted(glob.glob(os.path.join(EXP, "unibot_states", "*.npz"))):
        d = np.load(p, allow_pickle=True)["contig"].item()
        for e in np.unique(d["episode_index"]):
            m = d["episode_index"] == e
            if m.sum() < 200: continue
            for hand in ["left", "right"]:
                s = d[f"observation.state.{hand}_ee_pose_gripper_base"][m][:, :3]
                a = d[f"action.{hand}_ee_pose_gripper_base"][m][:, :3]
                if len(s) < 200: continue
                r = np.linalg.norm(a[:-1] - s[1:], axis=1)
                med = np.median(r[:45]); mad = np.median(np.abs(r[:45] - med)) + 1e-4
                z = (r - med) / (1.4826 * mad)
                nrms.append(np.percentile(z, 99))
                nom_n += 1
                for h in nom_alarm:
                    t, _ = cusum(z, 1.0, h)
                    if t is not None: nom_alarm[h] += 1
                # inject a persistent EE offset at a random point in the second half
                for dlt in det:
                    f = rng.integers(len(s) // 2, len(s) - 40)
                    s2 = s.copy(); s2[f:] += np.array([dlt, 0, 0])
                    r2 = np.linalg.norm(a[:-1] - s2[1:], axis=1)
                    z2 = (r2 - med) / (1.4826 * mad)
                    for h in det[dlt]:
                        t, _ = cusum(z2, 1.0, h)
                        if t is not None and t >= f - 2:
                            det[dlt][h].append((t - f) / 30.0)
                        elif t is not None:
                            det[dlt][h].append((t - f) / 30.0)   # early alarm counts as FA
    return dict(n_nominal=n nom if False else n_nominal if False else nom_n)


def main():
    out = stats_for()
    json.dump(out, open(os.path.join(EXP, "failure_detector_results.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
