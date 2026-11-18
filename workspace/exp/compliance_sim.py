"""Round 1 (impedance-control line) synthetic mechanism check.

NOT benchmark evidence.  A transparent quasi-static 2-D peg-in-hole model is used
to isolate one question that the offline UniBot trace cannot answer:

  With a pure position interface (no torque, no F/T sensor), does an outer-loop
  *apparent-impedance* layer plus a force-guided search primitive change the
  insertion success / contact-force trade-off, under actuation delay?

Model (all units mm, N, s):
  - hole radius clearance c=2.0, chamfer capture radius R=8.0
  - peg starts at a random lateral offset in a disk of radius 15 mm
  - vertical command v_z=8 mm/s; if the peg touches the table it penetrates by p
    and generates F_z = k_z p (k_z=6 N/mm).  F_z > F_jam (22 N) means a jam:
    lateral motion is blocked (static friction) until the normal force drops.
  - inside the chamfer (c<|r|<R) the chamfer produces a centering lateral force
    F_lat = -k_c (R-|r|) * unit(r), k_c=0.6 N/mm.  Outside R there is no lateral
    guidance.
  - rigid baseline: r_cmd follows a fixed plan (optionally an expanding spiral),
    no force feedback.  It stops descending once F_z > F_stop (18 N) but cannot
    reduce force, so a spiral often jams.
  - compliance: lateral admittance r_cmd = r_plan + alpha * F_lat_hat, and
    vertical admittance v_z_eff = v_z * clip(1 - F_z/F_jam, 0, 1).  F_lat_hat is
    delayed by d steps and corrupted by Gaussian noise (sensorless estimate).
  - success: |r| <= c and depth >= 20 mm; timeout 4 s; force limit 35 N.
A Monte-Carlo over initial offsets / angles / estimate noise is reported.
"""
import json
import numpy as np

DT = 1.0 / 30.0
T_MAX = 4.0
STEPS = int(T_MAX / DT)
C = 2.0
R = 8.0
KZ = 6.0
KC = 0.6
F_JAM = 22.0
F_STOP = 18.0
F_MAX = 35.0
F_BLOCK = 27.0       # lateral motion is blocked only above this normal force
F_LATCH = 1.0        # contact-triggered search freeze threshold
VZ = 8.0
TAU_R = 0.08
ALPHA = 1.0          # mm per N of admittance (lateral)
VZ_SPIRAL = 5.0      # mm/s radial expansion
OMEGA = 2 * np.pi * 0.6


def run_episode(delay_steps, use_admittance, use_spiral, force_sigma,
                use_vertical_admittance, r0, theta0, rng,
                alpha=ALPHA, spiral_gain=1.0, use_contact_latch=False,
                latch_sigma=0.0, latch_confirm=1):
    r_init = np.array([r0 * np.cos(theta0), r0 * np.sin(theta0)])
    r = r_init.copy()
    z = 5.0
    depth = 0.0
    k = 0
    jammed = False
    latched = False
    latch_count = 0
    captured = False
    max_force = 0.0
    fbuf = [np.zeros(2)] * (delay_steps + 1)
    t = 0.0
    for step in range(STEPS):
        t = step * DT
        if captured:
            z -= VZ * DT
            depth = max(0.0, -z)
            if depth >= 20.0:
                return {"success": True, "reason": "inserted", "time": t,
                        "max_force": max_force, "r_final": float(np.linalg.norm(r))}
            continue
        # nominal lateral plan: the policy does NOT know where the hole is; it
        # holds its own (possibly wrong) estimate, optionally sweeping around it.
        if use_spiral:
            amp = spiral_gain * VZ_SPIRAL * t
            ang = OMEGA * t
            r_plan = r_init + np.array([amp * np.cos(ang), amp * np.sin(ang)])
        else:
            r_plan = r_init.copy()
        # contact / chamfer force (from current state)
        F_lat_now = np.zeros(2)
        in_chamfer = C < np.linalg.norm(r) < R
        if in_chamfer and z <= 0.0:
            nr = r / (np.linalg.norm(r) + 1e-9)
            F_lat_now = -KC * (R - np.linalg.norm(r)) * nr
        # delayed noisy force estimate
        fbuf.append(F_lat_now.copy())
        f_est = fbuf[-1 - delay_steps].copy()
        if force_sigma > 0:
            f_est = f_est + rng.normal(0.0, force_sigma, 2)
        # lateral command
        if use_contact_latch:
            # noisy, delayed contact detector: confirm over several frames
            cobs = np.linalg.norm(F_lat_now)
            if latch_sigma > 0:
                cobs += rng.normal(0.0, latch_sigma)
            if cobs > F_LATCH:
                latch_count += 1
            else:
                latch_count = 0
            if latched or latch_count >= latch_confirm:
                # persistent latch: once contact is made, stop the blind search
                # and let admittance center; do not snap back to the spiral.
                latched = True
                r_plan = r.copy()
        r_cmd = r_plan.copy()
        if use_admittance:
            r_cmd = r_cmd + alpha * f_est
        # lateral second-order-ish relaxation
        dr = (r_cmd - r) * (DT / TAU_R)
        if not jammed:
            r = r + dr
        # vertical integration: inside clearance there is no table contact
        if np.linalg.norm(r) <= C:
            z -= VZ * DT
            depth = max(0.0, -z)
            captured = True
            if depth >= 20.0:
                return {"success": True, "reason": "inserted", "time": t,
                        "max_force": max_force, "r_final": float(np.linalg.norm(r))}
        else:
            Fz = KZ * max(0.0, -z)
            if z > 0.0:
                z -= VZ * DT
                if z < 0.0:
                    z = 0.0
                Fz = 0.0
            else:
                v_eff = VZ
                if use_vertical_admittance:
                    v_eff = VZ * float(np.clip((F_JAM - Fz) / (F_JAM - F_STOP), -1.0, 1.0))
                elif Fz > F_STOP:
                    v_eff = 0.0
                z -= v_eff * DT
                Fz = KZ * max(0.0, -z)
                max_force = max(max_force, Fz)
                depth = max(0.0, -z)
                jammed = Fz > F_BLOCK
                if Fz > F_MAX:
                    return {"success": False, "reason": "force", "time": t,
                            "max_force": max_force, "r_final": float(np.linalg.norm(r))}
                if jammed and not use_admittance:
                    return {"success": False, "reason": "jam", "time": t,
                            "max_force": max_force, "r_final": float(np.linalg.norm(r))}
    return {"success": False, "reason": "timeout", "time": t,
            "max_force": max_force, "r_final": float(np.linalg.norm(r))}


