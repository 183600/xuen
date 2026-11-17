"""Round-2 probe (UniBot line): does the real demonstration state stream support
a *shared skill vocabulary* + *low-rank action basis*?

Inputs are the 12 per-task state extracts in exp/unibot_states/*.npz
('contig' = contiguous frames from 1-2 episodes, 800 frames/task, real G1+Dex1).
No images are used here: this is a cheap proprio-only probe, not a full policy.

Outputs exp/round2_skill_basis_probe.json
"""
import glob
import json
import os

import numpy as np

FPS = 30.0
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "round2_skill_basis_probe.json")
SKILLS = ["REACH", "REGROUP", "HOLD", "CARRY"]


def medfilt(x, k):
    if k <= 1:
        return x
    pad = k // 2
    xp = np.pad(x, (pad, pad), mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(xp, k), axis=1)


def load_episodes(path):
    d = np.load(path, allow_pickle=True)["contig"].item()
    ep = d["episode_index"]
    out = []
    for e in np.unique(ep):
        idx = np.where(ep == e)[0]
        out.append({k: v[idx] for k, v in d.items()})
    return out


def segment(ep, side):
    g = medfilt(ep[f"observation.state.{side}_gripper"].astype(float), 5)
    pos = ep[f"observation.state.{side}_ee_pose_gripper_base"][:, :3]
    sp = np.zeros(len(g))
    sp[1:] = np.linalg.norm(np.diff(pos, axis=0), axis=1) * FPS
    sp = medfilt(sp, 9)
    closed = np.zeros(len(g), dtype=bool)
    c = False
    for t, v in enumerate(g):
        if c and v > 1.6:
            c = False
        elif not c and v < 1.0:
            c = True
        closed[t] = c
    moving = np.zeros(len(g), dtype=bool)
    m = False
    for t, v in enumerate(sp):
        if m and v < 0.02:
            m = False
        elif not m and v > 0.05:
            m = True
        moving[t] = m
    lab = np.empty(len(g), dtype=object)
    for t in range(len(g)):
        lab[t] = ("CARRY" if moving[t] else "HOLD") if closed[t] else (
            "REACH" if moving[t] else "REGROUP")
    return lab, sp, g, pos


def merge_min(lab, minlen=10):
    lab = lab.copy()
    n = len(lab)
    while True:
        starts = [0] + [i for i in range(1, n) if lab[i] != lab[i - 1]] + [n]
        done = True
        for a, b in zip(starts[:-1], starts[1:]):
            if b - a < minlen:
                left = lab[a - 1] if a > 0 else None
                right = lab[b] if b < n else None
                if left is None and right is None:
                    continue
                if left is None:
                    new = right
                elif right is None:
                    new = left
                else:
                    new = left if a < n - b else right
                lab[a:b] = new
                done = False
                break
        if done:
            return lab


def runs(lab):
    starts = np.r_[0, np.where(lab[1:] != lab[:-1])[0] + 1, len(lab)]
    return [(lab[starts[i]], int(starts[i + 1] - starts[i]))
            for i in range(len(starts) - 1)]


def kmeans(X, k, iters=100, restarts=12, seed=0):
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(restarts):
        # k-means++ init
        idx = [int(rng.integers(len(X)))]
        for _ in range(1, k):
            d2 = np.min(((X[:, None, :] - X[idx][None, :, :]) ** 2).sum(-1), axis=1)
            p = d2 / d2.sum()
            idx.append(int(rng.choice(len(X), p=p)))
        C = X[idx].copy()
        for _ in range(iters):
            dist = ((X[:, None, :] - C[None, :, :]) ** 2).sum(-1)
            a = dist.argmin(1)
            newC = np.array([X[a == j].mean(0) if (a == j).any() else C[j]
                             for j in range(k)])
            if np.allclose(newC, C, atol=1e-6):
                break
            C = newC
        sse = ((X - C[a]) ** 2).sum()
        if best is None or sse < best[0]:
            best = (sse, a, C)
    return best[1], best[2]


