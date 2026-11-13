#!/usr/bin/env python3
"""Round-6 probe: behavior-tree structure x anomaly detection for UniBot.

Two D-level checks (NOT robot evidence):

P1  Real official G1_Dex1 state traces (exp/unibot_states).  Leave-episode-out
    one-class anomaly detection with conformal thresholds.  Two feature views:
        state-only      (x)
        state+dynamics  (x, dx_1, dx_5)
    Synthetic disturbances injected into held-out episodes: reversal (undo),
    freeze (stuck), impulse (push).  Reports frame AUROC and detection delay
    at a T_a=8 block boundary.  The point: an undo revisits states that are on
    the demo manifold, so state-only anomaly detection is blind to it; the
    dynamics view is what makes "regressed" observable.

P2  Sampled-time behavior-tree toy.  fixed T_a, frontier/regression dynamics,
    noisy block-boundary observations.  Compares no-recovery / single-frame
    reactive (v3-style) / debounced+latched+retry-capped BT guard.  Reports
    step score, success, false resync rate and wasted ticks.

Outputs exp/r6_bt_anomaly_probe.json
"""
from __future__ import annotations
import glob, json, os
import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import rankdata

EXP = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(EXP, "unibot_states")
OUT = os.path.join(EXP, "r6_bt_anomaly_probe.json")

STATE_KEYS = [
    "observation.state.left_arm", "observation.state.right_arm",
    "observation.state.left_gripper", "observation.state.right_gripper",
    "observation.state.left_ee_pose_gripper_base",
    "observation.state.right_ee_pose_gripper_base",
    "observation.state.lower_body",
]
TA = 8  # block boundary (chunk length)


# --------------------------------------------------------------- real traces
def load_eps(path):
    d = np.load(path, allow_pickle=True)
    out = []
    for split in ("random", "contig"):
        if split not in d.files:
            continue
        e = d[split].item()
        idx = np.asarray(e["episode_index"]).astype(int)
        fi = np.asarray(e["frame_index"]).astype(int)
        for u in np.unique(idx):
            m = idx == u
            order = np.argsort(fi[m])
            if np.any(np.diff(fi[m][order]) <= 0):
                continue
            X = np.concatenate(
                [np.asarray(e[k], float)[m][order].reshape(m.sum(), -1)
                 for k in STATE_KEYS], axis=1)
            if len(X) >= 40:
                out.append(X)
    return out


def features(X, mode):
    x = X.astype(float)
    if mode == "state":
        return x
    d1 = np.diff(x, axis=0, prepend=x[:1])
    w = min(5, len(x) - 1)
    d5 = x - np.concatenate([np.repeat(x[:1], w, 0), x[:-w]], 0)
    return np.c_[x, d1, d5]


