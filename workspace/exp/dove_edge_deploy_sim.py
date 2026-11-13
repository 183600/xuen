#!/usr/bin/env python3
"""DOVE / SLO-LADDER synthetic mechanism check (NOT UniBot evidence).

Two seeded, deliberately small simulations:

A. DOVE compute allocation
   The benchmark score is success + ordered step score. On an edge device the
   per-episode compute is finite and a step is only paid for if it is reached.
   This isolates one question: does allocating compute by *downstream option
   value* (local step value + the value of all later steps that depend on this
   step succeeding) beat uniform / local-value / reach-only allocation?

B. SLO-LADDER
   A remote/edge policy sees a non-stationary network. A synchronous cloud
   advisory can raise subtask success but inflates p95/p99 latency and can
   exhaust the episode budget. A staleness-aware asynchronous advisory is
   non-blocking; an SLO controller decides when to use cloud, when to fall back
   to edge-only, and when to degrade.

All parameters are declared below; nothing is fitted to UniBot. Results are
mechanism checks, not leaderboard or real-robot evidence.
"""
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "dove_edge_deploy_results.json")
RNG = np.random.default_rng(20261113)

# ---------------------------------------------------------------------------
# 32-task step-value table (from the public info.json, as summarised in v2)
# ---------------------------------------------------------------------------
TASKS = [
    ("T01", [50, 50], "easy"), ("T02", [50, 50], "easy"),
    ("T03", [50, 50], "easy"), ("T04", [30, 30, 40], "easy"),
    ("T05", [50, 50], "hard"), ("T06", [30, 30, 40], "easy"),
    ("T07", [30, 30, 40], "medium"), ("T08", [50, 50], "easy"),
    ("T09", [25, 25, 25, 25], "hard"), ("T10", [30, 30, 40], "hard"),
    ("T11", [30, 30, 40], "medium"), ("T12", [30, 30, 40], "hard"),
    ("T13", [30, 30, 40], "easy"), ("T14", [50, 50], "hard"),
    ("T15", [25, 25, 25, 25], "medium"), ("T16", [20, 20, 20, 20, 20], "hard"),
    ("T17", [20, 20, 20, 20, 20], "easy"), ("T18", [25, 25, 25, 25], "medium"),
    ("T19", [50, 50], "medium"), ("T20", [30, 30, 40], "easy"),
    ("T21", [30, 30, 40], "easy"), ("T22", [25, 25, 25, 25], "medium"),
    ("T23", [50, 50], "medium"), ("T24", [50, 50], "medium"),
    ("T25", [30, 30, 40], "easy"), ("T26", [30, 30, 40], "medium"),
    ("T27", [30, 30, 40], "easy"), ("T28", [25, 25, 25, 25], "hard"),
    ("T29", [30, 30, 40], "hard"), ("T30", [50, 50], "medium"),
    ("T31", [30, 30, 40], "medium"), ("T32", [50, 50], "medium"),
]
DIFF = {"easy": 0.08, "medium": 0.00, "hard": -0.10}

# ---------------------------------------------------------------------------
# A. DOVE allocation
# ---------------------------------------------------------------------------
P_MAX = 0.98
TAU_MAIN_MS = 18.0
TAU_REC_MS = 25.0
Q_MAX = 0.85
E_TOTAL_MS = 90.0          # expected compute per episode (only reached steps pay)
B_STEP_MS = 60.0           # per-decision compute cap
DELTA_MS = 0.5
L0_MS = 15.0               # fixed edge overhead per decision
L_MAX_MS = 100.0           # p95 SLO
N_MC = 3000


