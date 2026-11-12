"""Round-61 synthetic mechanism check: FTCG (Fleet-Task Co-Grounded loop).

NOT benchmark evidence.  Four isolated mechanism questions against the
UniBot-V1 generalist setting (32 tasks, 5 generalisation axes, one checkpoint,
several G1 ports).  Declared generative models; magnitudes are illustrative.

S1 TSF  task-skill-generalisation additive factorisation vs global / per-task /
        per-cell impedance priors under few-shot cells.
S2 FAM  fleet affinity weighting vs naive pooling when robots have different
        camera / table-height calibration.
S3 CPR  robust cross-robot prior reconciliation vs plain mean under Byzantine
        (miscalibrated or adversarial) robots.
S4 TAR  task router with conformal abstention: selective risk vs coverage.
"""
import json
import math
import os
import random

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fleet_task_results.json")
SEED = 20261112

D = 4            # impedance vector dimension: (Kp, Kd, Fmax, vmax)
TASKS = 32
AXES = 5         # position / distractor / background / unseen object / human
SKILLS = 6       # reach / grasp / lift / place / handover / bimanual
SUCC_TAU = 2.60  # L2 error at which success proxy falls to 50%


def success(err):
    """Smooth success proxy: 1 - sigmoid((err - tau)/scale)."""
    return 1.0 / (1.0 + math.exp((err - SUCC_TAU) / 0.50))


def summary(v):
    return dict(mean=round(float(np.mean(v)), 4),
                worst=round(float(np.min(v)), 4),
                p10=round(float(np.percentile(v, 10)), 4))


# ======================================================================
# S1  Task-Skill-Generalisation factorisation
# ======================================================================
def _true_factors(rng, sigma_task=0.62, sigma_axis=0.46, sigma_skill=0.55):
    base = rng.normal(0, 0.8, D)
    a = rng.normal(0, sigma_task, (TASKS, D))
    b = rng.normal(0, sigma_axis, (AXES, D))
    c = rng.normal(0, sigma_skill, (SKILLS, D))
    skill_of = np.array([t % SKILLS for t in range(TASKS)])
    K = (base[None, None, :] + a[:, None, :] + b[None, :, :]
         + c[skill_of][:, None, :])
    return K, skill_of


def _design(task_idx, axis_idx, skill_idx, with_skill=True):
    # intercept + one-hot task + one-hot axis (+ one-hot skill)
    cols = [np.ones(len(task_idx))]
    for k in range(TASKS):
        cols.append((task_idx == k).astype(float))
    for k in range(AXES):
        cols.append((axis_idx == k).astype(float))
    if with_skill:
        for k in range(SKILLS):
            cols.append((skill_idx == k).astype(float))
    return np.column_stack(cols)


def _ridge_fit(X, Y, lam):
    A = X.T @ X + lam * np.eye(X.shape[1])
    return np.linalg.solve(A, X.T @ Y)


