#!/usr/bin/env python3
"""D-level mechanism checks for 多视角视觉 x 虚实迁移 (UniBot).

Two synthetic probes, explicitly NOT robot evidence:

P1  Multi-view vs single-view regression detection.
    A 3D object moves along a known progress path; two calibrated cameras
    observe it.  Contact phases occlude each view independently and one view
    is nearly degenerate along the motion (depth ambiguity).  A true human
    reversal moves the object backwards; no-reversal episodes contain
    occlusion and camera noise only.  We compare running-max drop detectors
    using (a) head view, (b) wrist view, (c) best available single view,
    (d) two-view triangulation.

P2  Sim-to-real score calibration as a ranking problem.
    True task scores y_t are observed for a few anchor tasks; the simulator
    reports s_t = alpha_t*y_t + beta_t + noise with task/group-dependent
    bias.  We compare raw sim ranking, global affine calibration, group
    affine calibration, and hierarchical (group + shrunk task residual)
    calibration by held-out Spearman rho.  This is the statistical core of
    "anchor-calibrated oracle", not a leaderboard result.

Outputs exp/mvst_results.json
"""
from __future__ import annotations
import json
import os

import numpy as np

EXP = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(EXP, "mvst_results.json")
rng = np.random.default_rng(20261113)


# ---------------------------------------------------------------- P1 multiview
def project(p, cam):
    """Pinhole projection of world points p (...,3) into one camera."""
    R, t, f, c = cam["R"], cam["t"], cam["f"], cam["c"]
    q = (p - t) @ R.T
    u = f * q[..., 0] / np.maximum(q[..., 2], 1e-6) + c[0]
    v = f * q[..., 1] / np.maximum(q[..., 2], 1e-6) + c[1]
    return np.stack([u, v], -1)


def triangulate(obs, cams):
    """Linear triangulation from >=2 views for a single point."""
    A = []
    for (u, v), cam in zip(obs, cams):
        R, t, f, c = cam["R"], cam["t"], cam["f"], cam["c"]
        # ray direction in world: R^T @ [(u-cx)/f, (v-cy)/f, 1]
        d = R.T @ np.array([(u - c[0]) / f, (v - c[1]) / f, 1.0])
        d = d / np.linalg.norm(d)
        # closest point to line: (I - dd^T) p = (I - dd^T) C
        A.append(np.eye(3) - np.outer(d, d))
    A = np.concatenate(A, 0)
    b = []
    for (u, v), cam in zip(obs, cams):
        R, t, f, c = cam["R"], cam["t"], cam["f"], cam["c"]
        d = R.T @ np.array([(u - c[0]) / f, (v - c[1]) / f, 1.0])
        d = d / np.linalg.norm(d)
        b.append((np.eye(3) - np.outer(d, d)) @ t)
    b = np.concatenate(b, 0)
    return np.linalg.lstsq(A, b, rcond=None)[0]


def q_from_point(p, p0, direction):
    return float(np.dot(p - p0, direction) / np.dot(direction, direction))


def make_cams():
    # Camera 0: head, wide baseline but 3D motion has a large depth component.
    # Camera 1: wrist, close-up, more accurate laterally but easily occluded.
    cams = []
    # Camera 0 looks almost exactly along DIR: monocular depth (and thus
    # progress) is ill-conditioned.  Camera 1 sees the motion laterally.
    for C, f, c in [((0.0, -1.0, 0.0), 520.0, (320.0, 240.0)),
                    ((0.7, 0.1, 0.5), 900.0, (320.0, 240.0))]:
        C = np.array(C, float)
        z = -C / np.linalg.norm(C)
        x = np.cross(np.array([0.0, 0.0, 1.0]), z)
        x = x / np.linalg.norm(x)
        y = np.cross(z, x)
        R = np.stack([x, y, z], 1)
        cams.append({"R": R, "t": C, "f": f, "c": np.array(c, float)})
    return cams


CAMS = make_cams()
SENS_THR = 20.0  # pixels per unit progress; below this a view is degenerate
P0 = np.array([0.0, 0.0, 0.0])
DIR = np.array([0.0, 1.0, 0.0])


def episode(seed, has_reversal, n=220):
    r = np.random.default_rng(seed)
    q = np.zeros(n)
    for t in range(1, n):
        q[t] = min(1.0, q[t - 1] + 0.0045 + r.normal(0, 0.0008))
    if has_reversal:
        e = int(r.integers(90, 170))
        depth = r.uniform(0.15, 0.30)
        q[e:] -= depth
        q[e:] = np.maximum(q[e:], 0.0)
        # a second, smaller reversal sometimes
        if r.random() < 0.35:
            e2 = min(n - 10, e + int(r.integers(25, 55)))
            q[e2:] -= r.uniform(0.08, 0.16)
            q[e2:] = np.maximum(q[e2:], 0.0)
    p = P0 + q[:, None] * DIR[None, :]
    # Occlusion: wrist is often blocked in contact-rich phases; head less so.
    contact = (q > 0.35) & (q < 0.85)
    occ = np.stack([
        r.random(n) < np.where(contact, 0.18, 0.05),
        r.random(n) < np.where(contact, 0.55, 0.12),
    ], 1)
    obs = np.full((n, 2, 2), np.nan)
    for v, cam in enumerate(CAMS):
        uv = project(p, cam) + r.normal(0, 1.8, (n, 2))
        obs[:, v] = np.where(occ[:, v, None], np.nan, uv)
    return q, obs


