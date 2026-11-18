"""Plant identification probe: can a linear ARX model predict joint state
better than persistence / last-command baselines, on held-out frames?

s[t+1] = A s[t] + B u[t-d] + c, per task, fitted by ridge least squares.
d = 3 frames is measured from the action->state error curve.
"""
import glob, json, os, re
from collections import defaultdict
import numpy as np

CACHE = "exp/duo_rows_cache"
D = 3
RIDGE = 1e-3


def task_of(f):
    return re.match(r"(.+)_(\d+)\.json$", os.path.basename(f)).group(1)


def load_segments(task):
    by = defaultdict(list)
    for f in sorted(glob.glob(f"{CACHE}/{task}_*.json")):
        for it in json.load(open(f)).get("rows", []):
            by[it["row"]["episode_index"]].append(it["row"])
    segs = []
    for ep, rows in sorted(by.items()):
        rows.sort(key=lambda r: r["frame_index"])
        cur = []
        for r in rows:
            if cur and r["frame_index"] != cur[-1]["frame_index"] + 1:
                if len(cur) >= 30:
                    segs.append(cur)
                cur = []
            cur.append(r)
        if len(cur) >= 30:
            segs.append(cur)
    return segs


def arr(rows, key):
    return np.array([r[key] for r in rows], float)


def fit_task(task):
    segs = load_segments(task)
    Xs, Ys = [], []
    for rows in segs:
        for side in ("left", "right"):
            S = arr(rows, f"observation.state.{side}_arm")
            A = arr(rows, f"action.{side}_arm")
            for t in range(D, len(S) - 1):
                Xs.append(np.concatenate([S[t], A[t - D], [1.0]]))
                Ys.append(S[t + 1])
    X = np.array(Xs); Y = np.array(Ys)
    n = len(X)
    cut = int(n * 0.7)
    Xtr, Ytr, Xte, Yte = X[:cut], Y[:cut], X[cut:], Y[cut:]
    # ridge closed form
    W = np.linalg.solve(Xtr.T @ Xtr + RIDGE * np.eye(Xtr.shape[1]), Xtr.T @ Ytr)
    pred = Xte @ W
    rmse = float(np.sqrt(np.mean((pred - Yte) ** 2)))
    # baselines
    s_t = Xte[:, :7]
    u_lag = Xte[:, 7:14]
    base_persist = float(np.sqrt(np.mean((s_t - Yte) ** 2)))
    base_cmd = float(np.sqrt(np.mean((u_lag - Yte) ** 2)))
    # one-step R^2
    ss = np.sum((Yte - Yte.mean(axis=0)) ** 2) + 1e-12
    r2 = float(1.0 - np.sum((pred - Yte) ** 2) / ss)
    return {"n": int(n), "n_train": int(cut), "n_test": int(n - cut),
            "rmse_model": rmse, "rmse_persist": base_persist,
            "rmse_last_cmd": base_cmd, "r2": r2}


def main():
    tasks = sorted({task_of(f) for f in glob.glob(f"{CACHE}/*.json")})
    out = {"delay_frames": D, "tasks": {}}
    for task in tasks:
        r = fit_task(task)
        out["tasks"][task] = r
        print(f"{task:22s} rmse model={r['rmse_model']:.5f} persist={r['rmse_persist']:.5f} "
              f"last_cmd={r['rmse_last_cmd']:.5f} R2={r['r2']:.4f}")
    ms = np.array([v["rmse_model"] for v in out["tasks"].values()])
    ps = np.array([v["rmse_persist"] for v in out["tasks"].values()])
    cs = np.array([v["rmse_last_cmd"] for v in out["tasks"].values()])
    out["summary"] = {
        "model_med": float(np.median(ms)), "persist_med": float(np.median(ps)),
        "last_cmd_med": float(np.median(cs)),
        "improve_vs_persist": float(1 - np.median(ms / ps)),
        "improve_vs_last_cmd": float(1 - np.median(ms / cs)),
        "n_tasks_model_better_persist": int(np.sum(ms < ps)),
        "n_tasks_model_better_last_cmd": int(np.sum(ms < cs)),
        "n_tasks": len(ms),
    }
    json.dump(out, open("exp/plantid_probe_results.json", "w"), indent=2)
    print("\nSUMMARY", json.dumps(out["summary"], indent=2))


if __name__ == "__main__":
    main()
