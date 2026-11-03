"""Synthetic mechanism check for MECHA (round 16).

NOT benchmark evidence. Isolates three questions on a 2-link arm model whose
joints are driven by a brushed-brushless-style position servo (PD + torque
limit + friction), with gravity and inertia known only approximately:

  A. Sensorless external-torque estimation (generalized-momentum observer):
     can a momentum observer recover the contact torque from joint positions
     only, better than the raw servo error q* - q?
  B. Sensorless admittance: can modulating the commanded position by the
     *estimated* external torque reduce peak contact force without an F/T
     sensor and without an oracle?
  C. Predictive kinematic shield: over a predicted action chunk, can a
     swept-capsule / potential-field shield cut two-arm collisions?

Generative model (declared, not fit):
  - 2-link planar arm; standard Lagrangian dynamics; gravity along -y.
  - inner servo: tau = clip(Kp (q* - q) - Kd qdot, -taumax, taumax)
    (no gravity feedforward -- a realistic stiff position servo).
  - friction: -b qdot - c sign(qdot).
  - contact: vertical wall at x = x_wall; force F = -K_w (x_ee - x_wall) on EE
    when penetrating; joint torque tau_ext = J^T F.
  - observer knows dynamics up to a gain/inertia mismatch (declared) and
    reads noisy q, qdot.
  - metrics: contact-detection AUROC and median detection delay (A),
    peak contact force (B), collision rate (C).
"""
import json
import math
import numpy as np

OUT = "/home/runner/work/xuen/xuen/workspace/exp/mecha_results.json"
RNG = np.random.default_rng(20261103)

# ----------------------------------------------------------------------------
# 2-link planar arm
# ----------------------------------------------------------------------------
M1, M2 = 1.6, 1.0
L1, L2 = 0.32, 0.26
LC1, LC2 = L1 / 2.0, L2 / 2.0
I1, I2 = 0.012, 0.008
GR = 9.81


def mass_matrix(q):
    c2 = math.cos(q[1])
    m11 = M1 * LC1**2 + M2 * (L1**2 + LC2**2 + 2 * L1 * LC2 * c2) + I1 + I2
    m12 = M2 * (LC2**2 + L1 * LC2 * c2) + I2
    m22 = M2 * LC2**2 + I2
    return np.array([[m11, m12], [m12, m22]])


def coriolis_T_dq(q, dq):
    # C^T(q,dq) dq with h = M2 L1 LC2 sin q2
    h = M2 * L1 * LC2 * math.sin(q[1])
    return np.array([0.0, -h * (dq[0] + dq[1]) * dq[0]])


def gravity(q):
    q1, q2 = q
    g1 = (M1 * LC1 + M2 * L1) * GR * math.cos(q1) + M2 * LC2 * GR * math.cos(q1 + q2)
    g2 = M2 * LC2 * GR * math.cos(q1 + q2)
    return np.array([g1, g2])


def jacobian(q):
    q1, q2 = q
    s1, s12 = math.sin(q1), math.sin(q1 + q2)
    c1, c12 = math.cos(q1), math.cos(q1 + q2)
    return np.array([[-L1 * s1 - L2 * s12, -L2 * s12],
                     [L1 * c1 + L2 * c12, L2 * c12]])


def fk(q):
    q1, q2 = q
    return np.array([L1 * math.cos(q1) + L2 * math.cos(q1 + q2),
                     L1 * math.sin(q1) + L2 * math.sin(q1 + q2)])


# ----------------------------------------------------------------------------
# Plant + servo
# ----------------------------------------------------------------------------
KP = np.array([90.0, 70.0])
KD = np.array([9.0, 7.0])
TAUMAX = 35.0
B_FRIC = 0.6
C_FRIC = 0.5
DT = 1.0 / 300.0
SUB = 10                      # 30 Hz control
WALL_X = 0.46
K_WALL = 1200.0


