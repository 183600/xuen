#!/usr/bin/env python3
"""Round 2 / UniBot-SAGE v2: a boundary test for skill-routing generalization.

Question: the round-1 IP-01 upper bound (per-task oracle 33.96 vs best single
29.70, +4.26) answers "what if we knew the best model per task".  It does NOT
answer "can a deployable router capture that gain".  This script brackets the
deployable gain with:

  * a deployable LOWER bound  -> route by task-name text similarity only
                                 (available at test time), leave-one-task-out;
  * a leaky UPPER bound       -> route by the held-out task's own cross-model
                                 profile (uses target info; not deployable);
  * a coarse-family bound     -> K-means over task profiles + cluster-LOO
                                 expert choice (known cluster membership).

Data: exp/r16/lb_data.py, a verbatim transcription of the official
leaderboard_data.json teaser table (retrieved 2026-11-02).  The page itself
says the table is randomly generated, so these are STRUCTURE-level results,
not real-world evidence.  The point is the test protocol, not the numbers.

No third-party deps: pure Python.
"""
import json
import math
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "r16"))
from lb_data import MODELS, TASKS  # noqa: E402

N, T = len(MODELS), len(TASKS)
M = [[float(m[5][j]) for j in range(T)] for m in MODELS]
AVG = [sum(row) / T for row in M]
BEST_SINGLE = max(AVG)
BEST_IDX = AVG.index(BEST_SINGLE)
ORACLE = sum(max(M[i][j] for i in range(N)) for j in range(T)) / T
ORACLE_GAIN = ORACLE - BEST_SINGLE
COLS = [[M[i][j] for i in range(N)] for j in range(T)]


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va == 0 or vb == 0:
        return 0.0
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / math.sqrt(va * vb)


def tokens(s):
    return set(re.findall(r"[a-z]+", s.lower()))


def char_ngrams(s, n=3):
    s = re.sub(r"\s+", " ", s.lower())
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jaccard(a, b):
    return len(a & b) / len(a | b) if (a | b) else 0.0


TEXT_FEATURES = {
    "token_jaccard": lambda a, b: jaccard(tokens(a), tokens(b)),
    "char3_jaccard": lambda a, b: jaccard(char_ngrams(a), char_ngrams(b)),
}


def route_loto(similarity, k=1):
    """Leave-one-task-out router.  Uses only test-time-available features."""
    per_task, picks = [], []
    for j in range(T):
        sims = sorted(((similarity(TASKS[j], TASKS[k]), k)
                       for k in range(T) if k != j), reverse=True)
        neighbours = [k for _, k in sims[:k]]
        expert = max(range(N), key=lambda i: sum(M[i][k] for k in neighbours) / len(neighbours))
        per_task.append(M[expert][j])
        picks.append({
            "task": TASKS[j],
            "nearest_task": TASKS[neighbours[0]],
            "expert": MODELS[expert][0],
        })
    return {
        "mean_success": sum(per_task) / T,
        "gain_vs_best_single": sum(per_task) / T - BEST_SINGLE,
        "capture_of_oracle_gain": (sum(per_task) / T - BEST_SINGLE) / ORACLE_GAIN,
        "per_task": per_task,
        "picks": picks,
    }


def route_leaky_profile(k=1):
    """UPPER bound: similarity uses the held-out task's own model profile."""
    per_task = []
    for j in range(T):
        sims = sorted(((corr(COLS[j], COLS[k]), k)
                       for k in range(T) if k != j), reverse=True)
        neighbours = [x for _, x in sims[:k]]
        expert = max(range(N), key=lambda i: sum(M[i][x] for x in neighbours) / len(neighbours))
        per_task.append(M[expert][j])
    return {
        "mean_success": sum(per_task) / T,
        "gain_vs_best_single": sum(per_task) / T - BEST_SINGLE,
        "capture_of_oracle_gain": (sum(per_task) / T - BEST_SINGLE) / ORACLE_GAIN,
        "per_task": per_task,
    }


def bootstrap_gain(per_task, n_boot=20000, seed=0):
    rnd = random.Random(seed)
    gains = []
    for _ in range(n_boot):
        s = [per_task[rnd.randrange(T)] for _ in range(T)]
        gains.append(sum(s) / T - BEST_SINGLE)
    gains.sort()
    return {
        "ci95": [gains[int(0.025 * n_boot)], gains[int(0.975 * n_boot)]],
        "p_gain_positive": sum(1 for g in gains if g > 0) / n_boot,
    }


