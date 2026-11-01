"""BRACE toy kinematic checks (Round 13).

Not a physics simulator and not a real-robot experiment.  It checks:
  A1 common-mode invariance (independent absolute servo vs relative-frame servo)
  A2 sensitivity to anchor/grasp-transform noise
  B  delay stability boundary for e_{k+1}=e_k-a e_{k-d}
  C  CBF safety filter on a 3D point robot
  D  handover arithmetic (closed form + small Monte Carlo)

Run:  workspace/.venv/bin/python workspace/exp/brace_sim.py
"""
import numpy as np
from scipy.spatial.transform import Rotation as Rot

rng = np.random.default_rng(20261101)


def mul(A, B):
    Ra, ta = A
    Rb, tb = B
    return (Ra @ Rb, ta + Ra @ tb)


def inv(T):
    R, t = T
    return (R.T, -R.T @ t)


def rel_error(T, Tstar):
    R, t = T
    Rs, ts = Tstar
    Re = R.T @ Rs
    te = R.T @ (ts - t)
    return Rot.from_matrix(Re).as_rotvec(), te


def apply_correction(T, dr, dt):
    R, t = T
    return (R @ Rot.from_rotvec(dr).as_matrix(), t + R @ dt)


def run_servo(T0, Tstar, steps=80, gain=0.6):
    T = T0
    for _ in range(steps):
        er, et = rel_error(T, Tstar)
        T = apply_correction(T, gain * er, gain * et)
    return T


def add_noise(T, sig_t, sig_r):
    R, t = T
    dR = Rot.from_rotvec(rng.normal(0, sig_r, 3)).as_matrix()
    dt = rng.normal(0, sig_t, 3)
    return (R @ dR, t + R @ dt)


I = np.eye(3)
T_A_star = (I, np.zeros(3))
T_AB_star = (I, np.array([0.05, 0.0, 0.0]))
T_B_star = mul(T_A_star, T_AB_star)


def experiment_a1(n=3000):
    err_ind_pos, err_ind_rot = [], []
    err_rel_pos, err_rel_rot = [], []
    for _ in range(n):
        rv = rng.uniform(-np.deg2rad(10), np.deg2rad(10), 3)
        tr = rng.uniform(-0.03, 0.03, 3)
        G = (Rot.from_rotvec(rv).as_matrix(), tr)
        T_A = mul(G, T_A_star)
        T_B0 = mul(G, T_B_star)

        T_B_ind = run_servo(T_B0, T_B_star)
        er, et = rel_error(mul(inv(T_A), T_B_ind), T_AB_star)
        err_ind_pos.append(np.linalg.norm(et))
        err_ind_rot.append(np.linalg.norm(er))

        T_B_rel = run_servo(T_B0, mul(T_A, T_AB_star))
        er, et = rel_error(mul(inv(T_A), T_B_rel), T_AB_star)
        err_rel_pos.append(np.linalg.norm(et))
        err_rel_rot.append(np.linalg.norm(er))

    print("A1 common-mode (N=%d, |t|<=3cm, |r|<=10deg)" % n)
    for name, arr in [("ind_pos_mm", np.array(err_ind_pos) * 1000),
                      ("ind_rot_deg", np.rad2deg(err_ind_rot)),
                      ("rel_pos_mm", np.array(err_rel_pos) * 1000),
                      ("rel_rot_deg", np.rad2deg(err_rel_rot))]:
        print("  %-12s mean=%8.3f p95=%8.3f max=%8.3f" %
              (name, arr.mean(), np.percentile(arr, 95), arr.max()))


def experiment_a2(n=500):
    print("\nA2 noise sweep (N=%d/level, common-mode 3cm/10deg)" % n)
    print("  noise_t_mm noise_r_deg | ind_pos ind_rot | rel_pos rel_rot | succ_rel")
    for sig_t, sig_r in [(0.0005, np.deg2rad(0.1)),
                         (0.001, np.deg2rad(0.2)),
                         (0.002, np.deg2rad(0.4))]:
        ind_pos, ind_rot, rel_pos, rel_rot, succ_rel = [], [], [], [], 0
        for _ in range(n):
            rv = rng.uniform(-np.deg2rad(10), np.deg2rad(10), 3)
            tr = rng.uniform(-0.03, 0.03, 3)
            G = (Rot.from_rotvec(rv).as_matrix(), tr)
            T_A_true = mul(G, T_A_star)
            T_B0_true = mul(G, T_B_star)
            T_A_meas = add_noise(T_A_true, sig_t, sig_r)
            T_B_meas0 = add_noise(T_B0_true, sig_t, sig_r)

            T_B_ind = run_servo(T_B_meas0, T_B_star)
            er, et = rel_error(mul(inv(T_A_true), T_B_ind), T_AB_star)
            ind_pos.append(np.linalg.norm(et))
            ind_rot.append(np.linalg.norm(er))

            T_B_rel = run_servo(T_B_meas0, mul(T_A_meas, T_AB_star))
            er, et = rel_error(mul(inv(T_A_true), T_B_rel), T_AB_star)
            rel_pos.append(np.linalg.norm(et))
            rel_rot.append(np.linalg.norm(er))
            succ_rel += (np.linalg.norm(et) < 0.002 and
                         np.linalg.norm(er) < np.deg2rad(1.0))
        print("  %8.2f %12.2f | %7.3f %7.3f | %7.3f %7.3f | %5d/%d" % (
            sig_t * 1000, np.rad2deg(sig_r),
            np.mean(ind_pos) * 1000, np.rad2deg(np.mean(ind_rot)),
            np.mean(rel_pos) * 1000, np.rad2deg(np.mean(rel_rot)),
            succ_rel, n))