def task_instance(rng, task_id, values, difficulty):
    n = len(values)
    w = np.asarray(values, dtype=float)
    w = 100.0 * w / w.sum()
    # Wide, declared heterogeneity: task ease, phase depth, and per-step undo
    # hazard all vary.  This is the regime in which allocation actually matters.
    ease = float(rng.uniform(0.0, 1.0))
    base = 0.40 + 0.40 * ease + 0.5 * DIFF[difficulty]
    p0 = np.array([
        float(np.clip(base - 0.06 * g + rng.normal(0.0, 0.06), 0.15, 0.92))
        for g in range(n)
    ])
    hazard = np.array([
        float(np.clip(rng.uniform(0.02, 0.28) + 0.015 * g, 0.02, 0.35))
        for g in range(n)
    ])
    return dict(id=task_id, w=w, p0=p0, hazard=hazard)


def p_main(p0, x):
    return np.clip(p0 + (P_MAX - p0) * (1.0 - np.exp(-x / TAU_MAIN_MS)), 0.0, P_MAX)


def q_recover(x):
    return Q_MAX * (1.0 - np.exp(-x / TAU_REC_MS))


def outcomes(inst, xm, xr):
    """Expected step score / success / expected compute for one task.

    A disturbance occurs with probability hazard after a step; recovery compute
    repairs it with probability q(x_r).  This makes recovery hazard-specific
    (the v2 `human_*` undo axis), not a generic second attempt.
    """
    w, p0, h = inst["w"], inst["p0"], inst["hazard"]
    pm = p_main(p0, xm)
    q = q_recover(xr)
    p = np.clip(pm * (1.0 - h * (1.0 - q)), 0.0, P_MAX)
    reach = np.ones_like(p)
    for g in range(1, len(p)):
        reach[g] = reach[g - 1] * p[g - 1]
    score = float(np.sum(w * reach * p))
    success = float(np.prod(p))
    compute = float(np.sum(reach * (xm + xr)))
    return score, success, compute, p, reach


def proportional(inst, weights, e_budget=E_TOTAL_MS):
    """Allocate x proportional to weights, scaled to the expected budget."""
    weights = np.asarray(weights, dtype=float)
    weights = weights / weights.sum()
    lo, hi = 0.0, 1e4
    best = np.zeros_like(weights)
    for _ in range(80):
        lam = 0.5 * (lo + hi)
        x = np.minimum(B_STEP_MS, lam * weights)
        _, _, C, _, _ = outcomes(inst, x, np.zeros_like(x))
        if C < e_budget:
            lo = lam
            best = x
        else:
            hi = lam
    return best


def greedy(inst, strategy, e_budget=E_TOTAL_MS):
    """Allocate DELTA_MS units until the expected-compute budget is exhausted.

    strategy in {uniform, local, reach, dove, dove_rec}.
    Non-DOVE strategies use a fixed priority; DOVE uses marginal
    (delta expected step score)/(delta expected compute).
    """
    n = len(inst["w"])
    xr = np.zeros(n)
    if strategy == "uniform":
        xm = proportional(inst, np.ones(n), e_budget)
        score, success, compute, p, reach = outcomes(inst, xm, xr)
        return dict(xm=xm, xr=xr, score=score, success=success,
                    compute=compute, p=p, reach=reach)
    if strategy == "local":
        xm = proportional(inst, inst["w"], e_budget)
        score, success, compute, p, reach = outcomes(inst, xm, xr)
        return dict(xm=xm, xr=xr, score=score, success=success,
                    compute=compute, p=p, reach=reach)
    if strategy == "reach":
        xm0 = proportional(inst, inst["w"], e_budget)
        _, _, _, _, reach0 = outcomes(inst, xm0, xr)
        xm = proportional(inst, inst["w"] * reach0, e_budget)
        score, success, compute, p, reach = outcomes(inst, xm, xr)
        return dict(xm=xm, xr=xr, score=score, success=success,
                    compute=compute, p=p, reach=reach)

    xm = np.zeros(n)
    allow_rec = strategy == "dove_rec"
    score, success, compute, p, reach = outcomes(inst, xm, xr)

    while True:
        best = None  # (priority, kind, index, new score, new success, new compute)
        for g in range(n):
            modules = [("m", g)]
            if allow_rec:
                modules.append(("r", g))
            elif strategy == "dove":
                pass
            for kind, idx in modules:
                if kind == "m" and xm[idx] + DELTA_MS > B_STEP_MS:
                    continue
                if kind == "r" and xm[idx] + xr[idx] + DELTA_MS > B_STEP_MS:
                    continue
                nxm, nxr = xm.copy(), xr.copy()
                if kind == "m":
                    nxm[idx] += DELTA_MS
                else:
                    nxr[idx] += DELTA_MS
                ns, nsucc, nc, _, _ = outcomes(inst, nxm, nxr)
                if nc > e_budget + 1e-9:
                    continue
                ds = ns - score
                dc = nc - compute
                if strategy == "dove" or strategy == "dove_rec":
                    if dc <= 1e-9 or ds <= 1e-12:
                        continue
                    prio = ds / dc
                else:
                    raise ValueError(strategy)
                if best is None or prio > best[0] + 1e-15:
                    best = (prio, kind, idx, ns, nsucc, nc)
        if best is None:
            break
        _, kind, idx, score, success, compute, = best
        if kind == "m":
            xm[idx] += DELTA_MS
        else:
            xr[idx] += DELTA_MS
        # recompute p / reach for the next iteration
        _, _, _, p, reach = outcomes(inst, xm, xr)
        if compute >= e_budget - 1e-9:
            break
    return dict(xm=xm, xr=xr, score=score, success=success,
                compute=compute, p=p, reach=reach)


