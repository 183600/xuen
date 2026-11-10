"""Synthetic mechanism check for round 42 (scene understanding x data scale).

Question: under a skewed, success-only, highly redundant demo distribution, does
selecting data by SCENE COVERAGE beat selecting by raw episode count (random)?
And where (mean vs. worst-group vs. held-out attributes) does the gain appear?

Transparent toy, NOT benchmark evidence. It only checks direction/shape.
"""
import json
import itertools
import numpy as np

RNG = np.random.default_rng(0)

SHAPES = ["box", "cylinder", "sphere", "mug"]
MATS = ["rigid", "soft", "slippery", "rough"]
SIZES = ["S", "M", "L"]
DISTS = ["none", "one", "two"]
BGS = ["wood", "white", "cluttered"]
DIMS = [len(SHAPES), len(MATS), len(SIZES), len(DISTS), len(BGS)]

cells = list(itertools.product(*[range(d) for d in DIMS]))
cell_index = {c: i for i, c in enumerate(cells)}
N_CELLS = len(cells)

def onehot(c):
    v = np.zeros(sum(DIMS))
    off = 0
    for k, d in enumerate(DIMS):
        v[off + c[k]] = 1.0
        off += d
    return v

X = np.stack([onehot(c) for c in cells])
group_slices, off = [], 0
for d in DIMS:
    group_slices.append((off, off + d))
    off += d
D = np.zeros((N_CELLS, N_CELLS))
for a, b in group_slices:
    D += (X[:, None, a:b] != X[None, :, a:b]).sum(-1) / (b - a)
D /= len(group_slices)
K = np.exp(-(D ** 2) / (2 * 0.16 ** 2))
TAU = 40.0

def difficulty(c):
    sh, ma, si, di, bg = c
    d = 0.0
    d += [0.0, 0.25, 0.75, 0.5][sh]
    d += [0.0, 0.45, 0.85, 0.2][ma]
    d += [0.35, 0.0, 0.45][si]
    d += [0.0, 0.45, 0.8][di]
    d += [0.0, 0.1, 0.5][bg]
    if sh == 2 and ma == 2: d += 0.6
    if sh == 3 and ma == 1: d += 0.35
    if si == 2 and di == 2: d += 0.4
    return d

DIFF = np.array([difficulty(c) for c in cells])
P_MAX = 1.0 / (1.0 + np.exp(-(2.6 - DIFF)))
HELD_OUT = np.array([c[0] == 2 or c[1] == 3 for c in cells])  # sphere OR rough: never collected

# 75% of demos pile onto a few easy "factory" scenes; 25% spread by difficulty.
factory = np.array([cell_index[(0, 0, 1, 0, bg)] for bg in range(len(BGS))], dtype=int)
q_spread = -1.2 * DIFF
q_spread[HELD_OUT] = -np.inf
q_spread = np.exp(q_spread - q_spread[~np.isinf(q_spread)].max())
q_spread[~np.isfinite(q_spread)] = 0.0
q_spread = q_spread / q_spread.sum()
q = 0.75 * np.eye(N_CELLS)[factory].sum(0) / len(factory) + 0.25 * q_spread
q = q / q.sum()

def coverage(sel):
    if len(sel) == 0:
        return np.zeros(N_CELLS)
    s = K[sel].sum(0)
    return 1.0 - np.exp(-s / TAU)

def success_from_coverage(cov, floor=0.12):
    return P_MAX * (floor + (1 - floor) * cov)

def greedy(unique_counts, b, weights=None):
    if weights is None:
        weights = np.ones(N_CELLS)
    avail = dict(unique_counts)
    s = np.zeros(N_CELLS)
    base = weights.copy()
    chosen = []
    for _ in range(b):
        if not avail:
            break
        cs = np.array(list(avail.keys()), dtype=int)
        Kc = K[cs]
        gains = (base[None, :] * (1.0 - np.exp(-Kc / TAU))).sum(1)
        j = int(np.argmax(gains))
        if gains[j] <= 1e-12:
            break
        c = int(cs[j])
        chosen.append(c)
        avail[c] -= 1
        if avail[c] <= 0:
            del avail[c]
        s += K[c]
        base = weights * np.exp(-s / TAU)
    return np.array(chosen, dtype=int)