def plant_step(q, dq, q_star, tau_ext):
    e = q_star - q
    tau = np.clip(KP * e - KD * dq, -TAUMAX, TAUMAX)
    tau = tau - B_FRIC * dq - C_FRIC * np.tanh(dq * 50.0)
    Mq = mass_matrix(q)
    rhs = tau + tau_ext - coriolis_T_dq(q, dq) - gravity(q)
    ddq = np.linalg.solve(Mq, rhs)
    return q + dq * DT, dq + ddq * DT, tau


def wall_torque(q):
    x, _ = fk(q)
    if x <= WALL_X:
        return np.zeros(2), 0.0
    f = -K_WALL * (x - WALL_X)
    return jacobian(q)[0] * f, f        # J^T [f,0]


# ----------------------------------------------------------------------------
# Generalized-momentum observer (De Luca & Mattone 2005)
#   beta = int (tau + C^T dq - g + r) dt ;  r = Ko (M dq - beta)
#   => rdot = Ko (tau_ext - r)
# Observer uses a *mismatched* dynamics model (declared) to test robustness.
# ----------------------------------------------------------------------------
K_O = np.array([18.0, 18.0])


class Observer:
    def __init__(self, q0, dq0, gain_mismatch=0.12, inertia_mismatch=0.10):
        self.gm = gain_mismatch
        self.im = inertia_mismatch
        self.beta = mass_matrix(q0) @ dq0
        self.r = np.zeros(2)

    def _tau_hat(self, q, dq, q_star):
        # inferred controller torque with mismatched gains; no friction term
        return np.clip((KP * (1 - self.gm)) * (q_star - q)
                       - (KD * (1 - self.gm)) * dq, -TAUMAX, TAUMAX)

    def update(self, q, dq, q_star):
        tau = self._tau_hat(q, dq, q_star)
        integrand = tau + coriolis_T_dq(q, dq) - gravity(q) + self.r
        self.beta = self.beta + integrand * DT
        p = (mass_matrix(q) * (1 + self.im)) @ dq
        self.r = K_O * (p - self.beta)
        return self.r.copy()


def run_observer_episode(seed, press=True):
    """Approach wall, then press. Return arrays + observer residuals."""
    rng = np.random.default_rng(seed)
    q = np.array([0.9, -0.8]) + rng.normal(0, 0.02, 2)
    dq = np.zeros(2)
    obs = Observer(q.copy(), dq.copy())
    # desired trajectory: absolute ramp into the wall, then keep pressing
    q0 = q.copy()
    q_goal = np.array([0.15, 0.05])
    steps = 240
    Q, DQ, E, R, TEXT, TAU, CONTACT = [], [], [], [], [], [], []
    for k in range(steps):
        frac = min(1.0, k / 140.0)
        q_star = q0 + (q_goal - q0) * frac
        for _ in range(SUB):
            te, f = wall_torque(q)
            q, dq, tau = plant_step(q, dq, q_star, te)
        # noisy measurements
        q_meas = q + rng.normal(0, 0.0015, 2)
        dq_meas = dq + rng.normal(0, 0.01, 2)
        r = obs.update(q_meas, dq_meas, q_star)
        e = q_star - q_meas
        te, f = wall_torque(q)
        Q.append(q.copy()); DQ.append(dq.copy()); E.append(e.copy())
        R.append(r.copy()); TEXT.append(te.copy()); TAU.append(tau.copy())
        CONTACT.append(1.0 if abs(f) > 1.0 else 0.0)
    return (np.array(Q), np.array(DQ), np.array(E), np.array(R),
            np.array(TEXT), np.array(TAU), np.array(CONTACT))


