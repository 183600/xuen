#!/usr/bin/env python3
"""Synthetic checks for the CLAUSE proposal.

Three experiments:
  A. contract-synchronized chunk horizon vs fixed horizons under latency
  B. phase-dependent whole-body allocation (macro/micro) in a planar reach task
  C. contract progress as an online success metric (AUROC / ECE)

The simulator is deliberately small and is *not* a UniBot digital twin.  It is a
falsification harness for the control logic, not evidence about real-robot
success rates.
"""
import json
import math
import os
import sys

import numpy as np

OUT = os.path.dirname(os.path.abspath(__file__))
DT = 1.0 / 30.0


# ---------------------------------------------------------------------------
# A. 2-D servo with chunked execution, latency, target shift, human edit
# ---------------------------------------------------------------------------

def run_servo_trial(controller, tau, delta, p_edit, seed):
    rng = np.random.default_rng(seed)
    p = np.array([0.0, 0.0])
    g = np.array([0.15, 0.05])
    bias = rng.normal(0.0, 0.008, size=2)
    edit_scheduled = rng.random() < p_edit
    t = 0.0
    t_shift = 0.80
    t_edit = 1.20
    shifted = False
    edited = False
    queue = []              # (start, end, v)
    prev_g_obs = None
    best_d = np.inf
    last_progress_t = 0.0
    recover_until = -1.0
    edit_until = -1.0
    n_chunks = 0
    n_recover = 0
    n_edit_detect = 0
    success_steps = 0
    success = False
    t_success = None
    while t < 4.0:
        # target motion happens before the next observation
        if (not shifted) and t >= t_shift:
            ang = rng.uniform(0, 2 * math.pi)
            g = g + delta * np.array([math.cos(ang), math.sin(ang)])
            shifted = True
        if (not edited) and t >= t_edit and edit_scheduled:
            ang = rng.uniform(0, 2 * math.pi)
            g = g + 0.05 * np.array([math.cos(ang), math.sin(ang)])
            edited = True

        occluded = rng.random() < 0.10
        obs_sigma = 0.0008 * (5.0 if occluded else 1.0)
        p_obs = p + rng.normal(0.0, obs_sigma, size=2)
        g_obs = g + rng.normal(0.0, obs_sigma, size=2)
        d = float(np.linalg.norm(g_obs - p_obs))

        if prev_g_obs is not None and np.linalg.norm(g_obs - prev_g_obs) > 0.02:
            n_edit_detect += 1
            edit_until = t + 0.10
        prev_g_obs = g_obs

        phase = "approach" if d > 0.08 else ("align" if d > 0.02 else "contact")
        H = controller.horizon(phase, d, occluded, t, recover_until, edit_until, tau)

        if controller.recovery and t - last_progress_t > 0.40 and t > 0.5:
            n_recover += 1
            recover_until = t + 0.10
            last_progress_t = t
            # a recovery chunk holds and takes a lower-noise look
            p_obs = p + rng.normal(0.0, 0.0003, size=2)
            g_obs = g + rng.normal(0.0, 0.0003, size=2)
            d = float(np.linalg.norm(g_obs - p_obs))
            phase = "approach" if d > 0.08 else ("align" if d > 0.02 else "contact")

        if d < best_d - 0.001:
            best_d = d
            last_progress_t = t

        if controller.name == "open30":
            vmax = 0.5
        elif phase == "approach":
            vmax = 0.5
        elif phase == "align":
            vmax = 0.15
        else:
            vmax = 0.04

        if t < edit_until or t < recover_until:
            v = np.zeros(2)
        else:
            # deadbeat plan over the chunk; the only difference across
            # controllers is H, i.e. how often the plan is refreshed.
            v = (g_obs - p_obs) / max(H * DT, 1e-6)
            v = v + bias + rng.normal(0.0, 0.006, size=2)
            if occluded and controller.name != "open30":
                v = v * 0.5
            nv = np.linalg.norm(v)
            if nv > vmax:
                v = v * (vmax / nv)
        n_chunks += 1
        queue.append((t + tau, t + tau + H * DT, v))

        # execute H steps
        for _ in range(H):
            if t >= 4.0:
                break
            active = None
            for (s, e, vv) in queue:
                if s <= t + 1e-12 < e:
                    active = vv
                    break
            if active is None:
                active = np.zeros(2)
            p = p + DT * active + rng.normal(0.0, 0.0002, size=2)

            if (not shifted) and t >= t_shift:
                ang = rng.uniform(0, 2 * math.pi)
                g = g + delta * np.array([math.cos(ang), math.sin(ang)])
                shifted = True
            if (not edited) and t >= t_edit and edit_scheduled:
                ang = rng.uniform(0, 2 * math.pi)
                g = g + 0.05 * np.array([math.cos(ang), math.sin(ang)])
                edited = True

            if np.linalg.norm(p - g) < 0.003:
                success_steps += 1
            else:
                success_steps = 0
            if success_steps >= 6:
                success = True
                t_success = t
                break
            t += DT
        if success:
            break
    return {
        "success": int(success),
        "time": float(t_success if success else 4.0),
        "final_err": float(np.linalg.norm(p - g)),
        "chunks": n_chunks,
        "recover": n_recover,
        "edit_detect": n_edit_detect,
    }


