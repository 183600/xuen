"""Synthetic mechanism checks for UniBot-SPECTRA (round: 视觉编码器 x 持续学习).

NOT benchmark evidence.  Every number here is a *simulation* with a declared
generative model and a fixed seed.  The goal is to isolate three claims that the
write-up uses, so that they can be falsified cheaply before any GPU is spent:

  (A) the invariance/utility trade-off: making a visual encoder invariant to a
      nuisance axis helps under shift *iff* that axis is not label-predictive in
      the source domain; over-invariance to a spuriously-correlated nuisance
      destroys source accuracy while helping the shifted domain.
  (B) forgetting on continual tasks is asymmetric: with a fixed plasticity
      budget, low-sample (hard / last-mile) tasks are forgotten more; replay
      reduces it, and *correct* subspace anchoring reduces it at no plasticity
      cost, whereas *over*-anchoring trades forgetting for plasticity.
  (C) geometry-core replay (k-center / leverage selection in the geometry
      embedding) covers a low-rank task-relevant subspace with fewer samples
      than random replay at the same budget.

The generative models are declared in each function, not fitted to real data.
"""
import json
import os

import numpy as np

rng = np.random.default_rng(20261119)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "spectra_results.json")


# ------------------------------------------------------------------ helpers
def orthonormal(p, r, rng):
    a = rng.normal(size=(p, r))
    q, _ = np.linalg.qr(a)
    return q[:, :r]


# ------------------------------------------------------- (A) invariance/util
def _gen_invariance(n, d_geo, d_nui, corr, rng, ood=False):
    g = rng.normal(size=(n, d_geo))
    a = np.linspace(1.0, 0.4, d_geo)
    a /= np.linalg.norm(a)
    y = np.where(g @ a >= 0, 1.0, -1.0)
    mu = np.linspace(0.8, 0.2, d_nui)
    if corr:
        sign = -1.0 if ood else 1.0          # OOD breaks the spurious cue
        nui = sign * y[:, None] * mu[None, :] + rng.normal(scale=0.7, size=(n, d_nui))
    else:
        nui = rng.normal(scale=1.0, size=(n, d_nui))
        if ood:                               # pure distribution shift
            nui = nui * 1.6 + 0.9
    x = np.concatenate([g, nui], axis=1)
    return x, y


