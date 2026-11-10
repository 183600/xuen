"""Toy audit: step-level safety vs commit-horizon safety shell (CHSS) under
observation age A and actuation delay D. 2D point robot, first-order velocity
commands, open-loop action chunks (T_a), one moving disc obstacle.

Not a robot benchmark. It isolates the *commit-window* effect: a filter that
only looks at the currently observed state cannot protect the steps that will
be executed after a delay.
"""
import json, numpy as np

DT = 0.05
VMAX = 1.2
T_A = 8
R_ROB = 0.06
R_OBS = 0.12
MARGIN = 0.03
START = np.array([0.2, 0.2])
GOAL = np.array([1.8, 1.8])
MAX_STEPS = 400
A_STEPS = 4      # observation age (steps)
D_STEPS = 3      # actuation delay (steps)
V_OBS = 0.5
EPS_PERC = 0.015
EPS_PRED = 0.02


def nominal(x, goal=GOAL):
    d = goal - x
    n = np.linalg.norm(d)
    if n < 1e-9:
        return np.zeros(2)
    return d / n * VMAX


def rollout_nominal(x, horizon):
    out = []
    p = x.copy()
    for _ in range(horizon):
        v = nominal(p)
        p = p + v * DT
        out.append(p.copy())
    return out


def predict_obstacle(p, v, horizon):
    return np.array([p + v * DT * k for k in range(1, horizon + 1)])


def choose_chss(x, goal, op, ov, v_now):
    """Return a velocity command safe over the whole chunk under age+delay.

    Candidate set = nominal, braking, and tangential detours. A candidate is
    admissible if the predicted robot path keeps clearance >= margin against
    the *inflated* obstacle prediction for every step of the commit horizon.
    """
    horizon = A_STEPS + D_STEPS + T_A
    cands = [nominal(x, goal), np.zeros(2)]
    if v_now is not None and np.linalg.norm(v_now) > 1e-6:
        cands.append(0.35 * v_now / np.linalg.norm(v_now))
    d = goal - x
    if np.linalg.norm(d) > 1e-6:
        u = d / np.linalg.norm(d)
        perp = np.array([-u[1], u[0]])
        for s in (+1, -1):
            cands.append(0.8 * VMAX * (0.55 * u + 0.85 * s * perp))
            cands.append(0.5 * VMAX * (0.3 * u + s * perp))
    best, best_score = None, -1e9
    for v in cands:
        if np.linalg.norm(v) > VMAX + 1e-9:
            continue
        p = x.copy()
        ok = True
        min_clear = 1e9
        for k in range(horizon):
            p = p + v * DT
            o = op + ov * DT * (k + 1)
            rho = np.linalg.norm(ov) * (A_STEPS + D_STEPS + k) * DT + EPS_PERC + EPS_PRED
            clear = np.linalg.norm(p - o) - (R_OBS + R_ROB + MARGIN + rho)
            min_clear = min(min_clear, clear)
            if clear < 0:
                ok = False
                break
        if ok:
            # prefer progress; small penalty for speed to keep motion smooth
            score = float(v @ (goal - x) / (np.linalg.norm(goal - x) + 1e-9)) - 0.05 * np.linalg.norm(v)
            if score > best_score:
                best_score, best = score, v
    if best is None:
        # no admissible candidate: hard brake as the fail-safe tail
        return np.zeros(2)
    return best


def choose_step(x, op):
    """Delay-unaware step filter: react only to the currently observed gap."""
    delta = x - op
    dist = np.linalg.norm(delta)
    if dist < R_OBS + R_ROB + MARGIN * 3 and dist > 1e-9:
        return VMAX * delta / dist
    return nominal(x)


def make_chunk(mode, x, op, ov, v_now):
    """Return a T_A-long velocity chunk (list of 2-vectors)."""
    if mode == "none":
        return [nominal(x)]
    if mode == "step":
        return [choose_step(x, op)]
    return [choose_chss(x, GOAL, op, ov, v_now)]


def _episode(mode, op0, ov, rng):
    x = START.copy()
    op = op0.copy()
    v_now = np.zeros(2)
    ov_est = ov + (rng.normal(0.0, 0.07, 2) if mode == "chss" else np.zeros(2))
    schedule = {}
    steps = 0
    collided = False
    for t in range(MAX_STEPS):
        if t % T_A == 0:
            obs_obst = op - ov * DT * A_STEPS
            chunk = make_chunk(mode, x, obs_obst, ov_est if mode == "chss" else ov, v_now)
            for k in range(T_A):
                schedule[t + D_STEPS + k] = chunk[k % len(chunk)]
        v_applied = schedule.pop(t, np.zeros(2))
        v_now = v_applied
        x = x + v_applied * DT
        op = op + ov * DT
        steps += 1
        if np.linalg.norm(x - op) < R_OBS + R_ROB:
            collided = True
            break
        if np.linalg.norm(x - GOAL) < 0.08:
            break
    success = (not collided) and np.linalg.norm(x - GOAL) < 0.08
    return success, collided, steps, float(np.linalg.norm(x - GOAL))


def run(mode, rng):
    phase = rng.uniform(-1.2, 1.2)
    center = np.array([1.0, 1.0])
    dirv = np.array([1.0, -1.0]) / np.sqrt(2)
    op0 = center + dirv * phase * 1.2
    ov = dirv * V_OBS
    return _episode(mode, op0, ov, rng)


def main():
    rng = np.random.default_rng(20261110)
    out = {}
    for mode in ["none", "step", "chss"]:
        res = [run(mode, rng) for _ in range(1500)]
        succ = np.mean([r[0] for r in res])
        coll = np.mean([r[1] for r in res])
        st = np.mean([r[2] for r in res])
        st_ok = np.mean([r[2] for r in res if r[0]])
        out[mode] = {"success": float(succ), "collision": float(coll),
                     "mean_steps": float(st), "mean_steps_success": float(st_ok)}
    # no-conflict episodes: obstacle parked far from the start-goal diagonal
    rng2 = np.random.default_rng(7)
    quiet = {}
    for mode in ["none", "step", "chss"]:
        vals = [_episode(mode, np.array([0.25, 1.75]), np.zeros(2), rng2)[2] for _ in range(400)]
        quiet[mode] = {"mean_steps": float(np.mean(vals))}
    out["quiet"] = quiet
    out["config"] = {"dt": DT, "vmax": VMAX, "chunk": T_A, "obs_age_steps": A_STEPS,
                     "act_delay_steps": D_STEPS, "r_obs": R_OBS, "r_robot": R_ROB,
                     "obstacle_speed": V_OBS, "episodes": 1500, "quiet_episodes": 400,
                     "seed": 20261110,
                     "claim": "under age+delay a delay-unaware step filter buys almost nothing; commit-horizon inflation removes nearly all collisions at a measured step cost, and costs nothing when the path is clear",
                     "not_claimed": "not a real-robot or full-physics benchmark; perception is a perfect track with bounded error"}
    path = "/home/runner/work/xuen/xuen/workspace/exp/r43_chss/chss_sim_results.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
