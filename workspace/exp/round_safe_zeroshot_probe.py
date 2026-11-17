"""Round-2 probe (UniBot line): safety-alignment / zero-shot-generalization.

Question: can a *fixed* proprioceptive safety envelope calibrated on some
tasks transfer to held-out tasks, and does adaptive conformal inference
(ACI) repair the calibration drift without any test labels?

Inputs are the 12 real G1+Dex1 contiguous state extracts in
exp/unibot_states/*.npz (800 frames/task, no images, no success labels).
This is a cheap falsification probe, not a policy rollout.  Outputs
exp/round_safe_zeroshot_probe.json.
"""
import glob
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "round_safe_zeroshot_probe.json")
FPS = 30.0
W = 30          # 1.0 s window
STRIDE = 15     # 0.5 s
H = 15          # 0.5 s look-ahead for the cross-task action probe
DELTA = 0.05    # target high-stress rate (5%)
SEED = 0
rng = np.random.default_rng(SEED)


def load_episodes(path):
    d = np.load(path, allow_pickle=True)["contig"].item()
    ep = d["episode_index"]
    out = []
    for e in np.unique(ep):
        idx = np.where(ep == e)[0]
        # keep only contiguous runs (episode_index can repeat across blocks)
        runs, start = [], 0
        for i in range(1, len(idx)):
            if idx[i] != idx[i - 1] + 1:
                runs.append(idx[start:i])
                start = i
        runs.append(idx[start:])
        for r in runs:
            if len(r) >= 60:
                out.append({k: v[r] for k, v in d.items()})
    return out


def fd(x, order=1):
    if order == 0:
        return x
    return fd(np.gradient(x, axis=0), order - 1) * FPS


def side_features(ep, side):
    pos = ep[f"observation.state.{side}_ee_pose_gripper_base"].astype(float)
    q = ep[f"observation.state.{side}_arm"].astype(float)
    g = ep[f"observation.state.{side}_gripper"].astype(float)
    v = fd(pos, 1)
    a = fd(pos, 2)
    j = fd(pos, 3)
    dq = fd(q, 1)
    ddq = fd(q, 2)
    dg = fd(g[:, None], 1)[:, 0]
    return {
        "pos": pos, "q": q, "g": g,
        "speed": np.linalg.norm(v[:, :3], axis=1),
        "acc": np.linalg.norm(a[:, :3], axis=1),
        "jerk": np.linalg.norm(j[:, :3], axis=1),
        "ang_speed": np.linalg.norm(v[:, 3:], axis=1),
        "dq": np.linalg.norm(dq, axis=1),
        "ddq": np.linalg.norm(ddq, axis=1),
        "dg": np.abs(dg),
        "v": v, "a": a, "j": j,
    }


