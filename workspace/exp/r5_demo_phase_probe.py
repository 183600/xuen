"""Round-5 probe: can demonstration state trajectories anchor a progress estimate?
Uses only official G1_Dex1 state/action traces fetched from HF (exp/unibot_states).
D-level: proprio-only, no images; tests whether demo time is a learnable state functional
and whether its temporal derivative flips on time-reversed (undo) trajectories.
"""
import glob, json, os
import numpy as np
from scipy.stats import spearmanr

EXP = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(EXP, "unibot_states")
OUT = os.path.join(EXP, "r5_demo_phase_probe.json")

STATE_KEYS = [
    "observation.state.left_arm", "observation.state.right_arm",
    "observation.state.left_gripper", "observation.state.right_gripper",
    "observation.state.left_ee_pose_gripper_base",
    "observation.state.right_ee_pose_gripper_base",
    "observation.state.lower_body",
]

def load_episodes(p):
    d = np.load(p, allow_pickle=True)
    eps = []
    for split in d.files:
        e = d[split].item()
        idx = np.asarray(e["episode_index"]).astype(int)
        fi = np.asarray(e["frame_index"]).astype(int)
        for u in np.unique(idx):
            m = idx == u
            if m.sum() < 30:
                continue
            order = np.argsort(fi[m])
            if np.any(np.diff(fi[m][order]) <= 0):
                continue
            X = np.concatenate([np.asarray(e[k], float)[m][order].reshape(m.sum(), -1)
                                for k in STATE_KEYS], axis=1)
            t = fi[m][order].astype(float)
            eps.append((X, t, split))
    return eps

def feats(X):
    d1 = np.diff(X, axis=0, prepend=X[:1])
    d5 = X - np.concatenate([np.repeat(X[:1], min(5, len(X)), 0), X[:-min(5, len(X))]], 0)
    return np.c_[X, d1, d5]

def fit_ridge(A, y, lam=1e-2):
    A1 = np.c_[A, np.ones(len(A))]
    return np.linalg.solve(A1.T @ A1 + lam * np.eye(A1.shape[1]), A1.T @ y)

def predict(w, A):
    return np.c_[A, np.ones(len(A))] @ w

def main():
    out = {}
    for p in sorted(glob.glob(os.path.join(STATE, "*.npz"))):
        name = os.path.basename(p)[:-4]
        eps = [e for e in load_episodes(p) if e[2] == "contig"]
        if not eps:
            continue
        # per-task feature standardization on all frames (unsupervised)
        allX = np.concatenate([feats(X) for X, _, _ in eps], 0)
        mu, sd = allX.mean(0), allX.std(0)
        sd[sd < 1e-8] = 1.0
        data = []
        for X, t, _ in eps:
            A = (feats(X) - mu) / sd
            y = (t - t.min()) / max(t.max() - t.min(), 1e-9)
            data.append((A, y))
        # leave-one-episode-out when possible, else temporal 80/20
        scores, order_acc, rev_order_acc, rev_deriv = [], [], [], []
        for i, (A, y) in enumerate(data):
            if len(data) >= 2:
                tr = [j for j in range(len(data)) if j != i]
                trA = np.concatenate([data[j][0] for j in tr], 0)
                trY = np.concatenate([data[j][1] for j in tr], 0)
            else:
                n = len(A); cut = int(0.8 * n)
                trA, trY = A[:cut], y[:cut]
            w = fit_ridge(trA, trY)
            yh = predict(w, A)
            rho = spearmanr(yh, y).statistic
            if np.isfinite(rho):
                scores.append(float(rho))
            # order accuracy over random within-episode pairs
            rng = np.random.default_rng(0)
            ii = rng.integers(0, len(y), 400); jj = rng.integers(0, len(y), 400)
            ok = y[ii] != y[jj]
            order_acc.append(float(np.mean((yh[ii] > yh[jj]) == (y[ii] > y[jj]))))
            # time-reversed version of same episode (undo)
            Ar, yr = A[::-1], y[::-1]
            yhr = predict(w, Ar)
            okr = y[ii] != y[jj]
            rev_order_acc.append(float(np.mean((yhr[ii] > yhr[jj]) == (yr[ii] > yr[jj]))))
            # derivative sign on reversed trajectory: should be mostly negative
            d = np.diff(yhr)
            rev_deriv.append(float(np.mean(d < 0)))
        out[name] = {
            "n_episodes": len(data),
            "phase_spearman_mean": round(float(np.mean(scores)), 4) if scores else None,
            "forward_order_acc": round(float(np.mean(order_acc)), 4),
            "reversed_order_acc": round(float(np.mean(rev_order_acc)), 4),
            "reversed_negative_derivative_frac": round(float(np.mean(rev_deriv)), 4),
        }
    mean = {k: round(float(np.mean([v[k] for v in out.values() if v[k] is not None])), 4)
            for k in ("phase_spearman_mean", "forward_order_acc",
                      "reversed_order_acc", "reversed_negative_derivative_frac")}
    result = {"note": "proprio-only demo-anchoring probe; no images; D-level",
              "per_task": out, "macro_mean": mean}
    json.dump(result, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(result, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