def entropy(p):
    p = np.asarray(p, dtype=float)
    p = p[p > 0]
    return float(-(p * np.log(p)).sum())


def nmi(a, b):
    ua = {v: i for i, v in enumerate(sorted(set(a)))}
    ub = {v: i for i, v in enumerate(sorted(set(b)))}
    A = np.array([ua[v] for v in a])
    B = np.array([ub[v] for v in b])
    n = len(A)
    ca = np.bincount(A, minlength=len(ua))
    cb = np.bincount(B, minlength=len(ub))
    cont = np.zeros((len(ua), len(ub)))
    for x, y in zip(A, B):
        cont[x, y] += 1
    pa = ca / n
    pb = cb / n
    pab = cont / n
    mi = 0.0
    for i in range(len(ua)):
        for j in range(len(ub)):
            if pab[i, j] > 0:
                mi += pab[i, j] * np.log(pab[i, j] / (pa[i] * pb[j]))
    ha = entropy(pa)
    hb = entropy(pb)
    return float(mi / np.sqrt(ha * hb)) if ha > 0 and hb > 0 else 0.0


tasks = [os.path.basename(p)[len("G1_Dex1_"):-4]
         for p in sorted(glob.glob(os.path.join(HERE, "unibot_states", "*.npz")))]

fractions = {}
transitions = {}
seg_feats = []
seg_labels = []
seg_task = []
global_action_feats = []
global_action_mean = []
action_task = []
action_ep = []
for ti, (task, path) in enumerate(zip(tasks, sorted(
        glob.glob(os.path.join(HERE, "unibot_states", "*.npz"))))):
    counts = {s: 0 for s in SKILLS}
    total = 0
    trans = np.zeros((len(SKILLS), len(SKILLS)))
    for ei, ep in enumerate(load_episodes(path)):
        # action-chunk features: commanded EE delta over 15-frame windows
        L = ep["action.left_ee_pose_gripper_base"]
        R = ep["action.right_ee_pose_gripper_base"]
        gL = ep["action.left_gripper"].astype(float)
        gR = ep["action.right_gripper"].astype(float)
        dL = np.diff(L, axis=0)
        dR = np.diff(R, axis=0)
        for t in range(0, len(dL) - 15, 5):
            sl = slice(t, t + 15)
            f = np.r_[dL[sl].mean(0), dL[sl].std(0),
                      dR[sl].mean(0), dR[sl].std(0),
                      np.abs(np.diff(gL[sl])).mean(),
                      np.abs(np.diff(gR[sl])).mean()]
            global_action_feats.append(f)
            global_action_mean.append(np.r_[dL[sl].mean(0), np.abs(np.diff(gL[sl])).mean(),
                                            dR[sl].mean(0), np.abs(np.diff(gR[sl])).mean()])
            action_task.append(task)
            action_ep.append(ei)
        for side in ["left", "right"]:
            lab, sp, g, pos = segment(ep, side)
            lab = merge_min(lab, 10)
            for s, n in runs(lab):
                counts[s] += n
                total += n
            for a, b in zip(lab[:-1], lab[1:]):
                if a != b:
                    trans[SKILLS.index(a), SKILLS.index(b)] += 1
            # segment features (kinematic, not label-based)
            for a, b in [(0, 0)]:
                pass
            starts = np.r_[0, np.where(lab[1:] != lab[:-1])[0] + 1, len(lab)]
            for i in range(len(starts) - 1):
                a, b = starts[i], starts[i + 1]
                if b - a < 3:
                    continue
                spd = sp[a:b]
                gr = g[a:b]
                p = pos[a:b]
                disp = np.linalg.norm(p[-1] - p[0]) if len(p) else 0.0
                seg_feats.append([
                    float(b - a), float(spd.mean()), float(spd.max()),
                    float(spd.std()), float(gr.mean()),
                    float(abs(gr[-1] - gr[0])), float(disp),
                    float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())
                    if len(p) > 1 else 0.0,
                ])
                seg_labels.append(lab[a])
                seg_task.append(task)
    for s in SKILLS:
        counts[s] /= max(total, 1)
    fractions[task] = {s: round(float(counts[s]), 4) for s in SKILLS}
    row = trans.sum(1, keepdims=True)
    transitions[task] = np.divide(trans, np.maximum(row, 1)).round(3).tolist()

