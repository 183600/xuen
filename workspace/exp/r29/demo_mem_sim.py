"""Round 29 / Experiment A - relational demo memory as a few-shot prior.

Question: can the *released* UniBot-V1 demonstrations (32k episodes, 169 h)
serve as an on-device "few-shot memory" that transfers behaviour to a task the
policy has never seen, without any extra training?

What is measured (real data only, no learned policy involved):
  A1  transport-duration MAE on a held-out task, versus (a) the memory mean
      and (b) a ridge regression on state-only features.  Sweep the number of
      demos kept per memory task (1 / 3 / 10 / all) -> few-shot curve.
  A2  transport-path shape RMSE (phase-aligned, approach-frame normalised):
      relational retrieval  vs  random retrieval  vs  absolute-key retrieval,
      with and without a simulated scene translation (the "position change"
      generalisation axis).
  A3  lift height (does the robot raise the object before transporting?).

All numbers are proxy metrics on demonstrations.  They are *not* robot success
rates; they only tell us whether a relational demo memory carries transferable
structure that a single flat fine-tune would average away.
"""

import json
import os
import random
import sys

import numpy as np

sys.path[:0] = [os.path.dirname(os.path.abspath(__file__))]
from dataio import GRIP_CLOSED, available_tasks, load_task

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "demo_mem_results.json")


def events(grip):
    """Return (close_idx, open_idx) events of a Dex1 opening signal."""
    closed = [g <= GRIP_CLOSED for g in grip]
    close_i, open_i = [], []
    for i in range(1, len(closed)):
        if closed[i] and not closed[i - 1]:
            close_i.append(i)
        elif not closed[i] and closed[i - 1]:
            open_i.append(i)
    return close_i, open_i


def pick_arm(ep):
    """Active arm: earliest arm with a close event followed by an open event."""
    best = None
    for arm in ("L", "R"):
        grip = [f[arm + "_grip"] for f in ep]
        c, o = events(grip)
        if not c:
            continue
        first_close = c[0]
        later_open = [x for x in o if x > first_close]
        if not later_open:
            continue
        motion = float(np.sum(np.abs(np.diff(np.array([f["a_" + arm] for f in ep]), axis=0)))) + 1e-9
        key = (first_close, -motion)
        if best is None or key < best[0]:
            best = (key, arm, first_close, later_open[0])
    if best is None:
        return None
    return best[1], best[2], best[3]


def episode_features(ep):
    """Task-agnostic relational description of one demonstration episode."""
    if len(ep) < 30:
        return None
    arm, grasp_i, release_i = pick_arm(ep)
    pos = np.array([f[arm + "_ee"][:3] for f in ep], dtype=float)
    grip = np.array([f[arm + "_grip"] for f in ep], dtype=float)
    other_grip = np.array([f[("R" if arm == "L" else "L") + "_grip"] for f in ep], dtype=float)
    p0, pg = pos[0], pos[grasp_i]
    approach = pg - p0
    d_app = float(np.linalg.norm(approach))
    if d_app < 1e-4:
        return None
    u_app = approach / d_app
    path = pos[grasp_i : release_i + 1]
    if len(path) < 5:
        return None
    seg = path[1:] - path[:-1]
    plen = float(np.sum(np.linalg.norm(seg, axis=1)))
    disp = path[-1] - path[0]
    d_tr = float(np.linalg.norm(disp))
    if d_tr < 1e-4:
        return None
    u_tr = disp / d_tr
    lift = float(np.max(path[:, 2]) - path[0, 2])
    dur = release_i - grasp_i
    # approach-phase descriptors (available *before* the answer is known)
    pre = pos[: grasp_i + 1]
    pre_path = float(np.sum(np.linalg.norm(np.diff(pre, axis=0), axis=1)))
    duty = float(np.mean(grip[: grasp_i + 1] <= GRIP_CLOSED))
    other_duty = float(np.mean(other_grip[: grasp_i + 1] <= GRIP_CLOSED))
    approach_frames = grasp_i
    # shape of the transport path, resampled to 20 arc-length points
    seglen = np.linalg.norm(seg, axis=1)
    s = np.concatenate([[0.0], np.cumsum(seglen)])
    if s[-1] < 1e-6:
        return None
    u = s / s[-1]
    grid = np.linspace(0.0, 1.0, 20)
    shape = np.stack([np.interp(grid, u, path[:, k]) for k in range(3)], axis=1)
    shape -= shape[0]
    return {
        "arm": arm,
        "grasp_i": grasp_i,
        "release_i": release_i,
        "p0": p0,
        "pg": pg,
        "u_app": u_app,
        "d_app": d_app,
        "u_tr": u_tr,
        "d_tr": d_tr,
        "lift": lift,
        "dur": dur,
        "plen": plen,
        "pre_path": pre_path,
        "duty": duty,
        "other_duty": other_duty,
        "approach_frames": approach_frames,
        "shape": shape,
        "rel_key": np.array([d_app, *u_app, duty, other_duty, pre_path / max(d_app, 1e-6), approach_frames / 30.0]),
        "abs_key": np.array([*pg, *p0]),
    }