class Controller:
    def __init__(self, name):
        self.name = name
        self.recovery = name in ("clause", "servo5_rec")

    def horizon(self, phase, d, occluded, t, recover_until, edit_until, tau=0.0):
        if self.name == "open30":
            return 30
        if self.name == "servo3":
            return 3
        if self.name in ("servo5", "servo5_rec"):
            return 5
        # clause variants: phase table, then shrink the chunk as RTT grows.
        # At 150 ms the feedback period is dominated by tau, so long chunks
        # only add open-loop exposure.
        # latency floor: once RTT >= 100 ms, H=5 is the sweet spot; going
        # below 5 adds calls/noise without reducing the dominant delay.
        if tau >= 0.10:
            H = 5
        else:
            H = 8 if phase == "approach" else (5 if phase == "align" else 3)
        H = max(3, min(10, H))
        if t < edit_until or t < recover_until:
            return 3
        if occluded:
            return 3
        return H


def exp_a(n_trials=400):
    rows = []
    for tau_ms in (0, 50, 100, 150):
        for name in ("open30", "servo5", "servo5_rec", "servo3",
                     "clause_norec", "clause"):
            ctrl = Controller(name)
            res = [run_servo_trial(ctrl, tau_ms / 1000.0, 0.02, 0.30,
                                   100000 + i) for i in range(n_trials)]
            rows.append({
                "tau_ms": tau_ms,
                "controller": name,
                "success": float(np.mean([r["success"] for r in res])),
                "mean_time": float(np.mean([r["time"] for r in res])),
                "mean_err_mm": float(np.mean([r["final_err"] for r in res]) * 1000),
                "mean_chunks": float(np.mean([r["chunks"] for r in res])),
                "recover": float(np.mean([r["recover"] for r in res])),
                "edit_detect": float(np.mean([r["edit_detect"] for r in res])),
            })
    return rows


def exp_a_shift(n_trials=300):
    rows = []
    for delta in (0.0, 0.02, 0.05):
        for name in ("open30", "servo5", "clause"):
            ctrl = Controller(name)
            res = [run_servo_trial(ctrl, 0.05, delta, 0.30,
                                   200000 + i) for i in range(n_trials)]
            rows.append({
                "delta_m": delta,
                "controller": name,
                "success": float(np.mean([r["success"] for r in res])),
                "mean_err_mm": float(np.mean([r["final_err"] for r in res]) * 1000),
            })
    return rows


# ---------------------------------------------------------------------------
# B. Planar whole-body reach with phase-dependent macro/micro allocation
# ---------------------------------------------------------------------------

L0, L1, L2 = 0.10, 0.30, 0.30
WAIST_Y = 0.45
QMIN = np.array([0.0, -0.5, -2.4, -1.6])
QMAX = np.array([0.8, 0.9, 0.6, 1.0])
QDOT_MAX = np.array([0.35, 0.7, 1.2, 1.5])


def fk(q):
    xb, tw, t1, t2 = q
    waist = np.array([xb, WAIST_Y])
    shoulder = waist + L0 * np.array([math.cos(tw), math.sin(tw)])
    a1 = tw + t1
    elbow = shoulder + L1 * np.array([math.cos(a1), math.sin(a1)])
    a2 = a1 + t2
    ee = elbow + L2 * np.array([math.cos(a2), math.sin(a2)])
    return waist, shoulder, elbow, ee


def head_and_cam(q):
    _, shoulder, _, _ = fk(q)
    head = shoulder + np.array([0.0, 0.08])
    cam_ang = q[1] - 1.00
    return head, cam_ang


def bearing(q, target):
    head, cam_ang = head_and_cam(q)
    d = target - head
    return math.atan2(d[1], d[0]) - cam_ang


def jac_num(fun, q, eps=1e-6):
    f0 = np.asarray(fun(q), dtype=float)
    J = np.zeros((f0.size, len(q)))
    for i in range(len(q)):
        qp = q.copy()
        qp[i] += eps
        J[:, i] = (np.asarray(fun(qp), dtype=float) - f0) / eps
    return J