def monte_carlo(n=1500, seed=0, **kw):
    rng = np.random.default_rng(seed)
    results = []
    for _ in range(n):
        r0 = 15.0 * np.sqrt(rng.random())
        th = rng.random() * 2 * np.pi
        results.append(run_episode(r0=r0, theta0=th, rng=rng, **kw))
    succ = np.array([r["success"] for r in results])
    times = np.array([r["time"] for r in results])
    forces = np.array([r["max_force"] for r in results])
    reasons = {}
    for r in results:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    return {"n": n, "success": float(succ.mean()),
            "mean_time_s": float(times.mean()),
            "mean_max_force_N": float(forces.mean()),
            "p95_max_force_N": float(np.percentile(forces, 95)),
            "reasons": reasons}


def main():
    configs = {
        "A_rigid": dict(delay_steps=0, use_admittance=False, use_spiral=False,
                        force_sigma=0.0, use_vertical_admittance=False),
        "B_rigid_spiral": dict(delay_steps=0, use_admittance=False, use_spiral=True,
                               force_sigma=0.0, use_vertical_admittance=False),
        "C_admittance_only": dict(delay_steps=3, use_admittance=True, use_spiral=False,
                                  force_sigma=0.5, use_vertical_admittance=True),
        "D_admittance_spiral": dict(delay_steps=3, use_admittance=True, use_spiral=True,
                                    force_sigma=0.5, use_vertical_admittance=True,
                                    use_contact_latch=True),
        "E_admittance_spiral_delay6": dict(delay_steps=6, use_admittance=True, use_spiral=True,
                                           force_sigma=1.0, use_vertical_admittance=True,
                                           use_contact_latch=True),
        "F_admittance_spiral_gain06": dict(delay_steps=3, use_admittance=True, use_spiral=True,
                                           force_sigma=0.5, use_vertical_admittance=True,
                                           use_contact_latch=True, alpha=0.6),
        "G_noisy_latch": dict(delay_steps=3, use_admittance=True, use_spiral=True,
                              force_sigma=0.5, use_vertical_admittance=True,
                              use_contact_latch=True, latch_sigma=1.0, latch_confirm=3),
        "H_very_noisy_latch": dict(delay_steps=3, use_admittance=True, use_spiral=True,
                                   force_sigma=0.5, use_vertical_admittance=True,
                                   use_contact_latch=True, latch_sigma=2.0, latch_confirm=5),
    }
    out = {}
    for name, kw in configs.items():
        # average over 5 seeds to reduce Monte-Carlo noise
        runs = [monte_carlo(n=600, seed=s, **kw) for s in range(5)]
        out[name] = {
            "success_mean": float(np.mean([r["success"] for r in runs])),
            "success_std": float(np.std([r["success"] for r in runs])),
            "mean_time_s": float(np.mean([r["mean_time_s"] for r in runs])),
            "mean_max_force_N": float(np.mean([r["mean_max_force_N"] for r in runs])),
            "p95_max_force_N": float(np.mean([r["p95_max_force_N"] for r in runs])),
            "reasons": runs[0]["reasons"],
        }
        print(name, json.dumps(out[name], ensure_ascii=False))
    # delay / noise sweep for the full system
    sweep = {}
    for d in (0, 1, 2, 3, 4, 6, 8):
        runs = [monte_carlo(n=400, seed=s, delay_steps=d, use_admittance=True,
                            use_spiral=True, force_sigma=0.8,
                            use_vertical_admittance=True, use_contact_latch=True) for s in range(3)]
        sweep[d] = {"success": float(np.mean([r["success"] for r in runs])),
                    "force": float(np.mean([r["mean_max_force_N"] for r in runs]))}
    out["delay_sweep"] = sweep
    print("delay_sweep", json.dumps(sweep, ensure_ascii=False))
    # detector-noise sweep for the contact latch
    det = {}
    for sig in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        runs = [monte_carlo(n=400, seed=s, delay_steps=3, use_admittance=True,
                            use_spiral=True, force_sigma=0.5,
                            use_vertical_admittance=True, use_contact_latch=True,
                            latch_sigma=sig, latch_confirm=3) for s in range(3)]
        det[sig] = {"success": float(np.mean([r["success"] for r in runs])),
                    "force": float(np.mean([r["mean_max_force_N"] for r in runs]))}
    out["detector_sweep"] = det
    print("detector_sweep", json.dumps(det, ensure_ascii=False))
    json.dump(out, open("exp/compliance_sim_results.json", "w"), indent=1, ensure_ascii=False)
    print("wrote exp/compliance_sim_results.json")


if __name__ == "__main__":
    main()