def estimate_q(obs_t, prev, dtype):
    """Estimate progress from one time slice; prev = last estimate."""
    if dtype == "head":
        return _single_q(obs_t[0], CAMS[0], prev)
    if dtype == "wrist":
        return _single_q(obs_t[1], CAMS[1], prev)
    if dtype == "best_single":
        # strong baseline: use whichever view is visible; prefer wrist (lower
        # pixel noise) when both are available.
        if not np.isnan(obs_t[1]).any():
            return _single_q(obs_t[1], CAMS[1], prev)
        if not np.isnan(obs_t[0]).any():
            return _single_q(obs_t[0], CAMS[0], prev)
        return prev
    if dtype in ("multi", "multi_all"):
        vis = [v for v in range(2) if not np.isnan(obs_t[v]).any()]
        if len(vis) == 0:
            return prev
        if dtype == "multi":
            # Observability gate: a view is usable only if q actually moves
            # its pixels.  A head camera looking down the motion ray has
            # near-zero sensitivity; trusting it manufactures false alarms.
            usable = []
            for v in vis:
                dq = 0.01
                p_lo = P0 + max(0.0, prev - dq) * DIR
                p_hi = P0 + min(1.05, prev + dq) * DIR
                sens = np.linalg.norm(project(p_hi[None], CAMS[v])[0] -
                                      project(p_lo[None], CAMS[v])[0]) / \
                    max(1e-9, (min(1.05, prev + dq) - max(0.0, prev - dq)))
                if sens > SENS_THR:
                    usable.append(v)
            if not usable:
                return prev
            vis = usable
        # Fuse in task space: one shared q must explain every usable view.
        # This is better conditioned than triangulating first.
        grid = np.linspace(0.0, 1.05, 421)
        pts = P0 + grid[:, None] * DIR[None, :]
        cost = np.zeros(len(grid))
        for v in vis:
            uv_hat = project(pts, CAMS[v])
            cost += ((uv_hat - obs_t[v]) ** 2).sum(1)
        return float(grid[np.argmin(cost)])
    raise ValueError(dtype)


def _single_q(uv, cam, prev):
    if np.isnan(uv).any():
        return prev
    # search q on a grid; cheap and stable for this toy
    grid = np.linspace(0.0, 1.05, 421)
    pts = P0 + grid[:, None] * DIR[None, :]
    uv_hat = project(pts, cam)
    return float(grid[np.argmin(((uv_hat - uv) ** 2).sum(1))])


def run_detector(dtype, episodes, thr=0.10, horizon=6):
    """Running-max drop detector at each frame, with a short debounce."""
    all_scores, all_labels, delays, false_alarms = [], [], [], 0
    for q, obs, has_rev, rev_t in episodes:
        est = np.zeros(len(q))
        last = 0.0
        for t in range(len(q)):
            last = estimate_q(obs[t], last, dtype)
            est[t] = last
        runmax = np.maximum.accumulate(est)
        drop = runmax - est
        # debounce: require drop over threshold for 2 consecutive frames
        alarm = np.zeros(len(est), bool)
        for t in range(len(est)):
            if drop[t] > thr:
                if t + 1 < len(est) and drop[t + 1] > thr:
                    alarm[t] = True
        if has_rev:
            first = np.where(alarm[rev_t:])[0]
            delays.append(int(first[0]) if len(first) else horizon + 1)
        else:
            false_alarms += int(alarm.any())
        # frame-level score for AUC: use drop as continuous evidence
        all_scores.append(drop)
        all_labels.append(np.zeros(len(drop), bool) if not has_rev else
                          (np.arange(len(drop)) >= rev_t))
    scores = np.concatenate(all_scores)
    labels = np.concatenate(all_labels)
    # rank AUC
    order = np.argsort(scores)
    ranks = np.empty(len(scores), float)
    ranks[order] = np.arange(1, len(scores) + 1)
    npos, nneg = labels.sum(), (~labels).sum()
    auc = float((ranks[labels].sum() - npos * (npos + 1) / 2) /
                max(npos * nneg, 1))
    return {
        "auc": round(auc, 4),
        "mean_delay": round(float(np.mean(delays)), 2),
        "detected_frac": round(float(np.mean(np.array(delays) <= horizon)), 3),
        "false_alarm_episodes": false_alarms,
        "n_episodes": len(episodes),
    }