def wqp(J, v, W, lam=1e-6):
    Winv = np.diag(1.0 / W)
    A = J @ Winv @ J.T + lam * np.eye(J.shape[0])
    return Winv @ J.T @ np.linalg.solve(A, v)


def run_wb_trial(controller, target, seed):
    rng = np.random.default_rng(seed)
    q = np.array([0.30, 0.30, -1.20, 0.50])
    W = np.array([10.0, 5.0, 1.0, 1.0])
    fov = 0.70
    in_fov_steps = 0
    steps = 0
    q0 = q.copy()
    q_hist = []
    reached = False
    t_reach = None
    for k in range(120):
        _, _, _, ee = fk(q)
        dist = float(np.linalg.norm(target - ee))
        head, cam_ang = head_and_cam(q)
        brg = bearing(q, target)
        in_fov = abs(brg) < fov
        if in_fov:
            in_fov_steps += 1
        steps += 1
        q_hist.append(q.copy())
        if dist < 0.01:
            reached = True
            t_reach = k * DT
            break

        shoulder = fk(q)[1]
        reach = float(np.linalg.norm(target - shoulder))
        arm_ok = abs(L1 - L2) + 0.01 <= reach <= L1 + L2 - 0.01
        need_stage = (abs(brg) > 0.60) or (reach > 0.90 * (L1 + L2)) or (reach < abs(L1 - L2) + 0.05)

        if controller == "arm_only":
            freeze = True
            stage = False
        elif controller == "wbc_stage":
            stage = need_stage
            freeze = not stage
        elif controller == "wbc_lock":
            stage = False
            freeze = (dist < 0.03 and arm_ok)
        else:
            stage = False
            freeze = False

        if dist > 0.03:
            v_e = np.clip(3.0 * (target - ee), -0.20, 0.20)
        else:
            v_e = np.clip(2.0 * (target - ee), -0.03, 0.03)
        J_e = jac_num(lambda x: fk(x)[3], q)

        if stage:
            # macro staging: bring the target into the camera/reach sweet spot,
            # hold the arm joints, then hand control back to the arm servo.
            x_des = float(np.clip(target[0] - 0.30, 0.0, 0.80))
            head_now, _ = head_and_cam(q)
            world_bearing = math.atan2(target[1] - head_now[1],
                                       target[0] - head_now[0])
            tw_des = float(np.clip(world_bearing + 1.00, QMIN[1], QMAX[1]))
            qd = np.zeros(4)
            qd[0] = float(np.clip(2.0 * (x_des - q[0]), -QDOT_MAX[0], QDOT_MAX[0]))
            qd[1] = float(np.clip(2.0 * (tw_des - q[1]), -QDOT_MAX[1], QDOT_MAX[1]))
            # let the arm start tracking during staging; the macro move is slow
            qd[2:] = 0.5 * wqp(J_e[:, 2:], v_e, W[2:]) if dist > 0.03 else np.zeros(2)
        else:
            J_o = jac_num(lambda x: np.array([bearing(x, target)]), q)
            # observability is a keep-in-view constraint, not a centering task
            if abs(brg) > 0.50:
                v_o = np.array([-2.0 * (brg - math.copysign(0.50, brg))])
            else:
                v_o = np.array([0.0])
            v_o = np.clip(v_o, -0.6, 0.6)

            if freeze:
                qd = np.zeros(4)
                qd[2:] = wqp(J_e[:, 2:], v_e, W[2:])
            else:
                qd1 = wqp(J_e, v_e, W)
                if controller == "wbc_no_obs":
                    qd = qd1
                else:
                    Winv = np.diag(1.0 / W)
                    N = np.eye(4) - Winv @ J_e.T @ np.linalg.solve(
                        J_e @ Winv @ J_e.T + 1e-6 * np.eye(2), J_e)
                    JoN = J_o @ N
                    z = np.linalg.solve(
                        JoN.T @ JoN + 1e-6 * np.eye(4),
                        JoN.T @ (v_o - J_o @ qd1))
                    qd = qd1 + N @ z
        qd = np.clip(qd, -QDOT_MAX, QDOT_MAX)
        q = np.clip(q + DT * qd + rng.normal(0, 0.00005, size=4), QMIN, QMAX)

    _, _, _, ee = fk(q)
    if len(q_hist) >= 10:
        base_move_last = abs(q_hist[-1][0] - q_hist[-10][0]) * 1000
    else:
        base_move_last = 0.0
    return {
        "success": int(reached),
        "time": float(t_reach if reached else 4.0),
        "final_err_mm": float(np.linalg.norm(target - ee) * 1000),
        "fov_frac": float(in_fov_steps / max(steps, 1)),
        "base_move_mm": float(abs(q[0] - q0[0]) * 1000),
        "base_move_last_mm": float(base_move_last),
    }