def eval_s1(n_per_cell=2, noise=0.95, seed=SEED, lam=6.0):
    """Hold out, for every task, one generalisation axis (g = task % AXES).
    Training sees the other four axes; test asks for compositional transfer
    to the unseen task-axis cell."""
    rng = np.random.default_rng(seed)
    K, skill_of = _true_factors(np.random.default_rng(seed + 1))
    # small task x axis interaction the additive model cannot explain
    K = K + rng.normal(0, 0.22, K.shape)

    held_axis = np.array([t % AXES for t in range(TASKS)])
    ti, gi = [], []
    for t in range(TASKS):
        for g in range(AXES):
            if g == held_axis[t]:
                continue
            ti += [t] * n_per_cell
            gi += [g] * n_per_cell
    ti, gi = np.array(ti), np.array(gi)
    si = skill_of[ti]
    obs = K[ti, gi] + rng.normal(0, noise, (len(ti), D))

    mu_g = obs.mean(0)
    mu_t = np.zeros((TASKS, D))
    for t in range(TASKS):
        mu_t[t] = obs[ti == t].mean(0)
    mu_c = np.zeros((TASKS, AXES, D))
    for t in range(TASKS):
        for g in range(AXES):
            m = (ti == t) & (gi == g)
            mu_c[t, g] = obs[m].mean(0) if m.any() else mu_t[t]

    Xs = _design(ti, gi, si, True)
    Xa = _design(ti, gi, si, False)
    theta_ts = _ridge_fit(Xs, obs, lam)
    theta_ta = _ridge_fit(Xa, obs, lam)

    def grid_pred(theta, with_skill):
        tt = np.repeat(np.arange(TASKS), AXES)
        gg = np.tile(np.arange(AXES), TASKS)
        X = _design(tt, gg, skill_of[tt], with_skill)
        return (X @ theta).reshape(TASKS, AXES, D)

    pred_t = grid_pred(theta_ts, True)
    pred_ta = grid_pred(theta_ta, False)

    errs = {k: [] for k in ("global", "per_task", "per_cell", "tsf",
                            "task_only")}
    for t in range(TASKS):
        g = held_axis[t]
        true = K[t, g]
        nv = rng.normal(0, noise, D)
        def e(p):
            return float(np.linalg.norm(p + nv - true))
        errs["global"].append(e(mu_g))
        errs["per_task"].append(e(mu_t[t]))
        errs["per_cell"].append(e(mu_c[t, g]))
        errs["tsf"].append(e(pred_t[t, g]))
        errs["task_only"].append(e(pred_ta[t, g]))

    out = {}
    for name, v in errs.items():
        errs_np = np.array(v)
        out[name] = dict(mse=round(float(np.mean(errs_np ** 2)), 4),
                         success=round(float(np.mean([success(e) for e in v])), 4),
                         worst_task_success=round(float(np.min(
                             [success(e) for e in v])), 4))
    return dict(setting=dict(n_per_cell=n_per_cell, noise=noise, lam=lam,
                             tasks=TASKS, axes=AXES, skills=SKILLS,
                             held_out="one axis per task, g = task mod 5",
                             interaction_sigma=0.22), results=out)