def kmeans(vectors, k, seed, iters=200):
    rnd = random.Random(seed)
    centroids = [list(rnd.choice(vectors)) for _ in range(k)]
    assign = [0] * len(vectors)
    for _ in range(iters):
        assign = [min(range(k), key=lambda c: sum(
            (v[d] - centroids[c][d]) ** 2 for d in range(len(v)))) for v in vectors]
        new = [[0.0] * len(vectors[0]) for _ in range(k)]
        cnt = [0] * k
        for v, a in zip(vectors, assign):
            cnt[a] += 1
            for d, val in enumerate(v):
                new[a][d] += val
        for c in range(k):
            new[c] = ([x / cnt[c] for x in new[c]] if cnt[c] else list(rnd.choice(vectors)))
        if new == centroids:
            break
        centroids = new
    sse = sum(sum((v[d] - centroids[a][d]) ** 2 for d in range(len(v)))
              for v, a in zip(vectors, assign))
    return assign, sse


def cluster_loo(k, n_restart=40):
    best = None
    for seed in range(n_restart):
        assign, sse = kmeans(COLS, k, seed)
        if best is None or sse < best[1]:
            best = (assign, sse)
    assign = best[0]
    per_task = []
    for j in range(T):
        members = [x for x in range(T) if assign[x] == assign[j] and x != j]
        if not members:
            members = [x for x in range(T) if x != j]
        expert = max(range(N), key=lambda i: sum(M[i][x] for x in members) / len(members))
        per_task.append(M[expert][j])
    return {
        "k": k,
        "mean_success": sum(per_task) / T,
        "gain_vs_best_single": sum(per_task) / T - BEST_SINGLE,
        "capture_of_oracle_gain": (sum(per_task) / T - BEST_SINGLE) / ORACLE_GAIN,
        "clusters": [[TASKS[j] for j in range(T) if assign[j] == c] for c in range(k)],
    }


def main():
    result = {
        "source": "exp/r16/lb_data.py (transcription of leaderboard_data.json, teaser, 2026-11-02)",
        "caveat": "teaser table is self-declared randomly generated; structure-level only",
        "baseline": {
            "best_single_model": MODELS[BEST_IDX][0],
            "best_single_success": BEST_SINGLE,
            "per_task_oracle": ORACLE,
            "oracle_gain": ORACLE_GAIN,
            "winner_counts": {
                MODELS[i][0]: sum(1 for j in range(T)
                                  if M[i][j] == max(M[x][j] for x in range(N)))
                for i in range(N)
            },
        },
        "deployable_text_routers": {},
        "leaky_profile_routers": {},
        "coarse_family_routers": {},
    }

    for name, sim in TEXT_FEATURES.items():
        for k in (1, 3):
            r = route_loto(sim, k)
            r["bootstrap"] = bootstrap_gain(r["per_task"])
            r.pop("picks", None) if k == 3 else None
            result["deployable_text_routers"][f"{name}_k{k}"] = r

    for k in (1, 3):
        r = route_leaky_profile(k)
        r["bootstrap"] = bootstrap_gain(r["per_task"])
        result["leaky_profile_routers"][f"profile_k{k}"] = r

    for k in (2, 3, 4, 5, 6, 8):
        result["coarse_family_routers"][f"kmeans_k{k}"] = cluster_loo(k)

    deltas = [max(M[i][j] for i in range(N)) - M[BEST_IDX][j] for j in range(T)]
    result["per_task_oracle_delta"] = {
        "all_nonnegative": all(d >= -1e-9 for d in deltas),
        "sum_pp": sum(deltas),
        "n_gt_5pp": sum(1 for d in deltas if d > 5),
        "max_task": TASKS[deltas.index(max(deltas))],
        "max_pp": max(deltas),
        "n_best_single_already_oracle": sum(1 for d in deltas if d <= 1e-9),
    }

    task_corrs = [corr(COLS[j], COLS[k]) for j in range(T) for k in range(j + 1, T)]
    task_corrs.sort()
    result["task_profile_correlation"] = {
        "mean": sum(task_corrs) / len(task_corrs),
        "median": task_corrs[len(task_corrs) // 2],
        "min": task_corrs[0],
        "max": task_corrs[-1],
        "frac_gt_0.5": sum(1 for x in task_corrs if x > 0.5) / len(task_corrs),
    }

    out = os.path.join(HERE, "route_boundary_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"best_single={BEST_SINGLE:.3f} ({MODELS[BEST_IDX][0]}) "
          f"oracle={ORACLE:.3f} gain={ORACLE_GAIN:.3f}")
    for group in ("deployable_text_routers", "leaky_profile_routers", "coarse_family_routers"):
        for key, r in result[group].items():
            print(f"{group:24s} {key:18s} mean={r['mean_success']:6.3f} "
                  f"gain={r['gain_vs_best_single']:+6.3f} capture={r['capture_of_oracle_gain']:+.1%}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
