"""v3 toy decision-theoretic check (synthetic, NOT real-robot evidence).

Question: under human "undo" disturbances, which planning lever matters most?
  (a) reordering subgoals (exposure minimization), or
  (b) commitment / irreversibility (reduce post-achievement undo hazard),
  and what happens when commitment costs time and the deadline is tight?

Model: 3 scoring subgoals with weights w, deterministic achieve time dt,
redo time rt, and post-achievement Poisson undo hazard lambda. Commit an
action multiplies lambda by CF but adds CC seconds. Undo after achievement
flips it to not-done; it can be redone if redo finishes before horizon T.
Final score = sum of weights of subgoals still achieved at T.
"""
import heapq
import json
import math
import random

BASE = [
    # (weight, achieve_time, redo_time, undo_hazard)
    (30, 8.0, 6.0, 0.010),
    (30, 8.0, 6.0, 0.006),
    (40, 8.0, 6.0, 0.020),
]
N_TRIALS = 30000
CF = 0.1   # hazard multiplier when committed
CC = 3.0   # extra seconds per committed subgoal


def simulate(T, order, commit_set, seed, redo_override=None):
    rng = random.Random(seed)
    n = len(BASE)
    t = 0.0
    tau = [0.0] * n
    lam = [0.0] * n
    for i in order:
        _, dt, _, lb = BASE[i]
        t += dt + (CC if i in commit_set else 0.0)
        if t >= T:
            return 0.0, False
        tau[i] = t
        lam[i] = lb * (CF if i in commit_set else 1.0)
    alive = [True] * n
    undone = [False] * n
    ev = []
    for i in range(n):
        heapq.heappush(ev, (tau[i] + rng.expovariate(lam[i]), i, "undo"))
    while ev:
        et, i, typ = heapq.heappop(ev)
        if et > T:
            break
        if typ == "undo":
            if alive[i] and not undone[i]:
                undone[i] = True
                alive[i] = False
                rt = BASE[i][2] if redo_override is None else redo_override
                if et + rt < T:
                    heapq.heappush(ev, (et + rt, i, "redo"))
        else:
            if not alive[i]:
                undone[i] = False
                alive[i] = True
                heapq.heappush(ev, (et + rng.expovariate(lam[i]), i, "undo"))
    score = sum(BASE[i][0] for i in range(n) if alive[i])
    return score, all(alive)


def run(T, name, order, commit_set, redo_override=None):
    total = success = sq = 0.0
    for s in range(N_TRIALS):
        sc, ok = simulate(T, order, commit_set, s, redo_override)
        total += sc
        success += ok
        sq += sc * sc
    mean = total / N_TRIALS
    sd = math.sqrt(max(sq / N_TRIALS - mean * mean, 0.0))
    return {
        "T": T,
        "arm": name,
        "order": order,
        "commit": sorted(commit_set),
        "mean_score": round(mean, 3),
        "success": round(success / N_TRIALS, 4),
        "sd": round(sd, 3),
    }


def main():
    wl = [w * l for (w, _, _, l) in BASE]
    asc = sorted(range(3), key=lambda i: wl[i])   # low w*lambda first, high last
    desc = asc[::-1]
    rows = []
    # R1: slack, cheap redo
    for T, tag, redo in ((40.0, "R1-slack", 6.0), (30.0, "R2-tight", 6.0),
                         (50.0, "R3-slow-redo", 20.0)):
        rows += [
            run(T, f"{tag}:fixed,no-commit", [0, 1, 2], set(), redo),
            run(T, f"{tag}:delay-high-wl,no-commit", asc, set(), redo),
            run(T, f"{tag}:high-wl-first,no-commit", desc, set(), redo),
            run(T, f"{tag}:commit-high-wl", asc, {2}, redo),
            run(T, f"{tag}:commit-all", [0, 1, 2], {0, 1, 2}, redo),
        ]
    out = {"config": {"BASE": BASE, "N_TRIALS": N_TRIALS, "CF": CF, "CC": CC},
           "rows": rows}
    with open("/home/runner/work/xuen/xuen/workspace/tmp/v3_plan_sim.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