def auroc(scores, labels):
    scores, labels = np.asarray(scores), np.asarray(labels)
    pos, neg = scores[labels > 0.5], scores[labels < 0.5]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(len(order), float)
    ranks[order] = np.arange(1, len(order) + 1)
    rp = ranks[:len(pos)].sum()
    return (rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def detection_delay(score, contact, thr):
    idx = np.where(contact > 0.5)[0]
    if len(idx) == 0:
        return float("nan")
    onset = idx[0]
    after = np.where(score[onset:] > thr)[0]
    return float("nan") if len(after) == 0 else float(after[0])


# ============================================================================
# Part A: observer vs servo error for contact detection
# ============================================================================
def part_A(n=60):
    a_obs, a_err, delays = [], [], []
    for s in range(n):
        Q, DQ, E, R, TEXT, TAU, CT = run_observer_episode(1000 + s)
        sc_obs = np.linalg.norm(R, axis=1)
        sc_err = np.linalg.norm(E, axis=1)
        a_obs.append(auroc(sc_obs, CT))
        a_err.append(auroc(sc_err, CT))
        # threshold at 95th pct of pre-contact score
        pre = sc_obs[CT < 0.5]
        thr = np.quantile(pre, 0.95) if len(pre) else np.inf
        delays.append(detection_delay(sc_obs, CT, thr))
    return {
        "auroc_observer": float(np.nanmean(a_obs)),
        "auroc_observer_std": float(np.nanstd(a_obs)),
        "auroc_servo_error": float(np.nanmean(a_err)),
        "auroc_servo_error_std": float(np.nanstd(a_err)),
        "median_detect_delay_steps": float(np.nanmedian(delays)),
        "n_episodes": n,
    }


# ============================================================================
# Part B: sensorless admittance via estimated torque
# ============================================================================
def run_admittance(mode, seed):
    """mode in {stiff, adm_est, adm_oracle}; returns peak |contact force|, time."""
    rng = np.random.default_rng(seed)
    q = np.array([0.9, -0.8]) + rng.normal(0, 0.02, 2)
    dq = np.zeros(2)
    obs = Observer(q.copy(), dq.copy())
    q_goal = np.array([0.12, 0.02])
    g_adm = 0.020
    peak_f, t_contact, force = 0.0, None, 0.0
    lp = np.zeros(2)
    te_prev = np.zeros(2)
    for k in range(300):
        q_nom = q + (q_goal - q) * 0.03
        if mode == "stiff":
            q_star = q_nom
        else:
            if mode == "adm_est":
                lp = 0.7 * lp + 0.3 * obs.r  # filtered estimate
                te_used = lp
            else:
                te_used = te_prev           # oracle: true tau_ext (1 step old)
            # task-space admittance: yield along the estimated external force
            J = jacobian(q)
            try:
                F_est = np.linalg.solve(J.T, te_used)
                dq_adm = np.linalg.solve(J, g_adm * F_est)
            except np.linalg.LinAlgError:
                dq_adm = np.zeros(2)
            dq_adm = np.clip(dq_adm, -0.03, 0.03)
            q_star = q_nom + dq_adm
        for _ in range(SUB):
            te, f = wall_torque(q)
            q, dq, tau = plant_step(q, dq, q_star, te)
        q_meas = q + rng.normal(0, 0.0015, 2)
        dq_meas = dq + rng.normal(0, 0.01, 2)
        obs.update(q_meas, dq_meas, q_star)
        te, f = wall_torque(q)
        te_prev = te
        force = abs(f)
        if force > 1.0 and t_contact is None:
            t_contact = k
        peak_f = max(peak_f, force)
    return peak_f, (t_contact if t_contact is not None else 300)


def part_B(n=40):
    res = {"stiff": [], "adm_est": [], "adm_oracle": []}
    tsec = {"stiff": [], "adm_est": [], "adm_oracle": []}
    for s in range(n):
        for mode in res:
            pf, tc = run_admittance(mode, 5000 + s)
            res[mode].append(pf); tsec[mode].append(tc)
    out = {}
    stiff = float(np.mean(res["stiff"]))
    for mode in res:
        pf = float(np.mean(res[mode]))
        out[f"peak_force_{mode}"] = pf
        out[f"peak_force_reduction_{mode}_pct"] = float(100 * (stiff - pf) / stiff)
        out[f"contact_time_{mode}_steps"] = float(np.mean(tsec[mode]))
    out["n_episodes"] = n
    return out


# ============================================================================
# Part C: predictive kinematic shield (two arms, swept capsule)
# ============================================================================
def seg_seg_dist(p1, p2, p3, p4):
    """min distance between segment p1p2 and segment p3p4."""
    d1, d2 = p2 - p1, p4 - p3
    r = p1 - p3
    a, e, f = d1 @ d1, d2 @ d2, d2 @ r
    c = d1 @ r
    b = d1 @ d2
    denom = a * e - b * b
    s = 0.0 if denom < 1e-9 else np.clip((b * f - c * e) / denom, 0, 1)
    t = np.clip((b * s + f) / e if e > 1e-9 else 0.0, 0, 1)
    s = np.clip((b * t - c) / a if a > 1e-9 else 0.0, 0, 1)
    return float(np.linalg.norm((p1 + s * d1) - (p3 + t * d2)))


def arm_points(q):
    q1, q2 = q
    p = np.array([0.0, 0.0])
    e1 = p + np.array([L1 * math.cos(q1), L1 * math.sin(q1)])
    e2 = e1 + np.array([L2 * math.cos(q1 + q2), L2 * math.sin(q1 + q2)])
    return p, e1, e2


def arm_min_dist(qa, qb):
    pa = arm_points(qa); pb = arm_points(qb)
    return min(seg_seg_dist(pa[0], pa[1], pb[0], pb[1]),
               seg_seg_dist(pa[0], pa[1], pb[1], pb[2]),
               seg_seg_dist(pa[1], pa[2], pb[0], pb[1]),
               seg_seg_dist(pa[1], pa[2], pb[1], pb[2]))


RADIUS = 0.055
MARGIN = 2.0 * RADIUS


def part_C(n=400, horizon=10, v=0.02, dt=1.0, steps=80):
    """Two moving bodies; body B crosses body A's region. The shield predicts
    the swept distance over `horizon` steps and pauses A when the future
    clearance drops below MARGIN. Collision = true clearance < MARGIN."""
    coll_plain, coll_shield = 0, 0
    wait_sum, n_shield = 0.0, 0
    for s in range(n):
        rng = np.random.default_rng(7000 + s)
        pa = np.array([rng.uniform(0.0, 0.1), rng.uniform(-0.15, 0.15)])
        goal = np.array([rng.uniform(0.55, 0.75), rng.uniform(-0.15, 0.15)])
        # B sweeps across the corridor from top to bottom (or reverse)
        pb = np.array([rng.uniform(0.25, 0.5), 0.45 * rng.choice([-1, 1])])
        vb = np.array([rng.uniform(-0.2, 0.2), -0.02 * np.sign(pb[1])])

        def run(shield):
            nonlocal wait_sum, n_shield
            pa_c, pb_c = pa.copy(), pb.copy()
            collided = False
            waited = 0
            for k in range(steps):
                step_a = (goal - pa_c)
                n_ = np.linalg.norm(step_a)
                step_a = v * step_a / (n_ + 1e-9)
                step_b = vb * dt
                if shield:
                    pa_p, pb_p = pa_c.copy(), pb_c.copy()
                    dmin = np.inf
                    for _ in range(horizon):
                        pa_p = pa_p + step_a
                        pb_p = pb_p + step_b
                        dmin = min(dmin, np.linalg.norm(pa_p - pb_p))
                    if dmin < MARGIN:
                        step_a = step_a * float(np.clip((dmin - 0.3 * MARGIN)
                                                        / (0.7 * MARGIN), 0.0, 1.0))
                        waited += 1
                pa_c = pa_c + step_a
                pb_c = pb_c + step_b
                if np.linalg.norm(pa_c - pb_c) < MARGIN:
                    collided = True
            if shield:
                wait_sum += waited
                n_shield += 1
            return collided

        coll_plain += run(False)
        coll_shield += run(True)
    return {
        "collision_rate_plain": coll_plain / n,
        "collision_rate_shield": coll_shield / n,
        "collision_reduction_pct": 100 * (coll_plain - coll_shield) / max(1, coll_plain),
        "mean_steps_waited_when_shielded": wait_sum / max(1, n_shield),
        "n": n, "horizon": horizon, "margin_m": MARGIN,
    }


if __name__ == "__main__":
    out = {"part_A_observer": part_A(), "part_B_admittance": part_B(),
           "part_C_shield": part_C()}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
