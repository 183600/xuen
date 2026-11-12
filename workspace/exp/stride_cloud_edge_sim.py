"""Round-2 synthetic mechanism check: STRIDE (cloud-edge asynchronous advisory).

NOT robot/benchmark evidence.  Isolates one question:

  A remote policy API is inherently cloud-edge: a slow cloud planner/verifier is
  useful, but blocking every decision on it inflates p95 latency and can exhaust
  the episode budget.  If the cloud emits timestamped advisories asynchronously,
  and the edge only consumes them while fresh, can we keep most of the success
  gain while leaving the per-step latency distribution untouched?

Models (declared, not fit):
  * 32 tasks, 4-8 ordered subtasks each; a subtask succeeds w.p. p0 in [0.55,0.80].
  * Cloud advice raises a subtask's success prob by dp in [0.05,0.20] when applied.
  * sync   : block at every subtask start for a cloud round trip; full dp.
  * async  : never block; apply advice at age=a with benefit dp*max(0,1-a/D),
             where D is the subtask duration; if a>D, carry 0.5*dp to next
             subtask when a<2D, else drop.  TTL gate drops very old advice.
  * selective: oracle-selective offload -- block only on subtasks with p0 below
             the median difficulty, async otherwise (upper bound on a real
             uncertainty-triggered gate).
  * local  : no cloud.
  * Wall clock: edge step latency ~ lognormal(25ms, cv=0.2); sync adds cloud RTT.
  * Episode budget = 1.55 * nominal-edge duration, so sync can time out.
Metrics: success (all subtasks), step score (completed fraction), p50/p95/std
per-step latency, timeout rate, advice-use rate, and a transparent rank proxy =
step_score + 20*success_rate (unknown official weights; reported only for ordering).
"""
import json, math, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stride_cloud_edge_results.json")
RNG = np.random.default_rng(20261112)

TASKS = 32
EPISODES = 80          # per task => 2560 episodes
FPS = 30.0
EDGE_MEAN_MS = 25.0
EDGE_CV = 0.20
CLOUD_MEDIAN_S = 0.90
CLOUD_SIGMA = 0.38     # lognormal sigma
CLOUD_COMPUTE_S = 0.08
BUDGET_FACTOR = 1.55
TTL_S = 1.60           # drop advice older than this
CARRY_DISCOUNT = 0.50
P0_MEDIAN = 0.675       # median of U(0.55,0.80), used by oracle-selective


def lognormal_from_median(median, sigma, rng):
    return rng.lognormal(mean=math.log(median), sigma=sigma)


def make_tasks(rng):
    tasks = []
    for _ in range(TASKS):
        n_sub = int(rng.integers(4, 9))
        p0 = float(rng.uniform(0.55, 0.80))
        dp = float(rng.uniform(0.05, 0.20))
        durations = rng.normal(2.0, 0.30, size=n_sub).clip(1.0, 3.5)
        tasks.append(dict(n_sub=n_sub, p0=p0, dp=dp, durations=durations))
    return tasks