def monte_carlo(inst, alloc, n=N_MC, rng=None):
    """Check planned allocation against step-latency SLO and episode success."""
    rng = rng or np.random.default_rng(7)
    w, p0, h = inst["w"], inst["p0"], inst["hazard"]
    xm, xr = alloc["xm"], alloc["xr"]
    pm = p_main(p0, xm)
    q = q_recover(xr)
    p = np.clip(pm * (1.0 - h * (1.0 - q)), 0.0, P_MAX)
    lat = []
    scores, succ = [], []
    for _ in range(n):
        s = 0.0
        ok_all = True
        for g in range(len(w)):
            noise = float(rng.lognormal(mean=math.log(5.0), sigma=0.30))
            step_lat = L0_MS + xm[g] + xr[g] + noise
            lat.append(step_lat)
            ok = rng.random() < p[g]
            if ok:
                s += w[g]
            else:
                ok_all = False
                break
        scores.append(s)
        succ.append(1.0 if ok_all else 0.0)
    lat = np.asarray(lat)
    return dict(score=float(np.mean(scores)), success=float(np.mean(succ)),
                lat_mean=float(lat.mean()), lat_p50=float(np.percentile(lat, 50)),
                lat_p95=float(np.percentile(lat, 95)),
                lat_p99=float(np.percentile(lat, 99)),
                lat_std=float(lat.std()),
                slo_viol=float(np.mean(lat > L_MAX_MS)))


def run_allocation():
    rng = np.random.default_rng(11)
    instances = [task_instance(rng, tid, v, d) for tid, v, d in TASKS]
    strategies = ["uniform", "local", "reach", "dove", "dove_rec"]
    per_task = {}
    for inst in instances:
        per_task[inst["id"]] = {}
        for s in strategies:
            alloc = greedy(inst, s)
            mc = monte_carlo(inst, alloc)
            per_task[inst["id"]][s] = {
                "expected_step_score": alloc["score"],
                "expected_success": alloc["success"],
                "expected_compute_ms": alloc["compute"],
                "mean_x_main_ms": float(alloc["xm"].mean()),
                "mean_x_rec_ms": float(alloc["xr"].mean()),
                "mc_score": mc["score"], "mc_success": mc["success"],
                "lat_p50": mc["lat_p50"], "lat_p95": mc["lat_p95"],
                "lat_p99": mc["lat_p99"], "lat_std": mc["lat_std"],
                "slo_viol": mc["slo_viol"],
            }
    summary = {}
    for s in strategies:
        summary[s] = {
            k: float(np.mean([per_task[t][s][k] for t in per_task]))
            for k in per_task[TASKS[0][0]][s]
        }
    return {"per_task": per_task, "summary": summary,
            "config": dict(E_TOTAL_MS=E_TOTAL_MS, B_STEP_MS=B_STEP_MS,
                           L0_MS=L0_MS, L_MAX_MS=L_MAX_MS, N_MC=N_MC,
                           seed=20261113)}