def p1():
    episodes = []
    for i in range(160):
        has = i % 2 == 1
        q, obs = episode(1000 + i, has)
        rev_t = int(np.argmax(np.diff(q) < -0.02)) + 1 if has else -1
        episodes.append((q, obs, has, rev_t))
    return {k: run_detector(k, episodes)
            for k in ("head", "wrist", "best_single", "multi_all", "multi")}


# ------------------------------------------------------------ P2 calibration
def rankdata(x):
    order = np.argsort(x)
    ranks = np.empty(len(x), float)
    ranks[order] = np.arange(len(x), dtype=float)
    # average ties
    for val in np.unique(x):
        m = x == val
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    return ranks


def spearman(a, b):
    ra, rb = rankdata(a) - (len(a) + 1) / 2, rankdata(b) - (len(b) + 1) / 2
    return float((ra * rb).sum() /
                 np.sqrt((ra ** 2).sum() * (rb ** 2).sum()))


def fit_affine(s, y):
    A = np.c_[s, np.ones(len(s))]
    w = np.linalg.lstsq(A, y, rcond=None)[0]
    return lambda z: np.atleast_1d(np.asarray(z, float)) * w[0] + w[1]


def calibrate(mode, s_a, y_a, g_a, s_q, g_q):
    """Fit a score->score map on anchor tasks, predict query tasks."""
    if mode == "raw":
        return np.asarray(s_q, float).copy()
    glob = fit_affine(s_a, y_a)
    pred = glob(s_q)
    if mode == "global":
        return pred
    pred_group = pred.copy()
    for grp in np.unique(g_q):
        ia, iq = g_a == grp, g_q == grp
        if ia.sum() >= 2:
            pred_group[iq] = fit_affine(s_a[ia], y_a[ia])(s_q[iq])
    if mode == "group":
        return pred_group
    if mode == "hier":
        return 0.65 * pred_group + 0.35 * pred
    raise ValueError(mode)


def p2(n_anchor=10, n_rep=300, gap=1.0, G=8):
    T = 32
    modes = ("raw", "global", "group", "hier")
    group = np.repeat(np.arange(G), T // G)
    res = {k: [] for k in modes + ("gated", "oracle")}
    for rep in range(n_rep):
        r = np.random.default_rng(7000 + rep)
        y = np.clip(r.normal(52, 18, T), 0, 100)
        g_alpha = r.normal(0, 0.08, G)
        g_beta = r.normal(0, 9.0, G)
        alpha = 1.0 + gap * (g_alpha[group] + r.normal(0, 0.04, T))
        beta = gap * (g_beta[group] + r.normal(0, 3.0, T))
        s = alpha * y + beta + r.normal(0, 4.5 * max(gap, 0.3), T)
        anchors = r.choice(T, n_anchor, replace=False)
        hold = np.setdiff1d(np.arange(T), anchors)
        ga, gh = group[anchors], group[hold]

        for mode in modes:
            res[mode].append(spearman(
                calibrate(mode, s[anchors], y[anchors], ga, s[hold], gh),
                y[hold]))

        # Gated calibrator: leave-one-anchor-out MSE picks a mode.  With a
        # small gap raw sim wins; with a large gap a calibrated mode wins.
        cv = {}
        for mode in modes:
            err = []
            for i in range(len(anchors)):
                a = np.delete(np.arange(len(anchors)), i)
                p = calibrate(mode, s[anchors][a], y[anchors][a], ga[a],
                              s[anchors][i:i + 1], ga[i:i + 1])
                err.append((p[0] - y[anchors][i]) ** 2)
            cv[mode] = float(np.mean(err))
        best = min(cv, key=cv.get)
        res["gated"].append(spearman(
            calibrate(best, s[anchors], y[anchors], ga, s[hold], gh), y[hold]))
        # Oracle mode: the best of the four on the held-out set.
        res["oracle"].append(max(
            spearman(calibrate(m, s[anchors], y[anchors], ga, s[hold], gh),
                     y[hold]) for m in modes))
    return {k: round(float(np.mean(v)), 4) for k, v in res.items()}


def main():
    out = {
        "note": ("D-level synthetic mechanism checks only; no images, no robot, "
                 "no leaderboard evidence."),
        "P1_multiview_regression": p1(),
        "P2_sim2real_ranking_calibration": {
            "gap_low": p2(10, 300, gap=0.25),
            "gap_medium": p2(10, 300, gap=1.0),
            "gap_high": p2(10, 300, gap=2.0),
            "n_anchor_6_gap_medium": p2(6, 300, gap=1.0),
            "n_anchor_16_gap_medium": p2(16, 300, gap=1.0),
            "n_anchor_16_gap_high_G4": p2(16, 300, gap=2.0, G=4),
        },
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