# ======================================================================
# S2  Fleet affinity weighting
# ======================================================================
def eval_s2(R=8, n_obs=8, shift=1.1, noise=0.75, seed=SEED, tau_A=0.7):
    """Half of the fleet carries a *systematic* camera/table-height offset.
    Target robot is clean.  Local estimate is noisy; naive pooling is biased;
    affinity weighting should dominate both."""
    rng = np.random.default_rng(seed)
    Ktrue = rng.normal(0, 1.0, D)
    bias = np.zeros((R, D))
    direction = np.array([1.0, 0.8, 0.6, 0.4])
    direction /= np.linalg.norm(direction)
    bias[R // 2:] = shift * direction[None, :]
    bias += rng.normal(0, 0.12, (R, D))          # small individual jitter
    obs = np.array([Ktrue + bias[r] + rng.normal(0, noise, (n_obs, D))
                    for r in range(R)])
    probe = np.array([Ktrue + bias[r] + rng.normal(0, noise, (4, D))
                      for r in range(R)])
    bias_hat = probe.mean(1) - np.median(probe.mean(1), axis=0, keepdims=True)

    res = {k: [] for k in ("target_only", "naive_pool", "affinity",
                           "fam_calibrated")}
    corrected = obs.mean(1) - bias_hat
    med_corr = np.median(corrected, axis=0)
    w = np.exp(-np.sum((corrected - med_corr) ** 2, axis=1) / (2 * tau_A ** 2))
    w = np.maximum(w, 1e-6)
    mu_fam = np.tensordot(w, corrected, axes=(0, 0)) / w.sum()
    for r in range(R):
        mu_local = obs[r].mean(0)
        mu_naive = obs.reshape(-1, D).mean(0)
        w_r = np.exp(-np.sum((bias_hat - bias_hat[r]) ** 2, axis=1)
                     / (2 * tau_A ** 2))
        w_r = np.maximum(w_r, 1e-6)
        mu_aff = np.tensordot(w_r, obs.mean(1), axes=(0, 0)) / w_r.sum()
        res["target_only"].append(success(np.linalg.norm(mu_local - Ktrue)))
        res["naive_pool"].append(success(np.linalg.norm(mu_naive - Ktrue)))
        res["affinity"].append(success(np.linalg.norm(mu_aff - Ktrue)))
        res["fam_calibrated"].append(success(np.linalg.norm(mu_fam - Ktrue)))
    return dict(setting=dict(robots=R, n_obs=n_obs, systematic_shift=shift,
                             noise=noise, tau_A=tau_A),
                results={k: summary(v) for k, v in res.items()},
                clean_target={k: summary(v[:R // 2]) for k, v in res.items()},
                shifted_target={k: summary(v[R // 2:]) for k, v in res.items()})


# ======================================================================
# S3  Cross-robot prior reconciliation under Byzantine reports
# ======================================================================
def eval_s3(seed=SEED, R=10, trials=400, noise=0.55):
    rng = np.random.default_rng(seed)
    fracs = [0.0, 0.1, 0.2, 0.3, 0.4]
    out = {}
    for beta in fracs:
        errs = {"mean": [], "median": [], "trimmed": []}
        for _ in range(trials):
            mu = rng.normal(0, 1.0, D)
            n_bad = int(round(beta * R))
            reports = []
            for i in range(R):
                if i < n_bad:
                    direction = rng.normal(0, 1, D)
                    direction /= np.linalg.norm(direction) + 1e-9
                    reports.append(mu + direction * rng.uniform(2.5, 4.5))
                else:
                    reports.append(mu + rng.normal(0, noise, D))
            rep = np.array(reports)
            mean = rep.mean(0)
            med = np.median(rep, axis=0)
            k = max(1, int(0.2 * R))
            srt = np.sort(rep, axis=0)
            trim = srt[k:R - k].mean(0)
            for name, est in (("mean", mean), ("median", med), ("trimmed", trim)):
                errs[name].append(np.linalg.norm(est - mu))
        out[f"byz_{int(beta*100)}pct"] = {
            k: dict(mse=round(float(np.mean(np.square(v))), 4),
                    success=round(float(np.mean([success(e) for e in v])), 4))
            for k, v in errs.items()}
    return dict(setting=dict(robots=R, trials=trials, report_noise=noise),
                results=out)


# ======================================================================
# S4  Task router with conformal abstention
# ======================================================================
def eval_s4(seed=SEED, n=6000, effect=6.0, alpha=0.05):
    rng = np.random.default_rng(seed)
    true_task = rng.integers(0, TASKS, n)
    logits = rng.normal(0, 1.0, (n, TASKS))
    logits[np.arange(n), true_task] += effect
    logits += rng.gumbel(0, 1.0, (n, TASKS))
    p = np.exp(logits - logits.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    ps = np.sort(p, axis=1)
    conf = ps[:, -1] - ps[:, -2]          # top-1 margin (better selective signal)
    order = rng.permutation(n)
    cal, test = order[:n // 2], order[n // 2:]
    correct = p.argmax(1) == true_task

    # conformal threshold on calibration: smallest conf whose selective
    # error rate <= alpha (with a conservative finite-sample correction)
    grid = np.unique(np.round(conf[cal], 3))       # ascending: max coverage
    tau = 1.01
    for g in grid:
        keep = cal[conf[cal] >= g]
        if len(keep) < 200:
            continue
        if 1.0 - correct[keep].mean() <= alpha:
            tau = g
            break
    keep = test[conf[test] >= tau]
    coverage = len(keep) / len(test)
    selective_err = 1.0 - correct[keep].mean() if len(keep) else float("nan")
    forced_err = 1.0 - correct[test].mean()
    return dict(setting=dict(episodes=n, effect_size=effect, alpha=alpha),
                results=dict(tau=round(float(tau), 3),
                             coverage=round(float(coverage), 4),
                             selective_error=round(float(selective_err), 4),
                             route_all_error=round(float(forced_err), 4),
                             abstention_rate=round(float(1 - coverage), 4)))


def main():
    res = dict(
        note="Synthetic mechanism check for Round-61 FTCG; NOT benchmark evidence.",
        s1_tsf=eval_s1(),
        s1_tsf_1shot=eval_s1(n_per_cell=1),
        s2_affinity=eval_s2(),
        s3_reconcile=eval_s3(),
        s4_router=eval_s4(),
    )
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