F = np.array([[fractions[t][s] for s in SKILLS] for t in tasks])
Fc = F - F.mean(0, keepdims=True)
sv = np.linalg.svd(Fc, compute_uv=False)
p = sv ** 2 / (sv ** 2).sum()
rank90 = int(np.searchsorted(np.cumsum(p), 0.9) + 1)
ent_rank = float(np.exp(entropy(p))) if (p > 0).any() else 0.0

# shared-vocabulary: Jaccard on skills with >5% mass
sets = {t: {s for s in SKILLS if fractions[t][s] > 0.05} for t in tasks}
jac = []
for i in range(len(tasks)):
    for j in range(i + 1, len(tasks)):
        a, b = sets[tasks[i]], sets[tasks[j]]
        jac.append(len(a & b) / max(len(a | b), 1))
# per-skill breadth: number of tasks with >5% mass
breadth = {s: int(sum(fractions[t][s] > 0.05 for t in tasks)) for s in SKILLS}

# unsupervised segment clustering
X = np.array(seg_feats, dtype=float)
X = (X - X.mean(0)) / (X.std(0) + 1e-9)
sils = {}
for k in range(2, 13):
    a, C = kmeans(X, k, restarts=8, seed=42 + k)
    # silhouette on a subsample for speed
    rng = np.random.default_rng(0)
    idx = rng.choice(len(X), size=min(300, len(X)), replace=False)
    dist = ((X[idx, None, :] - C[None, :, :]) ** 2).sum(-1) ** 0.5
    own = dist[np.arange(len(idx)), a[idx]]
    mask = dist.copy()
    mask[np.arange(len(idx)), a[idx]] = np.inf
    other = mask.min(1)
    s = (other - own) / np.maximum(other, own)
    sils[k] = float(np.mean(s))

# pick K by silhouette, then count shared clusters
bestk = max(sils, key=sils.get)
def cluster_stats(k):
    a, C = kmeans(X, k, restarts=16, seed=7)
    usage = {t: np.zeros(k) for t in tasks}
    for aa, tt in zip(a, seg_task):
        usage[tt][aa] += 1
    shared = int(sum(sum(usage[t][j] > 0 for t in tasks) >= 2
                     for j in range(k)))
    breadth = [int(sum(usage[t][j] > 0 for t in tasks)) for j in range(k)]
    return {
        "k": int(k),
        "clusters_used_by_ge2_tasks": shared,
        "cluster_task_breadth": breadth,
        "nmi_with_deterministic_labels": round(float(nmi(a, seg_labels)), 3),
        "per_task_cluster_entropy_mean": round(float(np.mean([
            entropy(usage[t] / max(usage[t].sum(), 1)) for t in tasks])), 3),
    }
cluster_by_k = {str(k): cluster_stats(k) for k in [2, 4, 6, 8, 10]}
shared = cluster_by_k[str(bestk)]["clusters_used_by_ge2_tasks"]
cluster_breadth = cluster_by_k[str(bestk)]["cluster_task_breadth"]
cluster_nmi = cluster_by_k[str(bestk)]["nmi_with_deterministic_labels"]

# action subspace
A = np.array(global_action_feats, dtype=float)
A = (A - A.mean(0)) / (A.std(0) + 1e-9)
U, sA, Vt = np.linalg.svd(A - A.mean(0), full_matrices=False)
pA = sA ** 2 / (sA ** 2).sum()
act_rank90 = int(np.searchsorted(np.cumsum(pA), 0.9) + 1)
act_ent = float(np.exp(entropy(pA)))
# per-task action centroid separability: nearest centroid, leave-episode-out-ish
# (we only have 1-2 episodes/task, so report in-sample centroid accuracy as a
# crude upper bound, and nearest-centroid label agreement)
cent = {t: A[[i for i, tt in enumerate(action_task) if tt == t]].mean(0)
        for t in tasks}
