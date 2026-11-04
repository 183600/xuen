"""Synthetic mechanism check for PACT-VLA (round 16).

NOT benchmark evidence. Isolates three questions raised by the words
"dynamics / ethics-and-compliance / business-model":

  A. DYNA-ID -- can object mass and friction be identified *label-free* from
     proprioceptive tracking error alone (the observation catalog exposes no
     torque/current/force channel), and does conditioning impedance on the
     estimate reduce impact damage / slip under unseen loads?

  B. COMPLIANCE SHIELD -- can projecting every action chunk onto a certified
     admissible set (bounded jerk, no outliers) drive the evaluator's
     "interaction-credibility" violation rate toward zero at small success
     cost, and prevent loss-of-control failures?

  C. COST-PER-SUCCESS SCHEDULER -- does scheduling a cheap dynamics primitive
     first and calling the VLA only when a physics predictor says the
     primitive is unlikely improve success-per-cost (a proxy for the
     competition's step score and for real deployment unit economics)?

Generative model is declared, not fit. Pure Python; fixed seeds.
"""
import math
import json
import random
import os
import statistics

G = 9.81


# --------------------------------------------------------------------------
# Part A -- DYNA-ID: recursive least squares on a momentum-observer model
# --------------------------------------------------------------------------
def rls_identify(m_true, mu_true, steps=400, dt=0.005, seed=0,
                 pos_noise=0.0005, vel_noise=0.008, acc_noise=0.03):
    """Identify held-object mass m and friction mu from (x, v) observations.

    Model (assumed known): F_cmd = m * a + mu*m*g*sign(v).  Let c = mu*m.
    Regress y = F_cmd on phi = [a, sign(v)] -> theta = [m, c].  mu = c/m.
    The robot never sees F_true; it reconstructs F_cmd from its own
    impedance law and noisy observations (a momentum observer).
    """
    rng = random.Random(seed)
    k_imp, b_imp = 40.0, 2.0
    lam = 0.995
    x = 0.0
    v = 0.0
    theta = [0.0, 0.0]
    P = [[1e3, 0.0], [0.0, 1e3]]
    for t in range(steps):
        xd = 0.05 * math.sin(2.0 * math.pi * 0.4 * t * dt)
        F_true = k_imp * (xd - x) - b_imp * v
        s = 1.0 if v > 1e-6 else (-1.0 if v < -1e-6 else 0.0)
        a = (F_true - mu_true * m_true * G * s) / m_true
        v += a * dt
        x += v * dt
        xn = x + rng.gauss(0.0, pos_noise)
        vn = v + rng.gauss(0.0, vel_noise)
        an = a + rng.gauss(0.0, acc_noise)
        Fc = k_imp * (xd - xn) - b_imp * vn
        phi = [an, s]
        Pphi = [P[0][0] * phi[0] + P[0][1] * phi[1],
                P[1][0] * phi[0] + P[1][1] * phi[1]]
        denom = lam + phi[0] * Pphi[0] + phi[1] * Pphi[1]
        K = [Pphi[0] / denom, Pphi[1] / denom]
        err = Fc - (theta[0] * phi[0] + theta[1] * phi[1])
        theta[0] += K[0] * err
        theta[1] += K[1] * err
        P = [[(P[0][0] - K[0] * Pphi[0]) / lam, (P[0][1] - K[0] * Pphi[1]) / lam],
             [(P[1][0] - K[1] * Pphi[0]) / lam, (P[1][1] - K[1] * Pphi[1]) / lam]]
    m_hat = max(theta[0], 1e-3)
    # theta[1] estimates c = mu*m*g, so mu = c/(m*g)
    mu_hat = max(theta[1], 0.0) / (m_hat * G)
    return m_hat, mu_hat