def align_rotation(u_from, u_to):
    """Minimal rotation R with R @ u_from = u_to (both unit vectors)."""
    a = u_from / (np.linalg.norm(u_from) + 1e-9)
    b = u_to / (np.linalg.norm(u_to) + 1e-9)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-8:
        return np.eye(3) if c > 0 else -np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def shape_rmse(shape_a, shape_b):
    """RMSE between two arc-length-resampled transport shapes after rotation
    into the same approach frame and normalisation by path length."""
    la = np.linalg.norm(shape_a[-1] - shape_a[0]) + 1e-9
    lb = np.linalg.norm(shape_b[-1] - shape_b[0]) + 1e-9
    return float(np.sqrt(np.mean(np.sum(((shape_a / la) - (shape_b / lb)) ** 2, axis=1))))


def collect():
    feats = {}
    for task in sorted(available_tasks()):
        eps = load_task(task)
        keep = []
        for ep in eps:
            f = episode_features(ep)
            if f is not None:
                keep.append(f)
        if keep:
            feats[task] = keep
    return feats


def build_memory(feats, held_out, per_task, rng):
    mem = []
    for task, items in feats.items():
        if task == held_out:
            continue
        take = items if per_task is None else items[:per_task]
        mem.extend(take)
    return mem


def knn(query_key, memory, k, key="rel_key"):
    keys = np.stack([m[key] for m in memory])
    d = np.linalg.norm(keys - query_key, axis=1)
    idx = np.argsort(d)[:k]
    return idx, d[idx]


def predict_duration(query, memory, k, mode="rel"):
    if mode == "rel":
        idx, dist = knn(query["rel_key"], memory, k)
    else:
        idx, dist = knn(query["abs_key"], memory, k, key="abs_key")
    w = 1.0 / (dist + 1e-3)
    w = w / w.sum()
    return float(np.sum([w[i] * memory[j]["dur"] for i, j in enumerate(idx)]))


def ridge_fit(memory):
    X = np.stack([m["rel_key"] for m in memory])
    y = np.array([m["dur"] for m in memory], dtype=float)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Xs = (X - mu) / sd
    Xs = np.concatenate([Xs, np.ones((len(Xs), 1))], axis=1)
    w, *_ = np.linalg.lstsq(Xs, y, rcond=None)
    return (mu, sd, w)


def ridge_pred(query, model):
    mu, sd, w = model
    x = (query["rel_key"] - mu) / sd
    x = np.concatenate([x, [1.0]])
    return float(x @ w)