# ---------------------------------------------------------------------------
# B. SLO-LADDER: synchronous vs asynchronous cloud advisory + fallback
# ---------------------------------------------------------------------------
FPS = 30.0
STEP_MEDIAN_MS = 30.0
STEP_SIGMA = 0.20
CLOUD_MEDIAN_MS = 500.0
CLOUD_SIGMA = 0.45
CLOUD_COMPUTE_MS = 60.0
ADVICE_DP = 0.12
TTL_MS = 1600.0
CARRY_DISCOUNT = 0.5
BUDGET_FACTOR = 1.55
EPISODES_PER_TASK = 120


def ladder_task(rng, values):
    n = len(values)
    w = np.asarray(values, dtype=float)
    w = 100.0 * w / w.sum()
    p0 = float(rng.uniform(0.55, 0.80))
    durations = rng.normal(2.0, 0.30, size=n).clip(1.0, 3.5)
    return dict(w=w, p0=p0, durations=durations)


def simulate_ladder(task, mode, rng, net_median_ms=CLOUD_MEDIAN_MS):
    n = len(task["w"])
    durations = task["durations"]
    nominal = float(durations.sum())
    budget = BUDGET_FACTOR * nominal
    clock = 0.0
    completed = 0
    lat = []
    wait = 0.0
    advice_used = 0
    carry = 0.0
    # simple online estimates for the auto controller
    seen_rtt = []
    for g in range(n):
        D = float(durations[g])
        use_cloud = False
        sync = False
        benefit = 0.0
        if mode == "sync":
            use_cloud, sync = True, True
        elif mode == "async":
            use_cloud, sync = True, False
        elif mode == "edge":
            use_cloud, sync = False, False
        elif mode == "auto":
            recent = float(np.median(seen_rtt[-5:])) if seen_rtt else net_median_ms
            # hysteresis: use async cloud only when the network looks healthy
            # and the advisory can plausibly arrive before the step ends.
            predicted_benefit = ADVICE_DP * max(
                0.0, 1.0 - recent / (D * 1000.0))
            remaining = budget - clock
            use_cloud = (recent <= 600.0 and predicted_benefit > 0.01
                         and remaining > 0.05)
            sync = False
        if use_cloud:
            rtt = float(rng.lognormal(mean=math.log(net_median_ms),
                                      sigma=CLOUD_SIGMA)) + CLOUD_COMPUTE_MS
            seen_rtt.append(rtt)
            if sync:
                clock += rtt / 1000.0
                wait += rtt / 1000.0
                benefit = ADVICE_DP
                advice_used += 1
            else:
                age = rtt
                if age <= D * 1000.0:
                    benefit = ADVICE_DP * max(0.0, 1.0 - age / (D * 1000.0))
                elif age <= TTL_MS:
                    benefit = CARRY_DISCOUNT * ADVICE_DP
                if benefit > 0.0:
                    advice_used += 1
        if carry > 0.0:
            benefit = max(benefit, carry)
            carry = 0.0
        p = float(np.clip(task["p0"] + benefit, 0.0, 0.985))
        ok = bool(rng.random() < p)
        n_steps = int(round(D * FPS))
        step_lat = np.maximum(
            1.0, rng.lognormal(mean=math.log(STEP_MEDIAN_MS),
                               sigma=STEP_SIGMA, size=n_steps))
        if sync:
            step_lat[0] += rtt
        lat.extend(step_lat.tolist())
        clock += float(step_lat.sum()) / 1000.0
        if clock > budget:
            break
        if ok:
            completed += 1
        else:
            break
    score = 100.0 * completed / n
    success = 1.0 if completed == n else 0.0
    timed_out = 1.0 if clock > budget else 0.0
    return dict(score=score, success=success, timed_out=timed_out,
                lat=lat, wait=wait, advice=advice_used)


