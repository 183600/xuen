"""CAP round-1 supporting simulation.

Compares a rigid position-target stream against command-space admittance
(reference shaping) on a 1-D contact/insertion task, using only quantities the
UniBot submission API actually exposes (commanded target u_t and observed EE
position x_t).  No torque / impedance-gain channel is assumed.

Run:  PYTHONPATH=.pylibs python3 exp/cap_admittance_sim.py
Writes exp/cap_admittance_results.json
"""

import json
import os

import numpy as np


DT = 1.0 / 30.0
T = 120
X_WALL = 0.10          # contact surface
X_GOAL = 0.12          # nominal target goes 2 cm past the surface (press/insert)
ALPHA = 0.30           # inner position-loop gain (unknown in reality; swept)


def nominal_traj(t):
    """Smooth 0 -> X_GOAL move over the first 60 steps, then hold."""
    s = min(t / 60.0, 1.0)
    s = s * s * (3 - 2 * s)          # smoothstep
    return X_GOAL * s


def rollout(mode, kc, alpha=ALPHA, noise=0.0, seed=0, beta=0.02,
            M=1.0, D=6.3, K=10.0, ke=100.0, guard=True):
    """Return metrics for one episode.

    mode: 'rigid' | 'adm' (second-order admittance) | 'prop' (proportional yield)
    """
    rng = np.random.default_rng(seed)
    x = 0.0
    u_prev = 0.0
    a = 0.0          # admittance offset (<= 0: yield backwards)
    va = 0.0
    forces, cmds, pos, jerks = [], [], [], []
    for t in range(T):
        x_nom = nominal_traj(t)
        # measured residual; a lag bias is removed using the previous velocity
        v_est = (x - pos[-1]) / DT if pos else 0.0
        r = u_prev - x
        r_lag = max(0.0, v_est) * (1 - alpha) / alpha
        f_hat = max(0.0, ke * (r - r_lag))

        if mode == "rigid":
            u = x_nom
        elif mode == "prop":
            u = x_nom - beta * (f_hat / ke)
        elif mode == "adm":
            acc = -f_hat / M - (D / M) * va - (K / M) * a
            va += DT * acc
            a += DT * va
            a = min(0.0, a)                    # only yield, never push ahead
            if guard:
                a = max(a, -0.03)              # hard yield cap (3 cm)
                va = max(min(va, 0.10), -0.10)  # rate cap
            u = x_nom + a
        else:
            raise ValueError(mode)

        if noise:
            x_meas_noise = rng.normal(0.0, noise)
        else:
            x_meas_noise = 0.0

        # inner position loop + stiff environment
        x_free = x + alpha * (u - x)
        if x_free <= X_WALL:
            x_next, f = x_free, 0.0
        else:
            x_next = X_WALL
            f = kc * (x_free - X_WALL)

        if cmds:
            jerks.append(abs(u - 2 * cmds[-1] + cmds[-2]) if len(cmds) > 1 else 0.0)
        forces.append(f)
        cmds.append(u)
        pos.append(x_next)
        u_prev = u
        x = x_next + x_meas_noise

    forces = np.asarray(forces)
    cmds = np.asarray(cmds)
    return {
        "peak_force": float(forces.max()),
        "mean_force_after_contact": float(forces[60:].mean()),
        "impulse": float(forces.sum() * DT),
        "jam_frac": float((forces > 20.0).mean()),
        "final_penetration": float(pos[-1] - X_WALL),
        "cmd_rms_jerk": float(np.sqrt(np.mean(np.asarray(jerks) ** 2)) if jerks else 0.0),
        "cmd_total_variation": float(np.abs(np.diff(cmds)).sum()),
    }


def summarize(rows):
    keys = rows[0].keys()
    return {k: float(np.mean([r[k] for r in rows])) for k in keys}


def main():
    out = {"config": {"dt": DT, "T": T, "x_wall": X_WALL, "x_goal": X_GOAL,
                      "alpha": ALPHA}, "sweeps": {}}
    kcs = [500.0, 2000.0, 10000.0]
    seeds = list(range(5))
    for kc in kcs:
        block = {}
        for mode in ["rigid", "prop", "adm"]:
            rows = [rollout(mode, kc, seed=s) for s in seeds]
            block[mode] = summarize(rows)
        # an over-aggressive admittance without guard, to expose instability
        rows = [rollout("adm", kc, seed=s, D=0.2, K=10.0, guard=False)
                for s in seeds]
        block["adm_unguarded"] = summarize(rows)
        out["sweeps"][str(int(kc))] = block

    # analytic reach-trim estimate: waist pitch shifts the shoulder forward
    l_torso, theta = 0.30, 0.15
    shift = l_torso * np.sin(theta)
    reach = 0.60
    d = 0.63
    out["reach_trim"] = {
        "torso_len_m": l_torso, "waist_pitch_rad": theta,
        "shoulder_shift_m": float(shift),
        "target_m": d, "arm_reach_m": reach,
        "extension_without_posture": float(d / reach),
        "extension_with_posture": float((d - shift) / reach),
    }

    path = os.path.join(os.path.dirname(__file__), "cap_admittance_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