def main():
    rng = random.Random(29)
    feats = collect()
    tasks = sorted(feats)
    print("tasks with usable episodes:", {t: len(v) for t, v in feats.items()})
    out = {"tasks": {t: len(v) for t, v in feats.items()}, "A1": {}, "A2": {}, "A3": {}}

    # ---- A1: transport-duration prediction on a held-out task -------------- #
    for per_task in (1, 3, 10, None):
        rows = []
        for held in tasks:
            mem = build_memory(feats, held, per_task, rng)
            if len(mem) < 10:
                continue
            mem_dur_mean = float(np.mean([m["dur"] for m in mem]))
            model = ridge_fit(mem)
            rel_err, base_err, ridge_err, cos_rel = [], [], [], []
            for q in feats[held]:
                p = predict_duration(q, mem, 5, mode="rel")
                rel_err.append(abs(p - q["dur"]))
                base_err.append(abs(mem_dur_mean - q["dur"]))
                ridge_err.append(abs(ridge_pred(q, model) - q["dur"]))
                # direction transfer: neighbours' transport direction rotated
                # into the query's approach frame
                idx, _ = knn(q["rel_key"], mem, 5)
                preds = []
                for j in idx:
                    R = align_rotation(mem[j]["u_app"], q["u_app"])
                    preds.append(R @ mem[j]["u_tr"])
                vec = np.mean(preds, axis=0)
                nv = np.linalg.norm(vec)
                cos_rel.append(float(vec @ q["u_tr"] / nv) if nv > 1e-9 else 0.0)
            rows.append(
                {
                    "held": held,
                    "n_query": len(rel_err),
                    "mem_dur_mean": mem_dur_mean,
                    "mae_rel": float(np.mean(rel_err)),
                    "mae_const": float(np.mean(base_err)),
                    "mae_ridge": float(np.mean(ridge_err)),
                    "cos_rel": float(np.mean(cos_rel)),
                }
            )
        key = "all" if per_task is None else str(per_task)
        out["A1"][key] = {
            "per_task": rows,
            "mae_rel_mean": float(np.mean([r["mae_rel"] for r in rows])),
            "mae_const_mean": float(np.mean([r["mae_const"] for r in rows])),
            "mae_ridge_mean": float(np.mean([r["mae_ridge"] for r in rows])),
            "cos_rel_mean": float(np.mean([r["cos_rel"] for r in rows])),
        }
        print(
            f"[A1] mem/task={key:>4}  MAE rel={out['A1'][key]['mae_rel_mean']:.1f}  "
            f"const={out['A1'][key]['mae_const_mean']:.1f}  ridge={out['A1'][key]['mae_ridge_mean']:.1f}  "
            f"cos={out['A1'][key]['cos_rel_mean']:.3f}"
        )

    # ---- A2: transport-shape transfer, relational vs random vs absolute ---- #
    rows = []
    for held in tasks:
        mem = build_memory(feats, held, None, rng)
        if len(mem) < 10:
            continue
        for perturb in (False, True):
            rel_rmse, rand_rmse, abs_rmse = [], [], []
            for q in feats[held]:
                d_app = q["d_app"]
                for trial in range(3):
                    if perturb:
                        delta = np.array([rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(-0.05, 0.05)])
                    else:
                        delta = np.zeros(3)
                    qq = dict(q)
                    qq["rel_key"] = q["rel_key"].copy()
                    qq["abs_key"] = q["abs_key"] + np.concatenate([delta, delta])
                    # relational retrieval is invariant to the scene translation
                    idx, _ = knn(qq["rel_key"], mem, 5)
                    errs_rel = []
                    for j in idx:
                        R = align_rotation(mem[j]["u_app"], q["u_app"])
                        errs_rel.append(shape_rmse(R @ (mem[j]["shape"].T).T, q["shape"]))
                    rel_rmse.append(float(np.mean(errs_rel)))
                    # random retrieval
                    rnd = rng.sample(range(len(mem)), 5)
                    errs_rand = []
                    for j in rnd:
                        R = align_rotation(mem[j]["u_app"], q["u_app"])
                        errs_rand.append(shape_rmse(R @ (mem[j]["shape"].T).T, q["shape"]))
                    rand_rmse.append(float(np.mean(errs_rand)))
                    # absolute-key retrieval
                    idx_a, _ = knn(qq["abs_key"], mem, 5, key="abs_key")
                    errs_abs = []
                    for j in idx_a:
                        R = align_rotation(mem[j]["u_app"], q["u_app"])
                        errs_abs.append(shape_rmse(R @ (mem[j]["shape"].T).T, q["shape"]))
                    abs_rmse.append(float(np.mean(errs_abs)))
            rows.append(
                {
                    "held": held,
                    "perturbed": perturb,
                    "rmse_rel": float(np.mean(rel_rmse)),
                    "rmse_rand": float(np.mean(rand_rmse)),
                    "rmse_abs": float(np.mean(abs_rmse)),
                }
            )
    for perturb in (False, True):
        sel = [r for r in rows if r["perturbed"] == perturb]
        out["A2"]["perturbed" if perturb else "clean"] = {
            "rmse_rel": float(np.mean([r["rmse_rel"] for r in sel])),
            "rmse_rand": float(np.mean([r["rmse_rand"] for r in sel])),
            "rmse_abs": float(np.mean([r["rmse_abs"] for r in sel])),
            "per_task": sel,
        }
        print(
            f"[A2] {'perturbed' if perturb else 'clean   '}  shape RMSE  rel={out['A2']['perturbed' if perturb else 'clean']['rmse_rel']:.4f}"
            f"  rand={out['A2']['perturbed' if perturb else 'clean']['rmse_rand']:.4f}"
            f"  abs-key={out['A2']['perturbed' if perturb else 'clean']['rmse_abs']:.4f}"
        )

    # ---- A3: lift-height transfer ----------------------------------------- #
    rows = []
    for held in tasks:
        mem = build_memory(feats, held, None, rng)
        if len(mem) < 10:
            continue
        const = float(np.mean([m["lift"] for m in mem]))
        rel_err, const_err = [], []
        for q in feats[held]:
            idx, dist = knn(q["rel_key"], mem, 5)
            w = 1.0 / (dist + 1e-3)
            w /= w.sum()
            pred = float(sum(w[i] * mem[j]["lift"] for i, j in enumerate(idx)))
            rel_err.append(abs(pred - q["lift"]))
            const_err.append(abs(const - q["lift"]))
        rows.append({"held": held, "mae_rel": float(np.mean(rel_err)), "mae_const": float(np.mean(const_err))})
    out["A3"] = {
        "mae_rel_mean": float(np.mean([r["mae_rel"] for r in rows])),
        "mae_const_mean": float(np.mean([r["mae_const"] for r in rows])),
        "per_task": rows,
    }
    print(f"[A3] lift MAE  rel={out['A3']['mae_rel_mean']:.4f}  const={out['A3']['mae_const_mean']:.4f}")

    with open(OUT, "w") as handle:
        json.dump(out, handle, indent=1)
    print("written", OUT)


if __name__ == "__main__":
    main()