def auroc(scores, labels):
    labels = np.asarray(labels).astype(bool)
    if labels.all() or (~labels).all():
        return None
    r = rankdata(scores)
    n1, n0 = labels.sum(), (~labels).sum()
    return float((r[labels].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def inject(X, kind, rng):
    """Return (Xa, onset, end) with one synthetic disturbance window."""
    n = len(X)
    W = min(20, max(8, n // 5))
    s = int(rng.integers(8, max(9, n - W - 2)))
    e = min(n, s + W)
    Xa = X.copy()
    if kind == "reversal":
        Xa[s:e] = X[s:e][::-1]
    elif kind == "freeze":
        Xa[s:e] = X[s]
    elif kind == "impulse":
        arm = slice(0, 14)
        sd = X.std(0) + 1e-6
        Xa[s:, arm] += 0.5 * sd[arm]
    else:
        raise ValueError(kind)
    return Xa, s, e


def conformal_thr(calib, alpha=0.05):
    c = np.sort(np.asarray(calib))
    n = len(c)
    k = int(np.ceil((n + 1) * (1 - alpha))) - 1
    return float(c[min(max(k, 0), n - 1)])


def knn_scores(train, query, k=5):
    tree = cKDTree(train)
    d, _ = tree.query(query, k=min(k, len(train)))
    return d.mean(1)


def p1_real():
    rows = []
    for p in sorted(glob.glob(os.path.join(STATE, "*.npz"))):
        eps = load_eps(p)
        if len(eps) < 6:
            continue
        name = os.path.basename(p)[:-4]
        rng = np.random.default_rng(7)
        order = rng.permutation(len(eps))
        n = len(order)
        n_tr = max(4, int(0.6 * n))
        n_ca = max(2, int(0.2 * n))
        tr = [eps[i] for i in order[:n_tr]]
        ca = [eps[i] for i in order[n_tr:n_tr + n_ca]]
        te = [eps[i] for i in order[n_tr + n_ca:]]
        if not te:
            te = [eps[order[-1]]]
        for mode in ("state", "dyn"):
            Ftr = np.concatenate([features(x, mode) for x in tr], 0)
            mu, sd = Ftr.mean(0), Ftr.std(0)
            sd[sd < 1e-8] = 1.0
            T = (Ftr - mu) / sd
            C = np.concatenate([features(x, mode) for x in ca], 0)
            C = (C - mu) / sd
            c_score = knn_scores(T, C, k=5)
            thr = conformal_thr(c_score, alpha=0.05)
            for kind in ("reversal", "freeze", "impulse"):
                sc, lab, delays, block_delays = [], [], [], []
                for X in te:
                    Xa, s, e = inject(X, kind, rng)
                    Q = (features(Xa, mode) - mu) / sd
                    sc_i = knn_scores(T, Q, k=5)
                    y = np.zeros(len(Q), bool)
                    y[s:e] = True
                    sc.append(sc_i)
                    lab.append(y)
                    # persistence-2 detector at block boundaries
                    flag = sc_i > thr
                    run = 0
                    hit = None
                    for t in range(s, min(len(Q), e + TA)):
                        run = run + 1 if flag[t] else 0
                        if run >= 2:
                            hit = t - s
                            break
                    if hit is None:
                        # allow a one-block-late boundary hit
                        for t in range(e, min(len(Q), e + 4 * TA)):
                            if flag[t]:
                                hit = t - s
                                break
                    delays.append(hit if hit is not None else np.nan)
                    block_delays.append(np.nan if hit is None else int(np.ceil(hit / TA)))
                sc = np.concatenate(sc)
                lab = np.concatenate(lab)
                hit = np.array(delays, float)
                rows.append({
                    "task": name, "mode": mode, "kind": kind,
                    "auroc": round(float(auroc(sc, lab)), 4) if auroc(sc, lab) is not None else None,
                    "thr_95": round(thr, 4),
                    "det_rate": round(float(np.mean(~np.isnan(hit))), 3),
                    "delay_frames_median": None if np.all(np.isnan(hit)) else round(float(np.nanmedian(hit)), 1),
                    "delay_blocks_median": None if np.all(np.isnan(hit)) else round(float(np.nanmedian(np.array(block_delays, float))), 2),
                })
    # macro summary
    summ = {}
    for mode in ("state", "dyn"):
        for kind in ("reversal", "freeze", "impulse"):
            v = [r for r in rows if r["mode"] == mode and r["kind"] == kind]
            vals = [x["auroc"] for x in v if x["auroc"] is not None]
            det = [x["det_rate"] for x in v]
            dly = [x["delay_blocks_median"] for x in v if x["delay_blocks_median"] is not None]
            summ[f"{mode}/{kind}"] = {
                "n_tasks": len(v),
                "auroc_mean": round(float(np.mean(vals)), 4) if vals else None,
                "det_rate_mean": round(float(np.mean(det)), 3),
                "delay_blocks_median_of_tasks": round(float(np.median(dly)), 2) if dly else None,
            }
    return {"per_task": rows, "macro": summ,
            "note": "D-level: proprio-only, random-split episodes, synthetic disturbances; not robot evidence"}


# ------------------------------------------------------- behavior-tree toy
def bt_sim(sigma=0.6, lam=0.15, mode="bt", M=5, T=60, episodes=400,
           q=0.85, fumble=0.08, alpha=0.10, rng=None):
    """Frontier/regression toy.

    p        true completed milestones
    F        believed frontier (highest completed)
    advance  works only if p == F, then p->p+1 w.p. q and F=p
    disturb  p -> max(0,p-1) w.p. lam per tick (F unchanged)
    resync   F <- observed level, costs 1 tick; false resync at p==F loses
             progress w.p. fumble (over-manipulation)
    """
    if rng is None:
        rng = np.random.default_rng(0)
    # calibrate the negative-innovation threshold on disturbance-free runs
    norm = []
    for _ in range(300):
        p = 0
        ys = []
        for t in range(T):
            if p < M and rng.random() < q:
                p += 1
            ys.append(p + rng.normal(0, sigma))
        ys = np.asarray(ys)
        norm.append(np.diff(ys))
    norm = np.concatenate(norm)
    thr = float(np.quantile(norm, alpha))  # lower-tail FPR alpha
    success = []
    score = []
    false_resync = []
    resyncs = []
    wasted = []
    for _ in range(episodes):
        p, F = 0, 0
        prev_y = p + rng.normal(0, sigma)
        run = 0
        recovering = False
        redo_left = 0 if mode == "bt" else 10 ** 9
        n_false = 0
        n_res = 0
        w = 0
        for t in range(T):
            if rng.random() < lam:
                p = max(0, p - 1)
            if recovering:
                # recovery postcondition: observed level back at/above F
                if prev_y >= F - 0.5 or redo_left <= 0:
                    recovering = False
                    redo_left = 0 if mode == "bt" else 10 ** 9
                else:
                    # try to restore via resync/redo
                    if mode == "openloop":
                        pass
                    else:
                        n_res += 1
                        if F == p:
                            n_false += 1
                            if rng.random() < fumble:
                                p = max(0, p - 1)
                        F = p
                        redo_left -= 1
                        w += 1
                        prev_y = p + rng.normal(0, sigma)
                        continue
            # normal control: advance if frontier matches true progress
            if p == F:
                if rng.random() < q:
                    p += 1
                    F = p
                else:
                    w += 1  # slip, still spends the tick
            else:
                # wrong precondition: stall until regression is detected
                w += 1
                if mode == "openloop":
                    pass
            y = p + rng.normal(0, sigma)
            dy = y - prev_y
            flag = dy < thr
            run = run + 1 if flag else 0
            if mode == "flat":
                trig = flag
            elif mode == "bt":
                trig = (run >= 2) and not recovering
            else:
                trig = False
            if trig and p < F:
                recovering = True
                redo_left = 2 if mode == "bt" else 10 ** 9
                if mode == "flat":
                    n_res += 1
                    if F == p:
                        n_false += 1
                        if rng.random() < fumble:
                            p = max(0, p - 1)
                    F = p
                    w += 1
            prev_y = y
        success.append(float(p >= M))
        score.append(p / M)
        false_resync.append(n_false / max(n_res, 1))
        resyncs.append(n_res)
        wasted.append(w / T)
    return {
        "sigma": sigma, "lam": lam, "mode": mode, "thr_alpha": alpha,
        "thr": round(thr, 3),
        "success": round(float(np.mean(success)), 3),
        "step_score": round(float(np.mean(score)), 3),
        "step_score_p25": round(float(np.percentile(score, 25)), 3),
        "false_resync_rate": round(float(np.mean(false_resync)), 3),
        "resyncs_mean": round(float(np.mean(resyncs)), 2),
        "wasted_tick_frac": round(float(np.mean(wasted)), 3),
    }


def p2_bt():
    rows = []
    for sigma in (0.3, 0.6, 1.0):
        for lam in (0.05, 0.15, 0.30):
            for mode in ("openloop", "flat", "bt"):
                rows.append(bt_sim(sigma=sigma, lam=lam, mode=mode,
                                   rng=np.random.default_rng(int(1000 * sigma + 100 * lam))))
    return {"rows": rows,
            "note": "synthetic sampled-time toy; fixed T_a=8; no robot evidence"}


def main():
    out = {
        "note": "Round-6 D-level probes: behavior tree x anomaly detection",
        "p1_real_anomaly": p1_real(),
        "p2_bt_toy": p2_bt(),
    }
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out["p1_real_anomaly"]["macro"], ensure_ascii=False, indent=1))
    print(json.dumps(out["p2_bt_toy"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