def run_invariance(n=24000, d_geo=10, d_nui=10):
    """Ridge readout, then attenuate nuisance weights by 1/(1+lambda).

    The attenuation models an invariance penalty that shrinks the encoder's
    sensitivity to nuisance dimensions.  It is deliberately simple: we want to
    read the *direction* of the trade-off, not a benchmark number.
    """
    grid = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]
    out = {}
    for regime, corr in (("independent", False), ("spurious", True)):
        x_tr, y_tr = _gen_invariance(n, d_geo, d_nui, corr, rng, ood=False)
        x_id, y_id = _gen_invariance(n // 2, d_geo, d_nui, corr, rng, ood=False)
        x_ood, y_ood = _gen_invariance(n // 2, d_geo, d_nui, corr, rng, ood=True)
        # closed-form ridge readout on the full observation
        lam = 1.0
        A = x_tr.T @ x_tr + lam * np.eye(x_tr.shape[1])
        w = np.linalg.solve(A, x_tr.T @ y_tr)
        rows = []
        for l in grid:
            w2 = w.copy()
            w2[d_geo:] /= (1.0 + l)
            acc_id = float(np.mean(np.sign(x_id @ w2) == y_id))
            acc_ood = float(np.mean(np.sign(x_ood @ w2) == y_ood))
            rows.append({"lambda": l, "acc_id": acc_id, "acc_ood": acc_ood,
                         "gap": acc_id - acc_ood})
        best = max(rows, key=lambda r: r["acc_ood"])
        out[regime] = {"rows": rows, "best_lambda_ood": best["lambda"],
                       "best_acc_ood": best["acc_ood"],
                       "acc_id_at_best": best["acc_id"]}
    return out


# ------------------------------------------------- (B) continual forgetting
def run_continual(n_tasks=8, p=120, r_prot=6, r_task=10, steps=260,
                  lr=0.06, replay_beta=0.55, noise=0.42):
    Q_prot = orthonormal(p, r_prot, rng)
    Q_task = orthonormal(p, r_task, rng)
    # make task basis orthogonal to the protected subspace
    Q_task = Q_task - Q_prot @ (Q_prot.T @ Q_task)
    Q_task, _ = np.linalg.qr(Q_task)
    Q_task = Q_task[:, :r_task]

    s = rng.normal(size=r_prot)
    b = rng.normal(size=(n_tasks, r_task))
    targets = [Q_prot @ s + Q_task @ b[t] for t in range(n_tasks)]
    # low-sample -> high gradient noise; hard tasks have fewer episodes
    n_samples = np.array([50, 80, 120, 200, 300, 450, 650, 900], dtype=float)

    def loss(theta, t):
        d = theta - targets[t]
        return 0.5 * float(d @ d)

    def run(method, seed):
        r = np.random.default_rng(seed)
        theta = np.zeros(p)
        learned = np.zeros(n_tasks)
        for t in range(n_tasks):
            # a task-agnostic replay buffer of previous targets
            prev = targets[:t]
            for _ in range(steps):
                g = theta - targets[t]
                if method == "replay" and prev:
                    g = g + replay_beta * np.mean(
                        [theta - tp for tp in prev], axis=0)
                if method == "freeze_before_learn":
                    g = g - Q_prot @ (Q_prot.T @ g)
                elif method == "anchor_over":
                    frozen = np.concatenate([Q_prot, Q_task[:, :r_task // 2]], axis=1)
                    freeze_basis, _ = np.linalg.qr(frozen)
                    g = g - freeze_basis @ (freeze_basis.T @ g)
                scale = noise / np.sqrt(n_samples[t] / 100.0)
                theta = theta - lr * (g + scale * r.normal(size=p))
            learned[t] = loss(theta, t)
        final = np.array([loss(theta, t) for t in range(n_tasks)])
        forget = final - learned
        order = np.argsort(n_samples)
        low = forget[order[: n_tasks // 2]]
        high = forget[order[n_tasks // 2:]]
        return {
            "final_avg_loss": float(final.mean()),
            "forgetting_avg": float(forget.mean()),
            "forgetting_worst": float(forget.max()),
            "forgetting_low_sample": float(low.mean()),
            "forgetting_high_sample": float(high.mean()),
            "bwt": float(np.mean(learned - final)),
            "final_loss_per_task": [float(v) for v in final],
        }

    methods = ["naive", "replay", "freeze_before_learn", "anchor_over"]
    seeds = range(6)
    agg = {}
    for m in methods:
        runs = [run(m, 1000 + s) for s in seeds]
        agg[m] = {
            k: float(np.mean([r[k] for r in runs]))
            for k in ("final_avg_loss", "forgetting_avg", "forgetting_worst",
                      "forgetting_low_sample", "forgetting_high_sample", "bwt")
        }
        agg[m]["final_loss_per_task"] = [
            float(np.mean([r["final_loss_per_task"][i] for r in runs]))
            for i in range(n_tasks)]
    agg["_meta"] = {"n_tasks": n_tasks, "p": p, "r_prot": r_prot,
                    "r_task": r_task, "steps": steps,
                    "n_samples": n_samples.tolist()}
    return agg


# --------------------------------------------- (C) geometry-core coverage
def run_coverage(d=32, n=900, m=32, trials=40):
    """Geometry-core replay vs random / leverage under a fixed budget.

    Data model: an imbalanced mixture of `d` orthogonal modes in R^d (rare
    modes are the analogue of rare object/task variants).  A balanced test set
    is scored by a linear readout fit on only `m` selected samples.  Random
    replay misses rare modes; k-center selection covers the geometry.
    """
    methods = ["random", "leverage", "kcenter"]
    errs = {k: [] for k in methods}
    cover = {k: [] for k in methods}
    for _ in range(trials):
        p = 1.0 / np.arange(1, d + 1) ** 1.3
        p /= p.sum()
        comp = rng.choice(d, size=n, p=p)
        centers = 3.0 * np.eye(d)
        z = centers[comp] + rng.normal(scale=0.4, size=(n, d))
        w = rng.normal(size=d)
        w[:4] *= 3.0
        y = z @ w
        tc = rng.integers(0, d, size=2000)
        zt = centers[tc] + rng.normal(scale=0.4, size=(2000, d))
        yt = zt @ w

        idx = {}
        idx["random"] = rng.choice(n, size=m, replace=False)
        lev = np.einsum("ij,jk,ik->i", z,
                        np.linalg.pinv(z.T @ z + 1e-6 * np.eye(d)), z)
        idx["leverage"] = np.argsort(lev)[-m:]
        chosen = [int(rng.integers(n))]
        d2 = np.sum((z - z[chosen[0]]) ** 2, axis=1)
        for _ in range(m - 1):
            j = int(np.argmax(d2))
            chosen.append(j)
            d2 = np.minimum(d2, np.sum((z - z[j]) ** 2, axis=1))
        idx["kcenter"] = np.array(chosen)

        for k in methods:
            zs, ys = z[idx[k]], y[idx[k]]
            beta = np.linalg.solve(zs.T @ zs + 1e-4 * np.eye(d), zs.T @ ys)
            errs[k].append(float(np.mean((zt @ beta - yt) ** 2)))
            cover[k].append(len(set(comp[idx[k]].tolist())))
    return {k: {"mse_mean": float(np.mean(errs[k])),
                "mse_p90": float(np.percentile(errs[k], 90)),
                "modes_covered": float(np.mean(cover[k])),
                "modes_total": d}
            for k in methods}


def main():
    out = {
        "seed": 20261119,
        "note": "synthetic mechanism checks, NOT benchmark evidence",
        "A_invariance_utility": run_invariance(),
        "B_continual_forgetting": run_continual(),
        "C_geometry_core_coverage": run_coverage(),
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