cent_arr = np.array([cent[t] for t in tasks])
pred = [tasks[j] for j in ((A[:, None, :] - cent_arr[None]) ** 2).sum(-1).argmin(1)]
cent_acc = float(np.mean([p == t for p, t in zip(pred, action_task)]))
# per-task principal angles to global top-r subspace (r=rank90)
r = min(act_rank90, A.shape[1], 6)
G = Vt[:r].T
angles = {}
for t in tasks:
    At = A[[i for i, tt in enumerate(action_task) if tt == t]]
    if len(At) < 2:
        continue
    _, _, Vt_t = np.linalg.svd(At - At.mean(0), full_matrices=False)
    Q = Vt_t[:min(r, len(At) - 1)].T
    sv_t = np.linalg.svd(Q.T @ G, compute_uv=False)
    angles[t] = round(float(np.degrees(np.arccos(np.clip(sv_t.min(), -1, 1)))), 1)

Am = np.array(global_action_mean, dtype=float)
Am = (Am - Am.mean(0)) / (Am.std(0) + 1e-9)
Um, sm, Vtm = np.linalg.svd(Am - Am.mean(0), full_matrices=False)
pm = sm ** 2 / (sm ** 2).sum()
act_mean_rank90 = int(np.searchsorted(np.cumsum(pm), 0.9) + 1)
act_mean_ent = float(np.exp(entropy(pm)))
# per-task rank90 on the mean-only features
per_task_rank = {}
for t in tasks:
    At = Am[[i for i, tt in enumerate(action_task) if tt == t]]
    if len(At) < 5:
        continue
    _, st, _ = np.linalg.svd(At - At.mean(0), full_matrices=False)
    pt = st ** 2 / (st ** 2).sum()
    per_task_rank[t] = int(np.searchsorted(np.cumsum(pt), 0.9) + 1)

out = {
    "tasks": tasks,
    "n_frames_per_task": 800,
    "skill_fractions": fractions,
    "transition_rows": transitions,
    "task_x_skill_rank": {
        "singular_values": [round(float(v), 4) for v in sv],
        "cum_var": [round(float(v), 3) for v in np.cumsum(p)],
        "rank90": rank90,
        "entropy_rank": round(ent_rank, 2),
        "max_rank": len(SKILLS),
    },
    "shared_vocabulary": {
        "avg_pairwise_skill_set_jaccard": round(float(np.mean(jac)), 3),
        "skill_breadth_tasks_gt5pct": breadth,
        "num_skills": len(SKILLS),
    },
    "segment_clustering": {
        "n_segments": int(len(X)),
        "silhouette_by_k": {str(k): round(v, 3) for k, v in sils.items()},
        "best_k": int(bestk),
        "clusters_used_by_ge2_tasks": shared,
        "cluster_task_breadth": cluster_breadth,
        "nmi_with_deterministic_labels": round(float(cluster_nmi), 3),
        "by_k": cluster_by_k,
    },
    "action_structure": {
        "n_windows": int(len(A)),
        "feature_dim": int(A.shape[1]),
        "rank90": act_rank90,
        "entropy_rank": round(act_ent, 2),
        "cum_var_top10": [round(float(v), 3) for v in np.cumsum(pA)[:10]],
        "nearest_centroid_task_accuracy_in_sample": round(cent_acc, 3),
        "chance": round(1.0 / len(tasks), 3),
        "principal_angle_to_global_top_r_deg": angles,
        "mean_only_feature_dim": int(Am.shape[1]),
        "mean_only_rank90": act_mean_rank90,
        "mean_only_entropy_rank": round(act_mean_ent, 2),
        "mean_only_per_task_rank90": per_task_rank,
    },
    "disclaimer": "12 tasks only, 800 contiguous frames each, proprio-only; "
                  "not a policy benchmark. Used as a cheap falsification probe "
                  "for the shared-skill / low-rank action assumptions.",
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