def spectral_radius(d, a):
    if d == 0:
        coeff = [1.0, a - 1.0]
    else:
        coeff = [1.0, -1.0] + [0.0] * (d - 1) + [a]
    return float(np.max(np.abs(np.roots(coeff))))


def critical_a(d, hi=4.0):
    lo = 1e-6
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if spectral_radius(d, mid) < 1.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def experiment_b():
    print("\nB delay stability: e_{k+1}=e_k-a e_{k-d}")
    print("  d   empirical_a*   closed_form")
    for d in range(0, 11):
        a_emp = critical_a(d)
        a_cf = 2 * np.sin(np.pi / (2 * (2 * d + 1)))
        print("  %2d   %12.6f   %12.6f" % (d, a_emp, a_cf))


def cbf_filter(x, c, r, delta, u_cmd, alpha=1.5):
    diff = x - c
    dist = np.linalg.norm(diff)
    h = dist - (r + delta)
    if dist < 1e-9:
        return np.zeros(3), h
    grad = diff / dist
    viol = grad @ u_cmd + alpha * h
    if viol >= 0:
        return u_cmd, h
    return u_cmd - (viol / (grad @ grad)) * grad, h


def simulate_safety(use_filter, n_trials=2000, seed=7):
    local = np.random.default_rng(seed)
    goal = np.array([1.0, 0.0, 0.0])
    r, delta, vmax, kp, alpha, beta = 0.15, 0.05, 0.5, 1.2, 1.5, 0.9
    collisions = successes = 0
    min_dists = []
    for _ in range(n_trials):
        x = np.array([0.0, 0.0, 0.0])
        c = np.array([local.uniform(0.25, 0.80),
                      local.uniform(-0.30, 0.30),
                      local.uniform(-0.10, 0.10)])
        min_d = 1e9
        reached = False
        for _ in range(600):
            to_goal = goal - x
            if np.linalg.norm(to_goal) < 0.05:
                reached = True
                break
            u = kp * to_goal
            diff = x - c
            d = np.linalg.norm(diff)
            h = d - (r + delta)
            if h < 0.25 and d > 1e-9:
                grad = diff / d
                g_dir = to_goal / (np.linalg.norm(to_goal) + 1e-12)
                tang = g_dir - (g_dir @ grad) * grad
                nt = np.linalg.norm(tang)
                if nt > 1e-9:
                    u = u + beta * (tang / nt)
            n = np.linalg.norm(u)
            if n > vmax:
                u = u / n * vmax
            if use_filter:
                u, _ = cbf_filter(x, c, r, delta, u, alpha)
                n = np.linalg.norm(u)
                if n > vmax:
                    u = u / n * vmax
            x = x + u * 0.01
            min_d = min(min_d, np.linalg.norm(x - c))
        min_dists.append(min_d)
        collisions += (min_d < r)
        successes += reached
    md = np.array(min_dists)
    return collisions, successes, md


def experiment_c():
    print("\nC CBF safety filter (3D point robot, 2000 random obstacle placements)")
    for use_filter in [False, True]:
        col, succ, md = simulate_safety(use_filter)
        print("  use_filter=%-5s collisions=%4d/%d success=%4d/%d "
              "min_dist mean=%.1f p5=%.1f min=%.1f mm" % (
                  use_filter, col, len(md), succ, len(md),
                  md.mean() * 1000, np.percentile(md, 5) * 1000, md.min() * 1000))


def experiment_d():
    p_fail, p_h, chunks = 0.01, 0.85, 20
    s_no = (1 - p_fail) ** chunks
    s_ho = (1 - p_fail * (1 - p_h)) ** chunks
    print("\nD handover arithmetic (p_fail=%.2f, p_h=%.2f, chunks=%d)" %
          (p_fail, p_h, chunks))
    print("  closed form: no_handover=%.4f  with_handover=%.4f" % (s_no, s_ho))
    local = np.random.default_rng(11)
    n = 50000
    succ_no = succ_ho = 0
    for _ in range(n):
        ok_no = ok_ho = True
        for _ in range(chunks):
            if local.random() < p_fail:
                ok_no = False
                if local.random() > p_h:
                    ok_ho = False
        succ_no += ok_no
        succ_ho += ok_ho
    print("  Monte Carlo (%d): no_handover=%.4f  with_handover=%.4f" %
          (n, succ_no / n, succ_ho / n))


if __name__ == "__main__":
    experiment_a1()
    experiment_a2()
    experiment_b()
    experiment_c()
    experiment_d()
