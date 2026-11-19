#!/usr/bin/env python3
"""Pilot sanity check for UniBot-SAFEDIAL.

A deliberately small 2-D abstraction of end-effector transit, NOT a robot
simulator.  It only checks whether the *mechanism* (contact-aware chance-CBF
+ bounded dialogue) behaves as claimed before spending real-robot hours.

Methods
  B0  policy only (no safety)
  B1  all-contact CBF (target also treated as an obstacle)
  B2  semantic CBF, stop on infeasibility (no dialogue)
  B3  semantic CBF + projection repair, no dialogue
  B4  semantic CBF + bounded dialogue (repair / request-alt / probe / yield /
      certified fallback / stall monitor)

Metrics
  success   reached the target disc
  collision hit a non-target object (or the human)
  stuck     neither success nor collision before the horizon
  steps     mean episode length (shorter is better, but never at the cost of
            success / safety)
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np

VMAX = 0.08
DT = 0.05
R_ROBOT = 0.015
R_TARGET = 0.05
ALPHA = 6.0
SIGMA0 = 0.018
KAPPA_D = 2.0
KAPPA_H = 3.0
EPS_DIST = 0.45 * VMAX
K_TURNS = 3
L_STALL = 35
HORIZON = 320
TAU_HUMAN = 0.60
YIELD_DIST = 0.12


@dataclass
class Obj:
    mu: np.ndarray
    r: float
    cls: str            # T, D, S, H
    sigma: float = SIGMA0
    dyn: bool = False
    phase: float = 0.0
    vel: np.ndarray = None
    base_y: float = 0.0

    def __post_init__(self):
        if self.vel is None:
            self.vel = np.zeros(2)


def policy(p, target, rng, bias=None, strength=0.0, obstacles=None):
    v = target - p
    n = np.linalg.norm(v)
    a = VMAX * v / n if n > 1e-9 else np.zeros(2)
    if bias is not None:
        a = a + bias
    if strength > 0.0 and obstacles is not None:
        for o in obstacles:
            d = p - o.mu
            dn = np.linalg.norm(d)
            if dn < 1e-9:
                continue
            w = strength * max(0.0, 1.0 - dn / 0.35)
            a = a + w * d / dn
    a = a + rng.normal(0.0, 0.04 * VMAX, size=2)
    sn = np.linalg.norm(a)
    if sn > VMAX:
        a = a / sn * VMAX
    return a


def perceive(objs, rng, scale=1.0):
    out = []
    for o in objs:
        sigma = o.sigma * scale
        mu = o.mu + rng.normal(0.0, sigma, size=2)
        r = max(0.01, o.r + rng.normal(0.0, 0.01 * scale))
        out.append(Obj(mu=mu, r=r, cls=o.cls, sigma=sigma, dyn=o.dyn,
                       phase=o.phase, vel=o.vel.copy(), base_y=o.base_y))
    return out


def _margin(o):
    k = KAPPA_H if o.cls == "H" else KAPPA_D
    return o.r + R_ROBOT + k * o.sigma


def _constraint(p, o, tau):
    mu = o.mu + o.vel * tau if o.dyn else o.mu
    d = p - mu
    dist = np.linalg.norm(d)
    n = d / dist if dist > 1e-9 else np.array([1.0, 0.0])
    h = dist - _margin(o)
    return n, -ALPHA * h, o


def cbf_filter(p, a_p, objs, block_target=True, tau=0.0):
    """Project a_p onto the linearised CBF half-spaces (POCS)."""
    a = a_p.copy()
    cons = []
    for o in objs:
        if o.cls == "T" and not block_target:
            continue
        cons.append(_constraint(p, o, tau if o.cls == "H" else 0.0))
    for _ in range(24):
        changed = False
        for n, b, _ in cons:
            if n @ a < b:
                a = a + (b - n @ a) * n
                changed = True
        an = np.linalg.norm(a)
        if an > VMAX:
            a = a / an * VMAX
            changed = True
        if not changed:
            break
    slack = math.inf
    viol = None
    for n, b, o in cons:
        s = n @ a - b
        if s < slack:
            slack = s
            viol = o
    return a, slack >= -1e-6, slack, viol


def hit(p, objs):
    for o in objs:
        if np.linalg.norm(p - o.mu) < o.r + R_ROBOT - 0.002:
            return True
    return False


def make_scene(scenario, rng):
    start = np.array([0.08, rng.uniform(0.30, 0.70)])
    target = np.array([0.92, rng.uniform(0.25, 0.75)])
    objs: list[Obj] = []

    def far(p, q, d):
        return np.linalg.norm(p - q) >= d

    n_static = 4 if scenario != "narrow" else 5
    tries = 0
    while len([o for o in objs if o.cls == "D"]) < n_static and tries < 2000:
        tries += 1
        mu = np.array([rng.uniform(0.22, 0.82), rng.uniform(0.12, 0.88)])
        r = rng.uniform(0.030, 0.065)
        if not far(mu, start, 0.22) or not far(mu, target, 0.20):
            continue
        if any(not far(mu, o.mu, r + o.r + 0.06) for o in objs):
            continue
        objs.append(Obj(mu=mu, r=r, cls="D"))
    if scenario == "narrow":
        ty = target[1]
        objs = [o for o in objs if abs(o.mu[0] - 0.55) > 0.12]
        objs.append(Obj(mu=np.array([0.55, ty - 0.10]), r=0.055, cls="D"))
        objs.append(Obj(mu=np.array([0.55, ty + 0.10]), r=0.055, cls="D"))
    if scenario == "human":
        objs.append(Obj(mu=np.array([0.80, target[1]]), r=0.045, cls="H",
                        sigma=0.020, dyn=True,
                        phase=rng.uniform(0, 2 * math.pi),
                        base_y=float(target[1])))
    objs.append(Obj(mu=target, r=R_TARGET, cls="T", sigma=0.0))
    return start, target, objs


def update_human(objs, t):
    for o in objs:
        if not o.dyn:
            continue
        new_y = o.base_y + 0.18 * math.sin(2 * math.pi * t / 200.0 + o.phase)
        o.vel = np.array([0.0, (new_y - o.mu[1]) / DT])
        o.mu = np.array([o.mu[0], new_y])


def human_predicted_clearance(p, human, tau):
    mu = human.mu + human.vel * tau
    return np.linalg.norm(p - mu) - (human.r + R_ROBOT + KAPPA_H * human.sigma)


def run_episode(method, scenario, seed):
    rng = np.random.default_rng(seed)
    start, target, true_objs = make_scene(scenario, rng)
    p = start.copy()
    collide = success = False
    stall = 0
    best = np.linalg.norm(p - target)
    steps = 0
    dialogue_turns = 0
    degraded = 0

    for t in range(HORIZON):
        steps = t + 1
        update_human(true_objs, t)
        est = perceive(true_objs, rng)
        est_target = [o for o in est if o.cls == "T"][0]
        blk = [o for o in est if o.cls != "T"]
        human_est = [o for o in est if o.cls == "H"]
        a_p = policy(p, est_target.mu, rng)

        if method == "B0":
            a = a_p
        elif method == "B1":
            a, feas, _, viol = cbf_filter(p, a_p, est, block_target=True, tau=TAU_HUMAN)
        elif method == "B2":
            # VETO-ONLY: commit the proposal only if it is already safe.
            a, feas, _, viol = cbf_filter(p, a_p, est, block_target=False, tau=TAU_HUMAN)
            if not (feas and np.linalg.norm(a - a_p) < 1e-9):
                a = np.zeros(2)
        elif method == "B3":
            a, feas, _, viol = cbf_filter(p, a_p, est, block_target=False, tau=TAU_HUMAN)
            if not feas:
                a = np.zeros(2)
        else:  # B4
            a, feas, slack, viol = cbf_filter(p, a_p, est, block_target=False, tau=TAU_HUMAN)
            d = np.linalg.norm(a - a_p)
            human_close = bool(human_est) and min(
                human_predicted_clearance(p, o, 0.5) for o in human_est) < YIELD_DIST
            if feas and d <= EPS_DIST:
                pass
            else:
                turns = 0
                chosen = None
                while turns < K_TURNS:
                    turns += 1
                    dialogue_turns += 1
                    if human_close and human_est and not feas:
                        # YIELD: step away from the predicted human position
                        h = human_est[0]
                        v = p - (h.mu + h.vel * 0.5)
                        n = np.linalg.norm(v)
                        chosen = VMAX * v / n if n > 1e-9 else np.zeros(2)
                        break
                    if not feas:
                        # PROBE: re-perceive with lower noise, then retry
                        est = perceive(true_objs, rng, scale=0.45)
                        blk = [o for o in est if o.cls != "T"]
                        a2, feas, slack, viol = cbf_filter(
                            p, a_p, est, block_target=False, tau=TAU_HUMAN)
                        d = np.linalg.norm(a2 - a_p)
                        if feas and d <= EPS_DIST:
                            chosen = a2
                            break
                    # REQUEST_ALT: ask the policy for a repulsive alternative
                    bias = np.zeros(2)
                    if viol is not None:
                        v = p - viol.mu
                        n = np.linalg.norm(v)
                        if n > 1e-9:
                            bias = 0.6 * VMAX * v / n
                    strength = 1.0 if stall > L_STALL else 0.5
                    a_p = policy(p, est_target.mu, rng, bias=bias,
                                 strength=strength, obstacles=blk)
                    a2, feas, slack, viol = cbf_filter(
                        p, a_p, est, block_target=False, tau=TAU_HUMAN)
                    d = np.linalg.norm(a2 - a_p)
                    if feas and d <= EPS_DIST:
                        chosen = a2
                        break
                if chosen is None:
                    chosen = np.zeros(2)   # certified fallback = brake/hold
                    degraded += 1
                a = chosen

        p = p + a * DT
        if hit(p, [o for o in true_objs if o.cls != "T"]):
            collide = True
            break
        dist = np.linalg.norm(p - target)
        if dist <= R_TARGET:
            success = True
            break
        if dist < best - 1e-4:
            best = dist
            stall = 0
        else:
            stall += 1
        if method == "B4" and stall > 2 * L_STALL:
            degraded += 1
            stall = 0

    return {
        "success": int(success),
        "collision": int(collide),
        "stuck": int((not success) and (not collide)),
        "steps": steps,
        "turns": dialogue_turns,
        "degraded": degraded,
    }


def summarize(rows):
    n = len(rows)
    out = {}
    for k in ("success", "collision", "stuck"):
        out[k] = round(100.0 * sum(r[k] for r in rows) / n, 2)
    out["steps"] = round(sum(r["steps"] for r in rows) / n, 1)
    out["turns_per_ep"] = round(sum(r["turns"] for r in rows) / n, 2)
    out["degraded_per_ep"] = round(sum(r["degraded"] for r in rows) / n, 2)
    out["n"] = n
    return out


def main():
    methods = ["B0", "B1", "B2", "B3", "B4"]
    scenarios = ["clutter", "narrow", "human"]
    seeds = list(range(1000, 1200))
    results = {}
    for sc in scenarios:
        results[sc] = {}
        for m in methods:
            rows = [run_episode(m, sc, s) for s in seeds]
            results[sc][m] = summarize(rows)
    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    for sc in scenarios:
        print(f"\n== {sc} ==")
        print(f"{'method':6} {'succ%':>6} {'coll%':>6} {'stuck%':>7} {'steps':>6} {'turns':>6} {'degr':>5}")
        for m in methods:
            r = results[sc][m]
            print(f"{m:6} {r['success']:6.1f} {r['collision']:6.1f} "
                  f"{r['stuck']:7.1f} {r['steps']:6.1f} "
                  f"{r['turns_per_ep']:6.2f} {r['degraded_per_ep']:5.2f}")


if __name__ == "__main__":
    main()