def window_feats(ep):
    L = side_features(ep, "left")
    R = side_features(ep, "right")
    torso = ep["observation.state.state_torso"].astype(float)
    waist = ep["observation.state.waist_state_joint"].astype(float)
    n = len(L["g"])
    hand_dist = np.linalg.norm(L["pos"][:, :3] - R["pos"][:, :3], axis=1)
    rel_speed = np.linalg.norm(L["v"][:, :3] - R["v"][:, :3], axis=1)
    dtw = fd(torso, 1)
    dw = fd(waist, 1)
    dt = 1.0 / FPS
    # --- feature groups (per window) ---
    abs_feats, dyn_feats, stress = [], [], []
    for s in range(0, n - W + 1, STRIDE):
        sl = slice(s, s + W)
        abs_feats.append(np.r_[
            L["pos"][sl, :3].mean(0), R["pos"][sl, :3].mean(0),
            L["q"][sl].mean(0), R["q"][sl].mean(0),
            L["g"][sl].mean(), R["g"][sl].mean(),
            torso[sl].mean(0), waist[sl].mean(0),
        ])
        dyn_feats.append(np.r_[
            L["speed"][sl].mean(), L["speed"][sl].max(),
            L["acc"][sl].mean(), L["acc"][sl].max(),
            L["jerk"][sl].mean(), L["jerk"][sl].max(),
            L["ang_speed"][sl].mean(), L["ang_speed"][sl].max(),
            L["dq"][sl].mean(), L["dq"][sl].max(),
            L["ddq"][sl].mean(), L["ddq"][sl].max(),
            L["dg"][sl].mean(), L["dg"][sl].max(),
            R["speed"][sl].mean(), R["speed"][sl].max(),
            R["acc"][sl].mean(), R["acc"][sl].max(),
            R["jerk"][sl].mean(), R["jerk"][sl].max(),
            R["ang_speed"][sl].mean(), R["ang_speed"][sl].max(),
            R["dq"][sl].mean(), R["dq"][sl].max(),
            R["ddq"][sl].mean(), R["ddq"][sl].max(),
            R["dg"][sl].mean(), R["dg"][sl].max(),
            hand_dist[sl].mean(), hand_dist[sl].std(),
            rel_speed[sl].mean(), rel_speed[sl].max(),
            np.linalg.norm(dtw[sl], axis=1).mean(),
            np.linalg.norm(dw[sl], axis=1).mean(),
        ])
        # physically-motivated composite stress proxy:
        # impact = EE jerk + joint jerk, plus a grip-transition term.
        comp = (np.log1p(L["jerk"][sl] + R["jerk"][sl])
                + np.log1p(L["ddq"][sl] + R["ddq"][sl])
                + 0.5 * np.log1p(1e3 * (L["dg"][sl] + R["dg"][sl])))
        stress.append(float(np.percentile(comp, 95)))
    return np.asarray(abs_feats), np.asarray(dyn_feats), np.asarray(stress)


