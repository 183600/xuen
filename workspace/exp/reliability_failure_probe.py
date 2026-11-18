#!/usr/bin/env python3
"""Round-2 probe: is a cheap residual monitor reliable enough to gate retries?

Signal available under the official API: commanded EE position a_t and the next
observed EE position s_{t+1}; residual r_t = ||a_t - s_{t+1}||. Normalise by the
episode's early median/MAD, run a two-sided CUSUM. Nominal (successful) demos
give the false-alarm rate; injected step offsets (slip / blocked insertion) give
detection delay. Detector characterisation on real successful demos, NOT a
dynamics simulation and NOT benchmark evidence.

Outputs exp/reliability_failure_probe.json
"""
import glob
import json
import os

import numpy as np

EXP = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(20261118)
HS = [4, 6, 8, 10]
DELTAS = [0.01, 0.02, 0.05, 0.10]


def cusum(z, k=1.0, h=6.0):
    gp = gn = 0.0
    for t, x in enumerate(z):
        gp = max(0.0, gp + x - k)
        gn = max(0.0, gn - x - k)
        if gp > h:
            return t, 1
        if gn > h:
            return t, -1
    return None, 0


def episodes():
    for p in sorted(glob.glob(os.path.join(EXP, "unibot_states", "*.npz"))):
        d = np.load(p, allow_pickle=True)["contig"].item()
        name = os.path.basename(p).replace("G1_Dex1_", "").replace(".npz", "")
        for e in np.unique(d["episode_index"]):
            m = d["episode_index"] == e
            if m.sum() < 200:
                continue
            for hand in ["left", "right"]:
                s = d[f"observation.state.{hand}_ee_pose_gripper_base"][m][:, :3]
                a = d[f"action.{hand}_ee_pose_gripper_base"][m][:, :3]
                if len(s) != len(a) or len(s) < 200:
                    continue
                yield name, int(e), hand, s, a


def main():
    nominal = {h: 0 for h in HS}
    n_nom = 0
    det = {dl: {h: [] for h in HS} for dl in DELTAS}
    nom_p99 = []
    n_eps = 0
    per_task = {}

    for name, e, hand, s, a in episodes():
        n_eps += 1
        r = np.linalg.norm(a[:-1] - s[1:], axis=1)
        k0 = max(10, min(45, len(r) // 4))
        med = np.median(r[:k0])
        mad = np.median(np.abs(r[:k0] - med)) + 1e-6
        z = (r - med) / (1.4826 * mad)
        nom_p99.append(float(np.percentile(z, 99)))
        for h in HS:
            t, _ = cusum(z, 1.0, h)
            if t is not None:
                nominal[h] += 1
                per_task.setdefault(name, {"nom_alarm": 0, "n": 0})
                per_task[name]["nom_alarm"] += 1
            per_task.setdefault(name, {"nom_alarm": 0, "n": 0})
            per_task[name]["n"] += 1

        for dl in DELTAS:
            f = int(RNG.integers(len(r) // 2, len(r) - 40))
            z2 = z.copy()
            # persistent offset => residual shift of about dl in metres,
            # normalised by the same robust scale (scale reported below)
            z2[f:] += dl / (1.4826 * mad)
            for h in HS:
                t, _ = cusum(z2, 1.0, h)
                if t is not None and t >= f - 2:
                    det[dl][h].append(int(t - f))

    out = {
        "source": "exp/unibot_states/*.npz (real successful demos, 12 tasks)",
        "warning": "detector characterisation on successful demos with synthetic step perturbations; NOT benchmark evidence",
        "n_episode_hand_rollouts": n_eps,
        "nominal_false_alarm_rate": {
            str(h): round(nominal[h] / max(n_eps, 1), 4) for h in HS},
        "nominal_z_p99_median": round(float(np.median(nom_p99)), 2),
        "nominal_z_p99_p90": round(float(np.percentile(nom_p99, 90)), 2),
        "detection_at_delta": {
            str(dl): {
                "h_" + str(h): {
                    "rate": round(len(v) / max(n_eps, 1), 4),
                    "median_delay_frames": (int(np.median(v)) if v else None),
                    "p90_delay_frames": (int(np.percentile(v, 90)) if v else None),
                } for h, v in det[dl].items()
            } for dl in DELTAS
        },
        "per_task_nominal": {
            k: {"n": v["n"], "alarm_rate": round(v["nom_alarm"] / max(v["n"], 1), 4)}
            for k, v in sorted(per_task.items())
        },
    }
    # Toy net-value map: base failure rate q, recovery chance given early
    # detection rho, cost of a false intervention c (loss of a would-be success).
    q, rho = 0.70, 0.50
    net = {}
    for h in HS:
        far = nominal[h] / max(n_eps, 1)
        detection = len(det[0.05][h]) / max(n_eps, 1)
        for c in [0.0, 0.1, 0.3]:
            net[f"h{h}_c{c}"] = round(q * detection * rho - (1 - q) * far * c, 4)
    out["toy_net_success_gain"] = net
    json.dump(out, open(os.path.join(EXP, "reliability_failure_probe.json"), "w"),
              indent=1, ensure_ascii=False)
    print(json.dumps(out, indent=1, ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main()