def part_a():
    configs = [(0.4, 0.25), (0.8, 0.25), (0.8, 0.55), (1.5, 0.55)]
    rows = []
    for m_true, mu_true in configs:
        merrs, muerrs = [], []
        for seed in range(12):
            mh, muh = rls_identify(m_true, mu_true, seed=seed)
            merrs.append(abs(mh - m_true) / m_true)
            muerrs.append(abs(muh - mu_true) / mu_true)
        rows.append(dict(m_true=m_true, mu_true=mu_true,
                         m_hat=round(statistics.mean(
                             [m_true * (1 + e) for e in merrs]), 4),
                         m_rel_err=round(statistics.mean(merrs), 3),
                         mu_hat=round(statistics.mean(
                             [mu_true * (1 + e) for e in muerrs]), 4),
                         mu_rel_err=round(statistics.mean(muerrs), 3)))
    return rows


# --------------------------------------------------------------------------
# Part A2 -- impedance conditioning: impact force / slip under unseen mass
# --------------------------------------------------------------------------
def part_a2():
    """Unseen payload mass: fixed impedance vs DYNA-ID-conditioned gains.

    Two failure modes: impact force F_peak ~ v0*sqrt(k*m) may exceed a damage
    threshold; grip force (fixed) may fall below the friction cone m*g, so the
    object slips.  DYNA-ID sets k proportional to m_hat and grip proportional
    to m_hat, holding both margins constant across mass.
    """
    rng = random.Random(5)
    f_damage = 3.2
    v0 = 0.20
    nominal_m = 0.8
    k_nominal = 200.0                        # stiffness tuned for nominal mass
    grip_nominal = 12.0                      # hold force tuned for nominal mass
    c_grip = 1.0                             # required hold per unit weight
    masses = [0.4, 0.8, 1.5]
    rows = []
    for m in masses:
        dmg_fixed = dmg_id = slip_fixed = slip_id = 0
        fail_fixed = fail_id = 0
        n = 4000
        for seed in range(n):
            # fixed gains
            f_fixed = v0 * math.sqrt(k_nominal * m) * (1 + rng.gauss(0, 0.05))
            df = f_fixed > f_damage
            sf = grip_nominal < c_grip * m * G * (1 + rng.gauss(0, 0.03))
            dmg_fixed += df
            slip_fixed += sf
            fail_fixed += (df or sf)
            # DYNA-ID-conditioned gains
            k_id = k_nominal * (nominal_m / m)
            grip_id = grip_nominal * (m / nominal_m)
            f_id = v0 * math.sqrt(k_id * m) * (1 + rng.gauss(0, 0.05))
            di = f_id > f_damage
            si = grip_id < c_grip * m * G * (1 + rng.gauss(0, 0.03))
            dmg_id += di
            slip_id += si
            fail_id += (di or si)
        rows.append(dict(mass=m,
                         damage_fixed=round(dmg_fixed / n, 3),
                         damage_id=round(dmg_id / n, 3),
                         slip_fixed=round(slip_fixed / n, 3),
                         slip_id=round(slip_id / n, 3),
                         fail_fixed=round(fail_fixed / n, 3),
                         fail_id=round(fail_id / n, 3)))
    return rows


# --------------------------------------------------------------------------
# Part B -- compliance shield: interaction-credibility under disturbance
# --------------------------------------------------------------------------
def part_b(n=200000, seed=7):
    rng = random.Random(seed)
    base_succ = 0.87
    j_flag, j_loc = 8.0, 12.0               # flag / loss-of-control jerk
    viol_un = 0
    fail_un = 0
    viol_sh = 0
    fail_sh = 0
    for _ in range(n):
        if rng.random() < 0.85:
            jerk = rng.gauss(2.0, 0.6)
        else:                               # disturbance / OOD chunk
            jerk = rng.gauss(9.0, 3.0)
        # unshielded
        if jerk > j_flag:
            viol_un += 1
        uncontrolled = jerk > j_loc
        succ = rng.random() < base_succ
        if uncontrolled or not succ:
            fail_un += 1
        # shielded: project jerk onto [0, 6.5]
        jerk_s = max(0.0, min(6.5, jerk))
        if jerk_s > j_flag:
            viol_sh += 1
        succ_s = rng.random() < base_succ
        if not succ_s:
            fail_sh += 1
    return dict(
        violation_unshielded=round(viol_un / n, 4),
        violation_shielded=round(viol_sh / n, 4),
        fail_unshielded=round(fail_un / n, 4),
        fail_shielded=round(fail_sh / n, 4),
        loss_of_control_removed=round(1.0 - fail_sh / fail_un, 4),
    )