def auroc(pos_scores, neg_scores):
    s = np.r_[pos_scores, neg_scores].astype(float)
    lab = np.r_[np.ones(len(pos_scores)), np.zeros(len(neg_scores))]
    order = np.argsort(s)
    ranks = np.empty(len(s), float)
    ranks[order] = np.arange(1, len(s) + 1)
    # average ranks for ties
    _, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    for gi in np.where(cnt > 1)[0]:
        idx = np.where(inv == gi)[0]
        ranks[idx] = ranks[idx].mean()
    n1, n0 = len(pos_scores), len(neg_scores)
    return float((ranks[lab == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def gauss_ood(train, test):
    mu = train.mean(0)
    var = train.var(0) + 1e-6
    f = lambda x: (((x - mu) ** 2) / var).sum(1)
    return f(train), f(test)


def standardize_fit(x):
    mu = x.mean(0)
    sd = x.std(0) + 1e-8
    return mu, sd


def aci_run(scores, delta=DELTA, gamma=0.01, buffer=60, alpha0=0.05):
    """Adaptive conformal inference on a score stream with a rolling quantile."""
    buf = []
    alpha = alpha0
    exceed, alphas, thresholds = [], [], []
    for s in scores:
        q = np.quantile(buf, 1 - alpha) if len(buf) >= 20 else np.inf
        e = int(s > q)
        exceed.append(e)
        thresholds.append(float(q) if np.isfinite(q) else None)
        alphas.append(float(alpha))
        buf.append(s)
        if len(buf) > buffer:
            buf.pop(0)
        alpha = float(np.clip(alpha + gamma * (delta - e), 0.005, 0.5))
    return np.asarray(exceed), np.asarray(alphas), thresholds


def main():
    paths = sorted(glob.glob(os.path.join(HERE, "unibot_states", "*.npz")))
    tasks = [os.path.basename(p)[len("G1_Dex1_"):-4] for p in paths]
    data = {}
    reg_abs, reg_dyn, reg_canon, reg_y, reg_tid = [], [], [], [], []
    for ti, (t, p) in enumerate(zip(tasks, paths)):
        A, D, Dc, S, reg = [], [], [], [], []
        for ep in load_episodes(p):
            a, d, s = window_feats(ep)
            med = np.median(d, 0)
            mad = np.median(np.abs(d - med), 0) + 1e-6
            dc = (d - med) / mad
            A.append(a); D.append(d); Dc.append(dc); S.append(s)
            al = ep["action.left_ee_pose_gripper_base"].astype(float)
            ar = ep["action.right_ee_pose_gripper_base"].astype(float)
            gl = ep["action.left_gripper"].astype(float)
            gr = ep["action.right_gripper"].astype(float)
            for i in range(len(a)):
                e = i * STRIDE + W
                if e + H >= len(al):
                    break
                y = np.r_[al[e + H] - al[e], ar[e + H] - ar[e],
                          gl[e + H] - gl[e], gr[e + H] - gr[e]]
                reg_abs.append(a[i]); reg_dyn.append(d[i])
                reg_canon.append(dc[i]); reg_y.append(y); reg_tid.append(ti)
        data[t] = {"abs": np.vstack(A), "dyn": np.vstack(D),
                   "dyn_canon": np.vstack(Dc), "stress": np.r_[*S]}

    # deterministic split: 8 calibration tasks, 4 held-out tasks (stratified by name order)
    rng2 = np.random.default_rng(SEED + 7)
    order = list(rng2.permutation(len(tasks)))
    cal_idx = sorted(order[:8])
    test_idx = sorted(order[8:])
    cal = [tasks[i] for i in cal_idx]
    test = [tasks[i] for i in test_idx]

    res = {"n_tasks": len(tasks), "calibration_tasks": cal,
           "heldout_tasks": test, "delta": DELTA, "window_s": W / FPS,
           "stride_s": STRIDE / FPS, "feature_groups": {}}

    # --- 1. OOD separability: diagonal-Gaussian Mahalanobis, AUROC heldout vs cal ---
    for grp in ["abs", "dyn"]:
        Xc = np.vstack([data[t][grp] for t in cal])
        # per-task standardization (test-time normalisation by own episode/task stats)
        def coeff(x, mu, sd):
            return (x - mu) / sd
        mu, sd = standardize_fit(Xc)
        Xc_s = coeff(Xc, mu, sd)
        mu2, sd2 = standardize_fit(Xc_s)
        inner = (((Xc_s - mu2) ** 2) / (sd2 ** 2 + 1e-6)).sum(1)
        task_aurocs, per_task_rate = {}, {}
        for t in test:
            Xt = coeff(data[t][grp], mu, sd)
            it = (((Xt - mu2) ** 2) / (sd2 ** 2 + 1e-6)).sum(1)
            task_aurocs[t] = round(auroc(it, inner), 4)
        res["feature_groups"][grp] = {
            "dim": int(Xc.shape[1]),
            "ood_auroc_mean": round(float(np.mean(list(task_aurocs.values()))), 4),
        "ood_separability_mean": round(float(np.mean([abs(v - 0.5) for v in task_aurocs.values()])), 4),
            "ood_separability_mean": round(float(np.mean([abs(v - 0.5) for v in task_aurocs.values()])), 4),
            "ood_auroc_min": round(float(np.min(list(task_aurocs.values()))), 4),
            "ood_auroc_max": round(float(np.max(list(task_aurocs.values()))), 4),
            "per_task_auroc": task_aurocs,
        }

    # --- 1b. per-episode canonicalised dynamics (median/MAD over episode) ---
    # The normaliser uses only the test episode itself -> still zero-shot.
    canon = {t: data[t]["dyn_canon"] for t in tasks}
    Xc = np.vstack([canon[t] for t in cal])
    mu2, sd2 = standardize_fit(Xc)
    inner = (((Xc - mu2) ** 2) / (sd2 ** 2 + 1e-6)).sum(1)
    task_aurocs = {}
    for t in test:
        Xt = canon[t]
        it = (((Xt - mu2) ** 2) / (sd2 ** 2 + 1e-6)).sum(1)
        task_aurocs[t] = round(auroc(it, inner), 4)
    res["feature_groups"]["dyn_episode_canon"] = {
        "dim": int(Xc.shape[1]),
        "ood_auroc_mean": round(float(np.mean(list(task_aurocs.values()))), 4),
        "ood_separability_mean": round(float(np.mean([abs(v - 0.5) for v in task_aurocs.values()])), 4),
        "ood_auroc_min": round(float(np.min(list(task_aurocs.values()))), 4),
        "ood_auroc_max": round(float(np.max(list(task_aurocs.values()))), 4),
        "per_task_auroc": task_aurocs,
    }

    # --- 1c. negative control: naive zero-shot action regression ---
    # Can a linear map from window features to the next 0.5 s action delta
    # transfer to held-out tasks?  If not, representation invariance alone is
    # insufficient and a compositional/affordance layer is required.
    def ridge_fit_predict(Xtr, ytr, Xte, lam=1.0):
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-8
        Xtr = np.c_[np.ones(len(Xtr)), (Xtr - mu) / sd]
        Xte = np.c_[np.ones(len(Xte)), (Xte - mu) / sd]
        Wm = np.linalg.solve(Xtr.T @ Xtr + lam * np.eye(Xtr.shape[1]), Xtr.T @ ytr)
        return Xte @ Wm

    tid_arr = np.asarray(reg_tid)
    cal_mask = np.isin(tid_arr, cal_idx)
    test_mask = np.isin(tid_arr, test_idx)
    Yreg = np.asarray(reg_y)
    reg_res = {}
    for name, arr in [("abs", reg_abs), ("dyn", reg_dyn), ("dyn_episode_canon", reg_canon)]:
        XX = np.asarray(arr)
        pred = ridge_fit_predict(XX[cal_mask], Yreg[cal_mask], XX[test_mask])
        yt = Yreg[test_mask]
        sse = ((yt - pred) ** 2).sum(0)
        sst = ((yt - yt.mean(0)) ** 2).sum(0) + 1e-9
        r2 = 1 - sse / sst
        r2_tasks = []
        for ti in test_idx:
            m = tid_arr[test_mask] == ti
            if m.sum() < 2:
                continue
            sse_t = ((yt[m] - pred[m]) ** 2).sum(0)
            sst_t = ((yt[m] - yt[m].mean(0)) ** 2).sum(0) + 1e-9
            r2_tasks.append(float(np.median(1 - sse_t / sst_t)))
        cors = []
        for j in range(yt.shape[1]):
            if yt[:, j].std() > 1e-9 and pred[:, j].std() > 1e-9:
                cors.append(float(np.corrcoef(yt[:, j], pred[:, j])[0, 1]))
        reg_res[name] = {
            "dim": int(XX.shape[1]), "n_test": int(test_mask.sum()),
            "median_R2_over_dims": round(float(np.median(r2)), 4),
            "mean_R2_over_dims": round(float(np.mean(r2)), 4),
            "median_corr_over_dims": round(float(np.median(cors)), 4),
            "per_task_median_R2": [round(x, 4) for x in r2_tasks],
        }
    res["zero_shot_action_regression"] = reg_res

    # --- 2. static split-conformal threshold vs ACI under task shift ---
    cal_scores = np.r_[*[data[t]["stress"] for t in cal]]
    q_static = float(np.quantile(cal_scores, 1 - DELTA))
    per_task = {}
    for t in test:
        s = data[t]["stress"]
        per_task[t] = {
            "n": int(len(s)),
            "static_rate": round(float((s > q_static).mean()), 4),
            "oracle_q": round(float(np.quantile(s, 1 - DELTA)), 4),
        }
    # order test tasks by static deviation (worst first) to make shift visible
    seq_tasks = sorted(test, key=lambda t: abs(per_task[t]["static_rate"] - DELTA),
                       reverse=True)
    seq = np.r_[*[data[t]["stress"] for t in seq_tasks]]
    exceed, alphas, thresholds = aci_run(seq)
    # per-task ACI rates
    pos = 0
    for t in seq_tasks:
        n = len(data[t]["stress"])
        per_task[t]["aci_rate"] = round(float(exceed[pos:pos + n].mean()), 4)
        per_task[t]["seq_order"] = len([x for x in seq_tasks[:seq_tasks.index(t)]])
        pos += n
    # repeated 4-task sequence x 8 cycles: does ACI converge on a longer stream?
    reps = 8
    seq_rep = np.tile(seq, reps)
    ex_rep, al_rep, _ = aci_run(seq_rep)
    last_cycle = ex_rep[-len(seq):]
    last_rates = {}
    pos2 = 0
    for t in seq_tasks:
        n = len(data[t]["stress"])
        last_rates[t] = round(float(last_cycle[pos2:pos2 + n].mean()), 4)
        pos2 += n
    res["calibration_transfer"] = {
        "q_static": round(q_static, 6),
        "static_mean_rate": round(float(np.mean([per_task[t]["static_rate"] for t in test])), 4),
        "static_min_rate": round(float(np.min([per_task[t]["static_rate"] for t in test])), 4),
        "static_max_rate": round(float(np.max([per_task[t]["static_rate"] for t in test])), 4),
        "static_max_abs_dev": round(float(np.max([abs(per_task[t]["static_rate"] - DELTA) for t in test])), 4),
        "aci_overall_rate": round(float(exceed.mean()), 4),
        "aci_max_abs_dev": round(float(np.max([abs(per_task[t]["aci_rate"] - DELTA) for t in test])), 4),
        "aci_final_alpha": round(float(alphas[-1]), 4),
        "sequence": seq_tasks,
        "per_task": per_task,
        "repeated_sequence": {
            "cycles": reps,
            "overall_rate": round(float(ex_rep.mean()), 4),
            "last_cycle_max_abs_dev": round(float(np.max([abs(v - DELTA) for v in last_rates.values()])), 4),
            "last_cycle_rates": last_rates,
        },
    }

    # --- 2b. pre-registered sensitivity check (short domains: small gamma is stable) ---
    sens = []
    for gamma in [0.01, 0.02, 0.05]:
        for buf in [60, 120, 240]:
            ex, _, _ = aci_run(seq, gamma=gamma, buffer=buf)
            pos3 = 0
            rates = {}
            for t in seq_tasks:
                n = len(data[t]["stress"])
                rates[t] = float(ex[pos3:pos3 + n].mean())
                pos3 += n
            sens.append({"gamma": gamma, "buffer": buf,
                         "overall": round(float(ex.mean()), 4),
                         "max_abs_dev": round(float(max(abs(v - DELTA) for v in rates.values())), 4)})
    res["calibration_transfer"]["sensitivity"] = sens

    # --- 3. compositional coverage of the 32 task names (light-weight) ---
    lb = json.load(open(os.path.join(HERE, "r16_leaderboard_data.json")))
    names = lb["tasks"]
    verbs = ["Hang", "Collect", "Pack", "Sort", "Disconnect", "Arrange", "Place",
             "Organize", "Plug", "Pick", "Unlock", "Open", "Fold", "Stack",
             "Clear", "Spell", "Store", "Remove", "Transfer", "Zip"]
    vset = sorted({v for v in verbs for nm in names if nm.lower().startswith(v.lower())})
    # crude object head = tokens after the verb
    objs = set()
    for nm in names:
        toks = nm.split()
        for i, tk in enumerate(toks):
            if tk.lower() in [v.lower() for v in verbs]:
                if i + 1 < len(toks):
                    objs.add(" ".join(toks[i + 1:]).lower())
    res["compositional_coverage"] = {
        "n_tasks": len(names), "n_verb_heads": len(vset),
        "verb_heads": vset, "n_object_heads": len(objs),
        "task_per_verb": round(len(names) / max(len(vset), 1), 2),
    }

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps({
        "heldout": test,
        "ood_auroc": {k: v["ood_auroc_mean"] for k, v in res["feature_groups"].items()},
        "static_rate": [per_task[t]["static_rate"] for t in test],
        "static_max_abs_dev": res["calibration_transfer"]["static_max_abs_dev"],
        "aci_overall": res["calibration_transfer"]["aci_overall_rate"],
        "aci_max_abs_dev": res["calibration_transfer"]["aci_max_abs_dev"],
        "compositional": res["compositional_coverage"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
