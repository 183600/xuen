#!/usr/bin/env python3
"""Round 55 toy mechanism check: region-conditioned multi-task sharing vs
global sharing vs per-task isolation under context shift and context leakage.

This is a *sanity check* of the proposed mechanism, not empirical evidence.
It contains no real robot data; parameters encode the two failure modes argued
in the idea section:

  1. sharing is only beneficial on a region of (task, context) space;
  2. leakage-blind validation (a shared representation using context as a
     shortcut) underestimates harm and over-shares, while a conservative,
     leakage-adjusted certificate rejects the harmful region.

Pure stdlib. Writes round55_ctxshare_results.json next to this file.
"""
import json
import os
import random
import statistics

TASKS = 6
CONTEXTS = 10
HALF = CONTEXTS // 2  # contexts [0,HALF) -> regime 0, [HALF,CONTEXTS) -> regime 1
DELTA_I = 0.05        # negative-transfer threshold: deployed effect < -DELTA_I
BASE_MEAN, BASE_SD = 0.72, 0.015

# True sharing effect (relative to per-task model) per (task, regime).
# Tasks 0..2 are context-entangled: sharing helps in regime 0, hurts in 1.
# Tasks 3..5 are genuinely shared: sharing helps in both regimes.
EFFECT = {
    (0, 0): +0.14, (1, 0): +0.13, (2, 0): +0.15,
    (3, 0): +0.10, (4, 0): +0.10, (5, 0): +0.09,
    (0, 1): -0.22, (1, 1): -0.20, (2, 1): -0.24,
    (3, 1): +0.08, (4, 1): +0.09, (5, 1): +0.08,
}
GENUINE = {3, 4, 5}


def regime(c):
    return 0 if c < HALF else 1


def leak(effect, lam):
    """Context leakage: amplify harm, shrink benefit."""
    return effect * (1.0 + 0.70 * lam) if effect < 0 else effect * (1.0 - 0.40 * lam)


def task_global_effect(t):
    """A context-blind shared model averages each task over contexts."""
    return statistics.mean(EFFECT[(t, regime(c))] for c in range(CONTEXTS))


def certified_mask(rng, r, n_probe=16, noise=0.06, slack=0.01, lam=0.15):
    """Conservative region certificate (IP-122 style).

    Probe, then require a leakage-adjusted lower confidence bound >= -DELTA_I.
    """
    out = {}
    for t in range(TASKS):
        obs = [leak(EFFECT[(t, r)], lam) + rng.gauss(0, noise)
               for _ in range(n_probe)]
        mean = statistics.mean(obs)
        sd = statistics.pstdev(obs) if n_probe > 1 else noise
        lcb = mean - 1.645 * sd / (n_probe ** 0.5) - slack
        out[t] = lcb >= -DELTA_I
    return out


def naive_mask(rng, r, n_probe=16, noise=0.06, hide=0.90):
    """Leakage-blind validation: the context shortcut hides most of the harm,
    and the point estimate (no conservative bound) is accepted if > -DELTA_I.
    """
    out = {}
    for t in range(TASKS):
        e = EFFECT[(t, r)]
        observed = e * (1.0 - hide) if e < 0 else e  # shortcut masks harm
        obs = [observed + rng.gauss(0, noise) for _ in range(n_probe)]
        out[t] = statistics.mean(obs) > -DELTA_I
    return out


def run(trials=40000, seed=20261111, n_probe=16):
    rng = random.Random(seed)
    glob = {t: task_global_effect(t) for t in range(TASKS)}
    cert = {r: certified_mask(rng, r, n_probe) for r in (0, 1)}
    naive = {r: naive_mask(rng, r, n_probe) for r in (0, 1)}
    res = {k: {"succ": [], "neg": 0, "share": 0, "n": 0}
           for k in ("single", "global", "region_naive", "region_cert")}

    for _ in range(trials):
        t = rng.randrange(TASKS)
        c = rng.randrange(CONTEXTS)
        r = regime(c)
        base = rng.gauss(BASE_MEAN, BASE_SD)
        true_e = EFFECT[(t, r)]

        res["single"]["succ"].append(base)
        res["single"]["n"] += 1

        e = leak(glob[t], 0.60) + rng.gauss(0, 0.01)
        res["global"]["succ"].append(min(1.0, base + e))
        res["global"]["neg"] += e < -DELTA_I
        res["global"]["share"] += 1
        res["global"]["n"] += 1

        if naive[r][t]:
            e = leak(true_e, 0.45) + rng.gauss(0, 0.01)
            res["region_naive"]["share"] += 1
        else:
            e = 0.0
        res["region_naive"]["succ"].append(min(1.0, base + e))
        res["region_naive"]["neg"] += e < -DELTA_I
        res["region_naive"]["n"] += 1

        if cert[r][t]:
            e = leak(true_e, 0.15) + rng.gauss(0, 0.01)
            res["region_cert"]["share"] += 1
        else:
            e = 0.0
        res["region_cert"]["succ"].append(min(1.0, base + e))
        res["region_cert"]["neg"] += e < -DELTA_I
        res["region_cert"]["n"] += 1

    out = {}
    for k, v in res.items():
        out[k] = {
            "mean_success": round(statistics.mean(v["succ"]), 4),
            "p05_success": round(sorted(v["succ"])[int(0.05 * len(v["succ"]))], 4),
            "negative_transfer_rate": round(v["neg"] / v["n"], 4),
            "share_rate": round(v["share"] / v["n"], 4),
        }
    out["meta"] = {
        "trials": trials, "n_probe": n_probe, "seed": seed,
        "global_task_effects": {str(t): round(glob[t], 4) for t in range(TASKS)},
        "note": "toy mechanism check, not empirical evidence",
    }
    return out


def by_regime(trials=40000, seed=20261112, n_probe=16):
    rng = random.Random(seed)
    glob = {t: task_global_effect(t) for t in range(TASKS)}
    cert = {r: certified_mask(rng, r, n_probe) for r in (0, 1)}
    acc = {k: {0: [], 1: []} for k in ("single", "global", "region_cert")}
    for _ in range(trials):
        t = rng.randrange(TASKS)
        c = rng.randrange(CONTEXTS)
        r = regime(c)
        base = rng.gauss(BASE_MEAN, BASE_SD)
        true_e = EFFECT[(t, r)]
        acc["single"][r].append(base)
        acc["global"][r].append(min(1.0, base + leak(glob[t], 0.60)
                                    + rng.gauss(0, 0.01)))
        share = cert[r][t]
        e = leak(true_e, 0.15) + rng.gauss(0, 0.01) if share else 0.0
        acc["region_cert"][r].append(min(1.0, base + e))
    return {k: {str(r): round(statistics.mean(v), 4) for r, v in d.items()}
            for k, d in acc.items()}


if __name__ == "__main__":
    out = run()
    out["by_regime"] = by_regime()
    path = os.path.join(os.path.dirname(__file__), "round55_ctxshare_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
