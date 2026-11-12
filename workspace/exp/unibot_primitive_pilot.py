"""Pilot: is there a low-rank *shared* action subspace across UniBot tasks?

Fetches a mid-episode window of 100 frames from each of 8 public G1_Dex1 datasets
via the HF datasets-server, forms 23-d action vectors
(left_arm 7 + right_arm 7 + grippers 2 + pivot 7), and tests whether a global
low-rank subspace learned on *other* tasks explains a held-out task's
frame-to-frame action deltas.

This is a mechanism sanity check, not a UniBot leaderboard result.
"""
import json
import urllib.request
import numpy as np

TASKS = ["HangCup", "ArrangePlates", "FoldTowel", "PlugCharger",
         "DisconnectEthernet", "PourOutMedicine", "PaperCupStacking",
         "OrganizeBookshelf"]
FIELDS = ["action.left_arm", "action.right_arm", "action.left_gripper",
          "action.right_gripper", "action.pivot"]


def fetch(task, offset, n=100):
    url = (f"https://datasets-server.huggingface.co/rows?dataset="
           f"unitreerobotics%2FG1_Dex1_{task}&config=default&split=train"
           f"&offset={offset}&length={n}")
    last = None
    for k in range(6):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return json.load(r)
        except Exception as e:
            last = e
            import time
            time.sleep(8 + 4 * k)
    raise last


def vec(row):
    out = []
    for f in FIELDS:
        v = row[f]
        out.extend(v if isinstance(v, list) else [v])
    return np.asarray(out, dtype=np.float64)


def task_deltas(task):
    import os
    cache = f"exp/.cache_{task}.npy"
    if os.path.exists(cache):
        return np.load(cache)
    meta = fetch(task, 0, 1)
    total = meta["num_rows_total"]
    off = max(0, total // 2)
    d = fetch(task, off, 100)
    X = np.stack([vec(r["row"]) for r in d["rows"]])
    D = np.diff(X, axis=0)             # 99 x 23
    np.save(cache, D)
    return D


def pca_basis(D, k):
    mu = D.mean(0, keepdims=True)
    C = np.cov((D - mu).T)
    w, V = np.linalg.eigh(C)
    idx = np.argsort(w)[::-1][:k]
    return mu, V[:, idx]


def residual_frac(D, mu, V):
    Z = D - mu
    R = Z - (Z @ V) @ V.T
    return float((R ** 2).sum() / max((Z ** 2).sum(), 1e-12))


def main():
    data = {t: task_deltas(t) for t in TASKS}
    res = {"tasks": TASKS, "dims": int(data[TASKS[0]].shape[1]),
           "per_task": {}, "shared": {}, "between_within": {}}

    allD = np.concatenate([data[t] for t in TASKS], 0)
    for t in TASKS:
        D = data[t]
        res["per_task"][t] = {
            "n": int(len(D)),
            "delta_rms": float(np.sqrt((D ** 2).mean())),
            "pca_var_top": [float(x) for x in np.sort(np.linalg.eigvalsh(
                np.cov(D.T)))[::-1][:8] / max(np.trace(np.cov(D.T)), 1e-12)],
        }

    for K in [2, 4, 6, 8]:
        rows = {}
        for t in TASKS:
            train = np.concatenate([data[u] for u in TASKS if u != t], 0)
            mu, V = pca_basis(train, K)
            rows[t] = {
                "shared_resid": residual_frac(data[t], mu, V),
                "own_resid": residual_frac(data[t], *pca_basis(data[t], K)),
            }
        res["shared"][f"K={K}"] = {
            "mean_shared_resid": float(np.mean([r["shared_resid"] for r in rows.values()])),
            "mean_own_resid": float(np.mean([r["own_resid"] for r in rows.values()])),
            "per_task": rows,
        }

    means = np.stack([data[t].mean(0) for t in TASKS])
    gm = allD.mean(0)
    between = float(((means - gm) ** 2).sum(1).mean())
    within = float(np.mean([((data[t] - data[t].mean(0)) ** 2).sum(1).mean() for t in TASKS]))
    res["between_within"] = {"between": between, "within": within,
                             "ratio_between_over_within": between / max(within, 1e-12)}

    # task affinity: cosine of mean delta vectors and subspace overlap (top-3)
    aff = {}
    for i, a in enumerate(TASKS):
        for b in TASKS[i + 1:]:
            ma, mb = data[a].mean(0), data[b].mean(0)
            c = float(ma @ mb / max(np.linalg.norm(ma) * np.linalg.norm(mb), 1e-12))
            _, Va = pca_basis(data[a], 3)
            _, Vb = pca_basis(data[b], 3)
            s = np.linalg.svd(Va.T @ Vb, compute_uv=False)
            aff[f"{a}|{b}"] = {"cos_mean_delta": c,
                               "subspace_overlap": float(np.mean(s))}
    res["affinity"] = aff

    # rank / variance budget: how many shared vs per-task dims are needed
    allcov = np.cov(allD.T)
    ev = np.sort(np.linalg.eigvalsh(allcov))[::-1]
    cum = np.cumsum(ev) / max(ev.sum(), 1e-12)
    res["global_pca_cumvar"] = {str(k): float(cum[k - 1]) for k in range(1, 13)}
    res["per_task_rank"] = {}
    for t in TASKS:
        D = data[t]
        e = np.sort(np.linalg.eigvalsh(np.cov(D.T)))[::-1]
        c = np.cumsum(e) / max(e.sum(), 1e-12)
        r95 = int(np.searchsorted(c, 0.95) + 1)
        r99 = int(np.searchsorted(c, 0.99) + 1)
        # residual rank after global K=8 subspace
        mu, V = pca_basis(allD, 8)
        Z = D - mu
        R = Z - (Z @ V) @ V.T
        er = np.sort(np.linalg.eigvalsh(np.cov(R.T)))[::-1]
        cr = np.cumsum(er) / max(er.sum(), 1e-12)
        rr95 = int(np.searchsorted(cr, 0.95) + 1)
        res["per_task_rank"][t] = {"own_rank95": r95, "own_rank99": r99,
                                   "residual_rank95_after_global8": rr95}

    with open("exp/unibot_primitive_pilot.json", "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: res[k] for k in ("dims", "between_within")}, indent=1))
    for K, v in res["shared"].items():
        print(K, "shared_resid=%.3f own_resid=%.3f" % (
            v["mean_shared_resid"], v["mean_own_resid"]))
    print("global PCA cumvar:", {k: round(v, 3) for k, v in res["global_pca_cumvar"].items()})
    print("per-task ranks:", res["per_task_rank"])
    print("affinity extremes:")
    for k, v in sorted(aff.items(), key=lambda kv: kv[1]["cos_mean_delta"])[:3]:
        print(" low", k, round(v["cos_mean_delta"], 3), round(v["subspace_overlap"], 3))
    for k, v in sorted(aff.items(), key=lambda kv: kv[1]["cos_mean_delta"])[-3:]:
        print(" high", k, round(v["cos_mean_delta"], 3), round(v["subspace_overlap"], 3))


if __name__ == "__main__":
    main()