def exp_b(n_targets=300):
    rng = np.random.default_rng(7)
    targets = []
    for _ in range(n_targets):
        x = rng.uniform(0.15, 1.05)
        y = rng.uniform(0.00, 0.25)
        targets.append(np.array([x, y]))
    rows = []
    for name in ("arm_only", "wbc_no_obs", "wbc", "wbc_lock", "wbc_stage"):
        res = [run_wb_trial(name, tg, 300000 + i)
               for i, tg in enumerate(targets)]
        rows.append({
            "controller": name,
            "success": float(np.mean([r["success"] for r in res])),
            "mean_time": float(np.mean([r["time"] for r in res])),
            "mean_err_mm": float(np.mean([r["final_err_mm"] for r in res])),
            "fov_frac": float(np.mean([r["fov_frac"] for r in res])),
            "base_move_mm": float(np.mean([r["base_move_mm"] for r in res])),
            "base_move_last_mm": float(np.mean([r["base_move_last_mm"] for r in res])),
        })
    return rows


# ---------------------------------------------------------------------------
# C. Contract progress as an online metric
# ---------------------------------------------------------------------------

def auroc(scores, labels):
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    # average ranks for ties
    sorted_scores = scores[order]
    i = 0
    while i < len(sorted_scores):
        j = i
        while j + 1 < len(sorted_scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        if j > i:
            avg = (i + j + 2) / 2.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg
        i = j + 1
    return float((ranks[labels == 1].sum() - len(pos) * (len(pos) + 1) / 2.0)
                 / (len(pos) * len(neg)))


def ece(pred, labels, n_bins=10):
    pred = np.asarray(pred, dtype=float)
    labels = np.asarray(labels, dtype=float)
    bins = np.linspace(0, 1, n_bins + 1)
    total = 0.0
    for i in range(n_bins):
        m = (pred >= bins[i]) & (pred < bins[i + 1] if i < n_bins - 1 else pred <= 1.0)
        if m.sum() == 0:
            continue
        total += m.mean() * abs(pred[m].mean() - labels[m].mean())
    return float(total)


def run_metric_trace(controller, tau, delta, p_edit, seed):
    """Same servo loop as run_servo_trial, but returns chunk-boundary traces."""
    ctrl = Controller(controller)
    rng = np.random.default_rng(seed)
    p = np.array([0.0, 0.0])
    g = np.array([0.15, 0.05])
    bias = rng.normal(0.0, 0.008, size=2)
    edit_scheduled = rng.random() < p_edit
    t = 0.0
    shifted = False
    edited = False
    queue = []
    prev_g_obs = None
    best_d = np.inf
    last_progress_t = 0.0
    recover_until = -1.0
    edit_until = -1.0
    success_steps = 0
    success = False
    phi = 0.0
    edit_time = None
    rec = []
    while t < 4.0:
        if (not shifted) and t >= 0.80:
            ang = rng.uniform(0, 2 * math.pi)
            g = g + delta * np.array([math.cos(ang), math.sin(ang)])
            shifted = True
        if (not edited) and t >= 1.20 and edit_scheduled:
            ang = rng.uniform(0, 2 * math.pi)
            g = g + 0.05 * np.array([math.cos(ang), math.sin(ang)])
            edited = True
            edit_time = t
        occluded = rng.random() < 0.10
        obs_sigma = 0.0008 * (5.0 if occluded else 1.0)
        p_obs = p + rng.normal(0.0, obs_sigma, size=2)
        g_obs = g + rng.normal(0.0, obs_sigma, size=2)
        d = float(np.linalg.norm(g_obs - p_obs))
        if prev_g_obs is not None and np.linalg.norm(g_obs - prev_g_obs) > 0.02:
            edit_until = t + 0.10
        prev_g_obs = g_obs
        phase = "approach" if d > 0.08 else ("align" if d > 0.02 else "contact")
        H = ctrl.horizon(phase, d, occluded, t, recover_until, edit_until, tau)
        if ctrl.recovery and t - last_progress_t > 0.40 and t > 0.5:
            recover_until = t + 0.10
            last_progress_t = t
        if d < best_d - 0.001:
            best_d = d
            last_progress_t = t
        # contract progress: approach -> align -> contact -> success
        if d <= 0.08:
            phi = max(phi, 0.25)
        if d <= 0.02:
            phi = max(phi, 0.60)
        if d <= 0.003:
            phi = max(phi, 1.00)
        conf = 0.5 if occluded else 1.0
        stall = (t - last_progress_t)
        # health is a *non-monotone* validity signal, separate from progress.
        if phase == "approach":
            health = 1.0 if d <= 0.10 else max(0.0, 1.0 - (d - 0.10) / 0.10)
        elif phase == "align":
            health = 1.0 if d <= 0.03 else max(0.0, 1.0 - (d - 0.03) / 0.03)
        else:
            health = 1.0 if d <= 0.005 else max(0.0, 1.0 - (d - 0.005) / 0.01)
        health *= conf
        risk = min(1.0, (1.0 - health) + stall / 0.50)
        rec.append((t, phi, d, conf, phase, stall, health, risk))
        if t < edit_until or t < recover_until:
            v = np.zeros(2)
        else:
            vmax = 0.5 if phase == "approach" else (0.15 if phase == "align" else 0.04)
            v = (g_obs - p_obs) / max(H * DT, 1e-6)
            v = v + bias + rng.normal(0.0, 0.006, size=2)
            if occluded:
                v = v * 0.5
            nv = np.linalg.norm(v)
            if nv > vmax:
                v = v * (vmax / nv)
        queue.append((t + tau, t + tau + H * DT, v))
        for _ in range(H):
            if t >= 4.0:
                break
            active = None
            for (s, e, vv) in queue:
                if s <= t + 1e-12 < e:
                    active = vv
                    break
            if active is None:
                active = np.zeros(2)
            p = p + DT * active + rng.normal(0.0, 0.0002, size=2)
            if (not shifted) and t >= 0.80:
                ang = rng.uniform(0, 2 * math.pi)
                g = g + delta * np.array([math.cos(ang), math.sin(ang)])
                shifted = True
            if (not edited) and t >= 1.20 and edit_scheduled:
                ang = rng.uniform(0, 2 * math.pi)
                g = g + 0.05 * np.array([math.cos(ang), math.sin(ang)])
                edited = True
                edit_time = t
            if np.linalg.norm(p - g) < 0.003:
                success_steps += 1
            else:
                success_steps = 0
            if success_steps >= 6:
                success = True
                break
            t += DT
        if success:
            break
    return rec, int(success), edit_time


def exp_c(n_trials=800, tau=0.15, delta=0.05, p_edit=0.50):
    traces = [run_metric_trace("clause", tau, delta, p_edit, 400000 + i)
              for i in range(n_trials)]
    out = {}
    for t_query in (0.5, 1.0, 1.5):
        phis, dists, confs, stalls, healths, risks, labels = [], [], [], [], [], [], []
        for rec, succ, _ in traces:
            last = None
            for row in rec:
                if row[0] <= t_query:
                    last = row
            if last is None:
                last = rec[0]
            phis.append(last[1])
            dists.append(-last[2])
            confs.append(last[1] * last[3])
            stalls.append(-last[5])
            healths.append(last[6])
            risks.append(last[7])
            labels.append(succ)
        out[f"t={t_query}"] = {
            "auroc_phi": auroc(phis, labels),
            "auroc_negdist": auroc(dists, labels),
            "auroc_confphi": auroc(confs, labels),
            "auroc_negstall": auroc(stalls, labels),
            "auroc_health": auroc(healths, labels),
            "auroc_risk_failure": auroc(risks, [1 - y for y in labels]),
            "ece_phi": ece(phis, labels),
            "success_rate": float(np.mean(labels)),
        }
    edited = [(rec, succ, et) for rec, succ, et in traces if et is not None]
    if edited:
        delays = []
        for rec, succ, et in edited:
            det = None
            for row in rec:
                if row[0] >= et and (row[6] < 0.5 or row[7] > 0.5):
                    det = row[0] - et
                    break
            if det is not None:
                delays.append(det)
        out["edited"] = {
            "n": len(edited),
            "success_rate": float(np.mean([succ for _, succ, _ in edited])),
            "detect_rate": float(len(delays) / len(edited)),
            "median_delay_s": float(np.median(delays)) if delays else float("nan"),
            "mean_delay_s": float(np.mean(delays)) if delays else float("nan"),
        }
    return out


def main():
    print("running exp_a ...", file=sys.stderr)
    a = exp_a()
    print("running exp_a_shift ...", file=sys.stderr)
    a_shift = exp_a_shift()
    print("running exp_b ...", file=sys.stderr)
    b = exp_b()
    print("running exp_c ...", file=sys.stderr)
    c = exp_c()
    result = {"exp_a": a, "exp_a_shift": a_shift, "exp_b": b, "exp_c": c}
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
