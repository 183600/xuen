import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

DT = 1.0 / 30.0
H_C = 5
T_END = 6.0
ROBOT_R = 0.02
HUMAN_R = 0.06
D_SAFE = 0.03
TARGET = np.array([0.45, 0.0])
TARGET_R = 0.015
U_MAX = 5.0
KP = 25.0
KD = 8.0
ALPHA = 0.0
A_MAX = 5.0
TAU_REACT = 0.10
E0 = 20.0
E_BAR = 40.0
P_DISS = 0.10
HUMAN_X = 0.25
HUMAN_Y0 = -0.30
HUMAN_Y1 = 0.30
HUMAN_DUR = 2.6


def human_state(t, t0, x_hold):
    if t < t0:
        return None, None
    if t < t0 + 0.6:
        s = (t - t0) / 0.6
        y = -0.40 + 0.40 * s
        vy = 0.40 / 0.6
    elif t < t0 + 1.4:
        y = 0.0
        vy = 0.0
    elif t < t0 + 2.0:
        s = (t - (t0 + 1.4)) / 0.6
        y = 0.0 - 0.40 * s
        vy = -0.40 / 0.6
    else:
        return None, None
    return np.array([x_hold, y]), np.array([0.0, vy])


def nominal(p, v):
    return KP * (TARGET - p) - KD * v


def solve_qp(u0, constraints):
    if all(a @ u0 >= b - 1e-9 for a, b in constraints):
        return u0, False
    cons = [
        {
            "type": "ineq",
            "fun": lambda u, a=a, b=b: float(a @ u - b),
            "jac": lambda u, a=a: a,
        }
        for a, b in constraints
    ]
    res = minimize(
        lambda u: float(np.sum((u - u0) ** 2)),
        u0,
        jac=lambda u: 2.0 * (u - u0),
        bounds=[(-U_MAX, U_MAX), (-U_MAX, U_MAX)],
        constraints=cons,
        method="SLSQP",
        options={"maxiter": 60, "ftol": 1e-10, "disp": False},
    )
    if not res.success:
        return np.zeros(2), True
    return np.asarray(res.x, dtype=float), True


def run_trial(method, seed):
    rng = np.random.default_rng(seed)
    p = np.zeros(2)
    v = np.zeros(2)
    e_tank = E0
    t0 = rng.uniform(0.0, 0.30)
    x_hold = rng.uniform(0.33, 0.37)
    min_target = float("inf")
    min_human = float("inf")
    first_success = None
    collision = False
    interventions = 0
    steps = 0
    energy_min = e_tank
    fallbacks = 0
    for k in range(int(T_END / DT)):
        t = k * DT
        hp, hv = human_state(t, t0, x_hold)
        u_nom = nominal(p, v)
        constraints = []
        active_human = hp is not None
        if active_human and method in ("leash", "geometric"):
            d = p - hp
            dist = float(np.linalg.norm(d))
            if dist > 1e-9:
                n = d / dist
                h = dist - HUMAN_R - ROBOT_R - D_SAFE
                closing = max(0.0, -float(n @ (v - hv)))
                grad_v = (closing / A_MAX + TAU_REACT) * n if closing > 1e-9 else np.zeros(2)
                h_b = h - closing * closing / (2.0 * A_MAX) - TAU_REACT * closing
                hp_next = hp + hv * DT
                a = 0.5 * DT * DT * n + DT * grad_v
                b = -h_b - DT * float(n @ (v - hv))
                constraints.append((a, b))
        if method == "geometric":
            d = p - TARGET
            dist = float(np.linalg.norm(d))
            if dist > 1e-9:
                n = d / dist
                h = dist - (TARGET_R + ROBOT_R + 0.03)
                closing = max(0.0, -float(n @ v))
                grad_v = (closing / A_MAX + TAU_REACT) * n if closing > 1e-9 else np.zeros(2)
                h_b = h - closing * closing / (2.0 * A_MAX) - TAU_REACT * closing
                a = 0.5 * DT * DT * n + DT * grad_v
                b = -h_b - DT * float(n @ v)
                constraints.append((a, b))
        u, filtered = solve_qp(u_nom, constraints)
        if method == "leash":
            power = float(u @ v)
            e_next = e_tank - DT * power - DT * P_DISS
            if e_next < 0.0:
                if power > 1e-9:
                    gamma = max(0.0, min(1.0, (e_tank - DT * P_DISS) / (DT * power)))
                    u = gamma * u
                    e_next = e_tank - DT * float(u @ v) - DT * P_DISS
                else:
                    u = np.zeros(2)
                    e_next = e_tank - DT * P_DISS
            e_tank = max(0.0, min(E_BAR, e_next))
        if filtered:
            interventions += 1
        v = v + DT * u
        p = p + DT * v
        steps += 1
        d_target = float(np.linalg.norm(p - TARGET))
        min_target = min(min_target, d_target)
        if d_target <= TARGET_R and first_success is None:
            first_success = t
        if active_human:
            dh = float(np.linalg.norm(p - hp))
            min_human = min(min_human, dh)
            if dh < HUMAN_R + ROBOT_R:
                collision = True
        energy_min = min(energy_min, e_tank)
    return {
        "method": method,
        "seed": seed,
        "t0": t0,
        "x_hold": x_hold,
        "success": bool(min_target <= TARGET_R),
        "min_target": min_target,
        "collision": collision,
        "min_human": None if min_human == float("inf") else min_human,
        "time_to_success": None if first_success is None else first_success,
        "interventions": interventions / max(steps, 1),
        "energy_min": energy_min,
        "fallbacks": fallbacks,
    }


def summarize(rows, method):
    sub = [r for r in rows if r["method"] == method]
    succ = np.mean([r["success"] for r in sub])
    coll = np.mean([r["collision"] for r in sub])
    min_h = [r["min_human"] for r in sub if r["min_human"] is not None]
    times = [r["time_to_success"] for r in sub if r["time_to_success"] is not None]
    inter = np.mean([r["interventions"] for r in sub])
    emin = np.mean([r["energy_min"] for r in sub])
    return {
        "method": method,
        "n": len(sub),
        "success": float(succ),
        "collision": float(coll),
        "min_human_mean": float(np.mean(min_h) if min_h else float("nan")),
        "min_human_p05": float(np.quantile(min_h, 0.05) if min_h else float("nan")),
        "time_mean": float(np.mean(times) if times else float("nan")),
        "interventions": float(inter),
        "energy_min_mean": float(emin),
    }


def main():
    t_start = time.time()
    rows = []
    for method in ("baseline", "geometric", "leash"):
        for seed in range(100):
            rows.append(run_trial(method, seed))
    summary = [summarize(rows, m) for m in ("baseline", "geometric", "leash")]
    out = {
        "config": {
            "dt": DT,
            "H_c": H_C,
            "T_end": T_END,
            "robot_r": ROBOT_R,
            "human_r": HUMAN_R,
            "d_safe": D_SAFE,
            "target": TARGET.tolist(),
            "target_r": TARGET_R,
            "u_max": U_MAX,
            "kp": KP,
            "kd": KD,
            "alpha": ALPHA,
            "e0": E0,
            "e_bar": E_BAR,
            "p_diss": P_DISS,
            "human_duration": HUMAN_DUR,
        },
        "summary": summary,
        "rows": rows,
        "elapsed_s": time.time() - t_start,
    }
    path = Path(__file__).with_name("leash_toy.json")
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out["summary"], indent=2, ensure_ascii=False))
    print("elapsed", out["elapsed_s"], "s")


if __name__ == "__main__":
    main()