def run_ladder():
    rng = np.random.default_rng(23)
    tasks = [ladder_task(rng, v) for _, v, _ in TASKS]
    modes = ["edge", "sync", "async", "auto"]
    out = {}
    for mode in modes:
        scores, succ, tos, lats, waits, adv = [], [], [], [], [], []
        for task in tasks:
            for _ in range(EPISODES_PER_TASK):
                # Non-stationary field network: good and bad regimes.
                net_median = 150.0 if rng.random() < 0.60 else 900.0
                r = simulate_ladder(task, mode, rng, net_median)
                scores.append(r["score"])
                succ.append(r["success"])
                tos.append(r["timed_out"])
                lats.extend(r["lat"])
                waits.append(r["wait"])
                adv.append(r["advice"])
        lats = np.asarray(lats)
        out[mode] = {
            "success_rate": float(np.mean(succ)),
            "mean_step_score": float(np.mean(scores)),
            "std_step_score": float(np.std(scores)),
            "timeout_rate": float(np.mean(tos)),
            "mean_sync_wait_s": float(np.mean(waits)),
            "advice_per_episode": float(np.mean(adv)),
            "lat_mean_ms": float(lats.mean()),
            "lat_p50_ms": float(np.percentile(lats, 50)),
            "lat_p95_ms": float(np.percentile(lats, 95)),
            "lat_p99_ms": float(np.percentile(lats, 99)),
            "lat_std_ms": float(lats.std()),
            "slo_viol_rate": float(np.mean(lats > L_MAX_MS)),
        }
    return {"results": out,
            "config": dict(FPS=FPS, STEP_MEDIAN_MS=STEP_MEDIAN_MS,
                           STEP_SIGMA=STEP_SIGMA,
                           CLOUD_MEDIAN_MS=CLOUD_MEDIAN_MS,
                           CLOUD_SIGMA=CLOUD_SIGMA,
                           CLOUD_COMPUTE_MS=CLOUD_COMPUTE_MS,
                           ADVICE_DP=ADVICE_DP, TTL_MS=TTL_MS,
                           BUDGET_FACTOR=BUDGET_FACTOR,
                           EPISODES_PER_TASK=EPISODES_PER_TASK,
                           L_MAX_MS=L_MAX_MS, seed=23)}


def main():
    a = run_allocation()
    b = run_ladder()
    payload = {"note": "Synthetic mechanism check only; not UniBot evidence.",
               "A_dove_allocation": a, "B_slo_ladder": b}
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=1)
    print("A. DOVE allocation summary")
    for s, v in a["summary"].items():
        print(f"  {s:9s} score={v['expected_step_score']:6.2f} "
              f"succ={v['expected_success']:.3f} "
              f"x={v['expected_compute_ms']:6.2f}ms "
              f"p95={v['lat_p95']:6.1f}ms "
              f"p99={v['lat_p99']:6.1f}ms "
              f"viol={v['slo_viol']:.4f}")
    print("B. SLO-LADDER summary")
    for m, v in b["results"].items():
        print(f"  {m:6s} score={v['mean_step_score']:6.2f} "
              f"succ={v['success_rate']:.3f} "
              f"p95={v['lat_p95_ms']:7.1f}ms "
              f"p99={v['lat_p99_ms']:8.1f}ms "
              f"timeout={v['timeout_rate']:.3f} "
              f"slo_viol={v['slo_viol_rate']:.4f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
