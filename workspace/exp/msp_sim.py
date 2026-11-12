#!/usr/bin/env python3
"""Round-1 (inspiration v2: motion-control x skill-composition) mechanism check.

NOT a robot result.  It isolates two claims behind the flagship MSP-01:
  C1  grasp timing contract  : closing the gripper only when |v| is small
                                reduces "grasp-while-moving" slip.
  C2  motion contract        : min-jerk blending at skill switches + a slew-rate
                                bound cuts the max per-step command jump
                                (a proxy for the credibility "action regularity"
                                metric) without hurting completion.

Task model: a 2-D end-effector must visit M=4 waypoints in order.  At each
waypoint the policy decides when to close the gripper; slip probability grows
with the speed at closure.  Abrupt target switches and human-style pushes are
the stressors.  All assumptions are printed with the result.

Methods (factorial):
  naive        : advance at r_switch, close immediately, no blend, no slew
  settle       : advance only when settled, close when settled, no blend/slew
  blend        : settle + min-jerk velocity blend at switch, no slew
  mcsc         : settle + blend + per-step slew-rate/accel feasibility projection
  mcsc_nosettle: blend + slew but switch at r_switch and close immediately

Run: python msp_sim.py
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

DT = 0.05
T_STEPS = 600
M_WAYPOINTS = 4
KP = 6.0
V_MAX = 1.2
R_SWITCH = 0.07
TOL = 0.03
V_GRASP = 0.12
SLIP_K = 0.85
SLIP_BASE = 0.03
DWELL = 3
J_MAX = 8.0
A_MAX = 8.0
BLEND_JERK_MAX = 1.875
METHOD_TAG = {"naive": 1, "settle": 2, "blend": 3, "mcsc": 4, "mcsc_nosettle": 5}


def _min_jerk(t):
    t = min(max(t, 0.0), 1.0)
    return 10 * t**3 - 15 * t**4 + 6 * t**5


def _clip(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _norm(v):
    return math.hypot(v[0], v[1])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _scale(a, s):
    return (a[0] * s, a[1] * s)


def _vel_toward(x, goal):
    e = _sub(goal, x)
    sp = _norm(e)
    v = _scale(e, KP)
    if sp * KP > V_MAX:
        v = _scale(v, V_MAX / (sp * KP))
    return v


def make_task(rng):
    pts = [(0.5, 0.1)]
    while len(pts) < M_WAYPOINTS + 1:
        p = (rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85))
        if _norm(_sub(p, pts[-1])) > 0.30:
            pts.append(p)
    return pts[1:]


def run(method, seed, push_prob):
    rng = random.Random((seed * 1009 + METHOD_TAG[method] * 7919
                         + int(push_prob * 1e6)) & 0x7FFFFFFF)
    goals = make_task(rng)
    x = (0.5, 0.1)
    v_emit = (0.0, 0.0)
    gi = 0
    grasped = 0
    max_jump = 0.0
    settle_count = 0
    blend_elapsed = 0
    blend_total = 0
    blend_from = (0.0, 0.0)
    blend_to = (0.0, 0.0)
    smooth = method in ("blend", "mcsc", "mcsc_nosettle")
    settle_gate = method in ("settle", "blend", "mcsc")

    for t in range(T_STEPS):
        if gi >= len(goals):
            break
        goal = goals[gi]
        e = _sub(goal, x)
        dist = _norm(e)
        v_des = _vel_toward(x, goal)
        speed_now = _norm(v_emit) if smooth else _norm(v_des)

        advance = False
        close_now = False
        if settle_gate:
            if dist < TOL and speed_now < V_GRASP:
                settle_count += 1
                if settle_count >= DWELL:
                    close_now = advance = True
            else:
                settle_count = 0
        else:
            if dist < R_SWITCH:
                close_now = advance = True

        if close_now:
            sp_close = speed_now
            p_slip = SLIP_BASE + SLIP_K * max(0.0, sp_close - V_GRASP) / max(1e-6, V_MAX - V_GRASP)
            p_slip = min(0.95, p_slip)
            if rng.random() >= p_slip:
                grasped += 1
            gi += 1
            settle_count = 0
            if gi >= len(goals):
                break
            goal = goals[gi]
            v_des = _vel_toward(x, goal)

        if smooth:
            if advance:
                blend_from = v_emit
                d = _norm(_sub(v_des, v_emit))
                blend_total = max(2, int(math.ceil(BLEND_JERK_MAX * d / (A_MAX * DT))))
                blend_elapsed = 0
            if blend_elapsed < blend_total:
                beta = _min_jerk((blend_elapsed + 1) / float(blend_total))
                cmd = _add(_scale(blend_from, 1 - beta), _scale(v_des, beta))
                blend_elapsed += 1
            else:
                cmd = v_des
            if method == "mcsc":
                max_dv = J_MAX * DT
                dv = _sub(cmd, v_emit)
                m = _norm(dv)
                if m > max_dv:
                    cmd = _add(v_emit, _scale(dv, max_dv / m))
            if t > 10:
                max_jump = max(max_jump, _norm(_sub(cmd, v_emit)))
            v_emit = cmd
        else:
            if t > 10:
                max_jump = max(max_jump, _norm(_sub(v_des, v_emit)))
            v_emit = v_des

        x = _add(x, _scale(v_emit, DT))

        if rng.random() < push_prob and t > 40:
            ang = rng.uniform(0, 2 * math.pi)
            mag = rng.uniform(0.04, 0.14)
            x = _add(x, (mag * math.cos(ang), mag * math.sin(ang)))
            settle_count = 0
            blend_elapsed = blend_total

    return {
        "success": 1.0 if grasped == M_WAYPOINTS else 0.0,
        "partial": grasped / float(M_WAYPOINTS),
        "max_jump": max_jump,
        "steps": t + 1,
        "grasped": grasped,
    }


def summarize(method, push_prob, seeds=600):
    succ = 0.0
    part = 0.0
    jumps = []
    steps = []
    for s in range(seeds):
        r = run(method, s, push_prob)
        succ += r["success"]
        part += r["partial"]
        jumps.append(r["max_jump"])
        steps.append(r["steps"])
    n = float(seeds)
    jumps.sort()
    return {
        "method": method,
        "push_prob": push_prob,
        "success_pct": round(100 * succ / n, 2),
        "partial_pct": round(100 * part / n, 2),
        "max_jump_mean": round(sum(jumps) / n, 4),
        "max_jump_p95": round(jumps[int(0.95 * (len(jumps) - 1))], 4),
        "mean_steps": round(sum(steps) / n, 1),
    }


def main():
    methods = ["naive", "settle", "blend", "mcsc", "mcsc_nosettle"]
    rows = []
    for pp in (0.0, 0.006):
        for m in methods:
            r = summarize(m, pp)
            rows.append(r)
            print(f"push={pp:<7} {m:<13} success={r['success_pct']:6.2f}%  "
                  f"partial={r['partial_pct']:6.2f}%  "
                  f"jump_mean={r['max_jump_mean']:.4f}  "
                  f"jump_p95={r['max_jump_p95']:.4f}  steps={r['mean_steps']}")
    out = {
        "note": "B-level synthetic mechanism check, NOT robot evidence",
        "assumptions": {
            "dt": DT, "T_steps": T_STEPS, "M_waypoints": M_WAYPOINTS,
            "kp": KP, "v_max": V_MAX, "r_switch": R_SWITCH, "tol": TOL,
            "v_grasp": V_GRASP, "slip_k": SLIP_K, "slip_base": SLIP_BASE,
            "dwell": DWELL, "j_max": J_MAX, "a_max": A_MAX, "seeds": 600,
        },
        "rows": rows,
    }
    with open(os.path.join(HERE, "msp_results.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("wrote msp_results.json")


if __name__ == "__main__":
    main()