def greedy_rare(unique_counts, b):
    order = sorted(unique_counts, key=lambda c: (unique_counts[c], -DIFF[c]))
    return np.array(order[:b], dtype=int)

def kcenter(unique_cells, b):
    if len(unique_cells) == 0:
        return np.array([], dtype=int)
    chosen = [unique_cells[0]]
    while len(chosen) < min(b, len(unique_cells)):
        dmin = np.min(D[np.ix_(unique_cells, chosen)], axis=1)
        nxt = int(np.argmax(dmin))
        cand = unique_cells[nxt]
        if cand in chosen:
            break
        chosen.append(cand)
    return np.array(chosen[:b], dtype=int)

def evaluate(sel, name):
    cov = coverage(sel)
    succ = success_from_coverage(cov)
    return {
        "name": name,
        "mean_success": float(succ.mean()),
        "worst20_success": float(np.sort(succ)[:max(1, N_CELLS // 5)].mean()),
        "heldout_success": float(succ[HELD_OUT].mean()),
        "n_eff_cells": float((cov >= 0.5).sum()),
        "mean_cov": float(cov.mean()),
        "n_unique_selected": int(len(np.unique(sel))),
    }

N_POOL = 20000
pool = RNG.choice(N_CELLS, size=N_POOL, p=q)
unique, counts = np.unique(pool, return_counts=True)
unique_counts = {int(u): int(c) for u, c in zip(unique, counts)}

budgets = [10, 20, 40, 80, 160, 200, 243, 320, 640, 1000, 2000]
results = {"budgets": budgets, "policies": {}}

for pol in ["random", "coverage", "weighted", "rare", "kcenter"]:
    results["policies"][pol] = []
    for b in budgets:
        reps = 8 if pol in ("random", "rare") else 1
        acc = []
        for _ in range(reps):
            if pol == "random":
                sel = RNG.choice(pool, size=min(b, N_POOL), replace=False)
            elif pol == "coverage":
                sel = greedy(unique_counts, b)
            elif pol == "weighted":
                sel = greedy(unique_counts, b, weights=P_MAX)
            elif pol == "rare":
                sel = greedy_rare(unique_counts, b)
            else:
                sel = kcenter([int(u) for u in unique], b)
            acc.append(evaluate(sel, pol))
        agg = {k: float(np.mean([a[k] for a in acc])) for k in
               ["mean_success", "worst20_success", "heldout_success",
                "n_eff_cells", "mean_cov", "n_unique_selected"]}
        agg["budget"] = b
        results["policies"][pol].append(agg)

# ceiling: all 20k demos
s_full = np.array([unique_counts.get(i, 0) for i in range(N_CELLS)]) @ K
cov_full = 1.0 - np.exp(-s_full / TAU)
succ_full = success_from_coverage(cov_full)
results["full_data"] = {
    "name": "full_pool",
    "mean_success": float(succ_full.mean()),
    "worst20_success": float(np.sort(succ_full)[:max(1, N_CELLS // 5)].mean()),
    "heldout_success": float(succ_full[HELD_OUT].mean()),
    "n_eff_cells": float((cov_full >= 0.5).sum()),
    "mean_cov": float(cov_full.mean()),
    "n_unique_selected": int(len(unique)),
}
results["pool"] = {
    "n_pool": int(N_POOL),
    "n_unique_cells": int(len(unique)),
    "n_cells_possible": int(N_CELLS),
    "heldout_cells": int(HELD_OUT.sum()),
    "top1_cell_share": float(counts.max() / N_POOL),
    "effective_by_raw": float(len(unique)),
}

with open("coverage_results.json", "w") as f:
    json.dump(results, f, indent=2)
print(json.dumps({k: results[k] for k in ["pool", "full_data"]}, indent=2))
for pol, rows in results["policies"].items():
    print("\n==", pol)
    for x in rows:
        print(f"B={x['budget']:5d} mean={x['mean_success']:.3f} "
              f"worst20={x['worst20_success']:.3f} held={x['heldout_success']:.3f} "
              f"neff={x['n_eff_cells']:.0f} uniq={x['n_unique_selected']:.0f} "
              f"cov={x['mean_cov']:.3f}")