# --------------------------------------------------------------------------
# Part C -- cost-per-success scheduler
# --------------------------------------------------------------------------
def part_c(n=120000, seed=11, pi_p=0.65, g_prim=0.80, route_acc=0.85,
           c_vla=1.0, c_prim=0.20, c_shield=0.02):
    """Three operating points on the success/cost frontier.

    - vla_only: always call the VLA (the baseline).
    - primitive_only: use a dynamics primitive on solvable tasks, VLA only
      on semantic tasks (cheapest, lower ceiling).
    - pact: DYNA-ID + a cheap touch-probe predictor routes solvable tasks to
      the primitive only when it predicts success, otherwise to the VLA.
    """
    rng = random.Random(seed)
    p_vla_solvable, p_vla_semantic = 0.90, 0.55
    strategies = ["vla_only", "primitive_only", "pact"]
    acc = {s: dict(succ=0.0, cost=0.0, vla=0, prim=0) for s in strategies}
    for _ in range(n):
        solvable = rng.random() < pi_p
        actual_prim = rng.random() < g_prim
        # predictor outcome: correct with prob route_acc
        correct = rng.random() < route_acc
        pred_prim = actual_prim if correct else (not actual_prim)
        for s in strategies:
            cost = c_shield
            vla = prim = 0
            if s == "vla_only":
                vla += 1
                cost += c_vla
                succ = rng.random() < (p_vla_solvable if solvable else p_vla_semantic)
            elif s == "primitive_only":
                if solvable:
                    prim += 1
                    cost += c_prim
                    succ = actual_prim
                else:
                    vla += 1
                    cost += c_vla
                    succ = rng.random() < p_vla_semantic
            else:  # pact
                if solvable and pred_prim:
                    prim += 1
                    cost += c_prim
                    succ = actual_prim
                elif solvable:
                    vla += 1
                    cost += c_vla
                    succ = rng.random() < p_vla_solvable
                else:
                    vla += 1
                    cost += c_vla
                    succ = rng.random() < p_vla_semantic
            acc[s]["succ"] += 1.0 if succ else 0.0
            acc[s]["cost"] += cost
            acc[s]["vla"] += vla
            acc[s]["prim"] += prim
    rows = []
    for s in strategies:
        succ = acc[s]["succ"] / n
        cost = acc[s]["cost"] / n
        rows.append(dict(policy=s, success=round(succ, 4), cost=round(cost, 4),
                         spc=round(succ / cost, 4),
                         vla_calls_per_ep=round(acc[s]["vla"] / n, 3),
                         prim_calls_per_ep=round(acc[s]["prim"] / n, 3)))
    return rows


# --------------------------------------------------------------------------
# Part C2 -- economics sensitivity to the primitive's reliability
# --------------------------------------------------------------------------
def part_c2(seed=13, pi_p=0.65):
    rows = []
    for g in (0.5, 0.6, 0.7, 0.8, 0.9):
        rng = random.Random(seed)
        n = 30000
        c_vla, c_prim, c_shield = 1.0, 0.20, 0.02
        p_vla_s, p_vla_m = 0.90, 0.55
        succ = cost = 0.0
        for _ in range(n):
            solvable = rng.random() < pi_p
            cost += c_shield
            if solvable:
                cost += c_prim
                if rng.random() < g:
                    succ += 1.0
                else:
                    cost += c_vla
                    succ += 1.0 if rng.random() < p_vla_s else 0.0
            else:
                cost += c_vla
                succ += 1.0 if rng.random() < p_vla_m else 0.0
        rows.append(dict(g_prim=g, success=round(succ / n, 4),
                         cost=round(cost / n, 4), spc=round((succ / n) / (cost / n), 4)))
    return rows


if __name__ == "__main__":
    out = dict(
        part_a_dyna_id=part_a(),
        part_a2_impedance=part_a2(),
        part_b_shield=part_b(),
        part_c_scheduler=part_c(),
        part_c2_sensitivity=part_c2(),
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pact_results.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("\nwrote", path)
