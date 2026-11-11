#!/usr/bin/env python3
"""Round-55 probe: certificate-aware replay vs baselines + depth-quality estimator.

Pure-numpy synthetic probe (NOT a robotics benchmark). It is designed to falsify:
  1) random replay preserves average accuracy but not the certificate-critical set;
  2) the mean depth quality hides a bad support point that the alpha-quantile sees.

Run: python3 exp/cl_depth_probe.py
"""
import sys
sys.path.insert(0, "/home/runner/work/xuen/xuen/workspace/.pylibs")
import numpy as np

RNG = np.random.default_rng(20261111)
D, T, N, BUFFER, STEPS, LR = 20, 12, 500, 240, 300, 0.03
W_SHARED = RNG.normal(size=D) / np.sqrt(D)


def make_task(seed):
    r = np.random.default_rng(seed)
    w = W_SHARED + 0.35 * r.normal(size=D) / np.sqrt(D)
    X = r.normal(size=(N, D))
    y = X @ w + 0.05 * r.normal(size=N)
    lev = np.abs(X @ w)
    idx = np.argsort(lev)[-int(0.2 * N):]          # boundary/high-leverage = C_i
    return X, y, X[idx], y[idx]


TASKS = [make_task(1000 + i) for i in range(T)]


def train(theta, X, y, anchors=None, anchor_w=0.0):
    theta = theta.copy()
    n = len(X)
    for _ in range(STEPS):
        idx = RNG.integers(0, n, size=min(64, n))
        g = 2 * X[idx].T @ (X[idx] @ theta - y[idx]) / len(idx)
        if anchors is not None and anchor_w > 0:
            Xa, ya = anchors
            g = g + anchor_w * (2 * Xa.T @ (Xa @ theta - ya) / len(Xa))
        theta -= LR * g
    return theta


def drift(a, b, Xc):
    pa, pb = Xc @ a, Xc @ b
    return float(np.mean(np.abs(pa - pb)) / (np.mean(np.abs(pb)) + 1e-9))


def run(strategy):
    theta = np.zeros(D)
    mem_x, mem_y = [], []
    history = []
    for X, y, Xc, yc in TASKS:
        if strategy == "naive":
            theta = train(theta, X, y)
        elif strategy == "random_replay":
            if mem_x:
                theta = train(theta, np.vstack([X] + mem_x),
                              np.concatenate([y] + mem_y))
            else:
                theta = train(theta, X, y)
        elif strategy == "cert_replay":
            if mem_x:
                AX, AY = np.vstack(mem_x), np.concatenate(mem_y)
                theta = train(theta, np.vstack([X, AX]),
                              np.concatenate([y, AY]), (AX, AY), 0.50)
            else:
                theta = train(theta, X, y)
        history.append(theta.copy())

        if strategy == "random_replay":
            pool = np.vstack([X] + mem_x) if mem_x else X
            pool_y = np.concatenate([y] + mem_y) if mem_y else y
            keep = RNG.choice(len(pool), size=min(BUFFER, len(pool)), replace=False)
            mem_x, mem_y = [pool[keep]], [pool_y[keep]]
        elif strategy == "cert_replay":
            k = BUFFER // 2
            ci = RNG.choice(len(Xc), size=min(k, len(Xc)), replace=False)
            ui = RNG.choice(len(X), size=min(BUFFER - k, len(X)), replace=False)
            nX = np.vstack([Xc[ci], X[ui]])
            ny = np.concatenate([yc[ci], y[ui]])
            if mem_x:
                pool = np.vstack([nX] + mem_x)
                pool_y = np.concatenate([ny] + mem_y)
                keep = RNG.choice(len(pool), size=BUFFER, replace=False)
                mem_x, mem_y = [pool[keep]], [pool_y[keep]]
            else:
                mem_x, mem_y = [nX], [ny]

    drift_c = np.mean([drift(theta, history[t], TASKS[t][2]) for t in range(T)])
    drift_a = np.mean([drift(theta, history[t], TASKS[t][0]) for t in range(T)])
    mse = np.mean([np.mean((TASKS[t][0] @ theta - TASKS[t][1]) ** 2)
                   for t in range(T)])
    return drift_c, drift_a, mse


def depth_probe():
    r = np.random.default_rng(7)
    reps, theta_d = 8000, 0.60
    f, b, sigma_d, sigma0 = 400.0, 0.05, 0.2, 0.01

    def sample(n):
        z = r.uniform(0.2, 3.0)
        sz = z ** 2 * sigma_d / (f * b)
        q = np.exp(-sz / sigma0) * r.uniform(0.9, 1.0, size=n)
        pf = r.uniform(0.0, 0.25)                # transparent/reflective failure rate
        fail = r.random(n) < pf
        q[fail] = r.uniform(0.0, 0.4, size=fail.sum())
        return q

    mean_fa = q10_fa = 0
    for _ in range(reps):
        obs = sample(120)
        hidden = sample(5)                       # support points the estimator misses
        truth = np.quantile(np.concatenate([obs, hidden]), 0.10)
        mean_fa += (obs.mean() >= theta_d) and (truth < theta_d)
        q10_fa += (np.quantile(obs, 0.10) >= theta_d) and (truth < theta_d)

    zs = np.linspace(0.2, 3.0, 500)
    q_theory = np.exp(-(zs ** 2 * sigma_d / (f * b)) / sigma0)
    max_range = zs[q_theory >= theta_d].max()
    return theta_d, mean_fa / reps, q10_fa / reps, max_range


if __name__ == "__main__":
    print("== continual-learning probe (12 tasks, d=20, C_i = top-20% leverage) ==")
    for s in ("naive", "random_replay", "cert_replay"):
        dc, da, mse = run(s)
        print(f"{s:14s} drift_crit={dc:.3f} drift_all={da:.3f} mse_old={mse:.4f}")
    th, mf, qf, mr = depth_probe()
    print("== depth-quality probe (stereo f=400px, b=0.05m, sigma_d=0.2px) ==")
    print(f"theta_d={th}  mean false-accept={mf:.3f}  q10 false-accept={qf:.3f}")
    print(f"theoretical certifiable range at theta_d: 0.2-{mr:.2f} m")
