"""Pilot: the sharing-vs-conflict tradeoff behind task-affinity grouping.

Toy mean-estimation analogue of multi-task action-head learning:
  * shared/global head      : one parameter for all tasks (max sharing)
  * independent head        : one parameter per task (no sharing)
  * oracle-grouped head     : share inside true task groups
  * affinity-grouped (CV)   : cluster per-task estimates, pick #groups by
                              held-out risk (what we can actually do)

Two regimes: (a) tasks really form G groups; (b) tasks are independent.
The point is not to model UniBot, but to make the bias-variance tradeoff that
motivates 'shared primitive library + task affinity grouping' explicit.
"""
import json
import numpy as np

D, T, G = 4, 32, 4
NOISE = 1.0
SEEDS = 8


def kmeans(X, k, iters=30, seed=0):
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(iters):
        lab = ((X[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)
        for j in range(k):
            if (lab == j).any():
                C[j] = X[lab == j].mean(0)
    return lab, C


def grouped_predict(Xtr, ytr, Xte, k, seed=0):
    lab, C = kmeans(Xtr, k, seed=seed)
    means = np.stack([ytr[lab == j].mean(0) if (lab == j).any() else C[j]
                      for j in range(k)])
    lab_te = ((Xte[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)
    return means[lab_te]


def run(regime, n, seed):
    rng = np.random.default_rng(seed)
    if regime == "grouped":
        centers = rng.normal(0, 1.0, (G, D))
        g = rng.integers(0, G, T)
        theta = centers[g] + rng.normal(0, 0.2, (T, D))
    else:                                   # independent tasks
        theta = rng.normal(0, 1.0, (T, D))

    Xtr, ytr, Xte, yte = [], [], [], []
    for i in range(T):
        Xtr.append(np.full((n, D), i))
        ytr.append(rng.normal(theta[i], NOISE, (n, D)))
        Xte.append(np.full((50, D), i))
        yte.append(rng.normal(theta[i], NOISE, (50, D)))
    Xtr, ytr = np.concatenate(Xtr), np.concatenate(ytr)
    Xte, yte = np.concatenate(Xte), np.concatenate(yte)

    def mse(pred):
        return float(((pred - yte) ** 2).mean())

    # global
    pred_global = np.tile(ytr.mean(0), (len(yte), 1))
    # independent: per-task mean
    ind = np.stack([ytr[Xtr[:, 0] == i].mean(0) for i in range(T)])
    pred_ind = ind[Xte[:, 0].astype(int)]

    # oracle groups (only exists in grouped regime)
    if regime == "grouped":
        orc = np.stack([ytr[g[Xtr[:, 0].astype(int)] == j].mean(0)
                        for j in range(G)])
        pred_orc = orc[g[Xte[:, 0].astype(int)]]
    else:
        pred_orc = pred_ind

    # CV-selected affinity grouping over per-task estimates
    best = (None, np.inf)
    for k in [1, 2, 4, 8, 16, T]:
        # split each task's samples in half, fit on half, score on other half
        rng2 = np.random.default_rng(seed + 99)
        sc = []
        for fold in range(2):
            m = np.zeros(len(Xte), bool)
            for i in range(T):
                idx = np.where(Xtr[:, 0] == i)[0]
                rng2.shuffle(idx)
                m[idx[fold::2]] = True
            p = grouped_predict(Xtr[m], ytr[m], Xtr[~m], k, seed=seed + fold)
            sc.append(((p - ytr[~m]) ** 2).mean())
        risk = float(np.mean(sc))
        if risk < best[1]:
            best = (k, risk)
    kbest = best[0]
    pred_aff = grouped_predict(Xtr, ytr, Xte, kbest, seed=seed)

    return dict(global_=mse(pred_global), independent=mse(pred_ind),
                oracle_grouped=mse(pred_orc), affinity_grouped=mse(pred_aff),
                k_selected=int(kbest))


def main():
    out = {}
    for regime in ["grouped", "independent"]:
        for n in [5, 20, 100]:
            rs = [run(regime, n, s) for s in range(SEEDS)]
            agg = {k: float(np.mean([r[k] for r in rs])) for k in
                   ["global_", "independent", "oracle_grouped",
                    "affinity_grouped"]}
            agg["k_selected"] = float(np.mean([r["k_selected"] for r in rs]))
            out[f"{regime}|n={n}"] = agg
            print(regime, "n=%3d" % n, {k: round(v, 3) for k, v in agg.items()})
    with open("exp/unibot_mtl_pilot.json", "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