def simulate_episode(task, mode, rng):
    n = task["n_sub"]
    durations = task["durations"]
    nominal = float(durations.sum())
    budget = BUDGET_FACTOR * nominal
    clock = 0.0
    completed = 0
    latencies = []
    advice_used = 0
    wait_time = 0.0
    carry = 0.0
    for i in range(n):
        D = float(durations[i])
        use_sync = (mode == "sync") or (mode == "selective" and task["p0"] < P0_MEDIAN)
        use_async = (mode == "async") or (mode == "selective" and not use_sync)
        if mode == "local":
            benefit = 0.0
        elif use_sync:
            rtt = lognormal_from_median(CLOUD_MEDIAN_S, CLOUD_SIGMA, rng) + CLOUD_COMPUTE_S
            clock += rtt
            wait_time += rtt
            benefit = task["dp"]
            advice_used += 1
        else:  # async
            rtt = lognormal_from_median(CLOUD_MEDIAN_S, CLOUD_SIGMA, rng) + CLOUD_COMPUTE_S
            age = rtt
            if age <= D:
                benefit = task["dp"] * max(0.0, 1.0 - age / D)
            elif age <= 2.0 * D and i + 1 < n and age <= TTL_S:
                benefit = CARRY_DISCOUNT * task["dp"]
                carry = max(carry, benefit)
            else:
                benefit = 0.0
            if carry > 0.0:
                benefit = max(benefit, carry)
                carry = 0.0
            if benefit > 0.0:
                advice_used += 1
        p = float(np.clip(task["p0"] + benefit, 0.0, 0.985))
        ok = bool(rng.random() < p)
        n_steps = int(round(D * FPS))
        step_lat = np.maximum(
            1.0, rng.lognormal(mean=math.log(EDGE_MEAN_MS), sigma=EDGE_CV, size=n_steps)
        )
        if use_sync:
            step_lat[0] += rtt * 1000.0
        latencies.extend(step_lat.tolist())
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
    return dict(score=score, success=success, timeout=timed_out,
                latencies=latencies, completed=completed, n_sub=n,
                budget=budget, clock=clock, advice_used=advice_used,
                wait_time=wait_time)


def summarize(rows):
    lat = np.array([x for r in rows for x in r["latencies"]], dtype=float)
    scores = np.array([r["score"] for r in rows])
    succ = np.array([r["success"] for r in rows])
    timeout = np.array([r["timeout"] for r in rows])
    advice = np.array([r["advice_used"] for r in rows])
    wait = np.array([r["wait_time"] for r in rows])
    return dict(
        success_rate=float(succ.mean()),
        mean_step_score=float(scores.mean()),
        std_step_score=float(scores.std()),
        timeout_rate=float(timeout.mean()),
        advice_used_per_episode=float(advice.mean()),
        mean_sync_wait_s=float(wait.mean()),
        steps=float(len(lat)),
        lat_mean_ms=float(lat.mean()),
        lat_p50_ms=float(np.percentile(lat, 50)),
        lat_p95_ms=float(np.percentile(lat, 95)),
        lat_p99_ms=float(np.percentile(lat, 99)),
        lat_std_ms=float(lat.std()),
        rank_proxy=float(scores.mean() + 20.0 * succ.mean()),
    )


def main():
    tasks = make_tasks(RNG)
    results = {}
    for mode in ("local", "async", "selective", "sync"):
        rows = []
        for t in tasks:
            for _ in range(EPISODES):
                rows.append(simulate_episode(t, mode, RNG))
        results[mode] = summarize(rows)
    out = dict(
        note="Synthetic mechanism check only; parameters declared in script, not fitted to UniBot.",
        config=dict(TASKS=TASKS, EPISODES=EPISODES, FPS=FPS, EDGE_MEAN_MS=EDGE_MEAN_MS,
                    EDGE_CV=EDGE_CV, CLOUD_MEDIAN_S=CLOUD_MEDIAN_S,
                    CLOUD_SIGMA=CLOUD_SIGMA, CLOUD_COMPUTE_S=CLOUD_COMPUTE_S,
                    BUDGET_FACTOR=BUDGET_FACTOR, TTL_S=TTL_S,
                    CARRY_DISCOUNT=CARRY_DISCOUNT, P0_MEDIAN=P0_MEDIAN,
                    seed=20261112),
        results=results,
    )
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for mode in ("local", "async", "selective", "sync"):
        r = results[mode]
        print(f"{mode:9s} success={r['success_rate']:.3f} score={r['mean_step_score']:.1f} "
              f"timeout={r['timeout_rate']:.3f} wait={r['mean_sync_wait_s']:.2f}s "
              f"p50={r['lat_p50_ms']:.1f} p95={r['lat_p95_ms']:.1f} "
              f"p99={r['lat_p99_ms']:.1f} std={r['lat_std_ms']:.1f} proxy={r['rank_proxy']:.1f}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
