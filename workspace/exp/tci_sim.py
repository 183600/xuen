#!/usr/bin/env python3
"""Round-1 (inspiration v3: embodied-intelligence x real-world-generalization).

Proxy mechanism check for TCI (Task-Conditional Invariance).

NOT a robot result.  It isolates one claim:
  A task-agnostic invariance/augmentation operator can remove a *task-relevant*
  cue (colour for a sorting task, shape for a moving task) and therefore hurts
  worst-axis OOD accuracy, while a language-conditioned gate that only removes
  the *task-nuisance* factors keeps the relevant cue and removes the spurious
  background correlation.

Tasks
  T1 "move": label = shape (4 classes), colour is nuisance.
  T2 "sort": label = colour (4 classes), shape is nuisance.
Training set intentionally plants a spurious correlation: background == label
with p=0.8.  OOD axes break that correlation or shift nuisance statistics.
All numbers are synthetic; see exp/tci_results.json.
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = int(os.environ.get("TCI_SEED", "0"))
RNG = np.random.default_rng(SEED)

# feature layout
TASK = [0, 1]
SHAPE = list(range(2, 6))
COLOR = list(range(6, 10))
BG = list(range(10, 14))
DISTRACTOR = 14
POS = [15, 16]
LIGHT = 17
HUMAN = 18
DIM = 19
NCLS = 4


def onehot(idx, k=4):
    out = np.zeros((len(idx), k), dtype=np.float64)
    out[np.arange(len(idx)), idx] = 1.0
    return out


def make(n, axis="id", seed=0, occ_p=0.0, cue_noise=0.0):
    r = np.random.default_rng(seed)
    task = r.integers(0, 2, n)
    shape = r.integers(0, 4, n)
    color = r.integers(0, 4, n)
    y = np.where(task == 0, shape, color)
    # training only: hide the task-relevant cue for a fraction of samples,
    # so the perfectly-predictive background becomes an easier shortcut
    if occ_p > 0:
        occ = r.random(n) < occ_p
        shape = np.where(occ & (task == 0), -1, shape)
        color = np.where(occ & (task == 1), -1, color)
    # training only: corrupt the task-relevant cue so the (easier) background
    # shortcut is preferred by ERM; test cues stay clean
    if cue_noise > 0:
        bad = r.random(n) < cue_noise
        shape = np.where(bad & (task == 0), r.integers(0, 4, n), shape)
        color = np.where(bad & (task == 1), r.integers(0, 4, n), color)

    if axis == "id":
        bg = np.where(r.random(n) < 0.95, y, r.integers(0, 4, n))
        distractor = r.poisson(0.5, n)
        pos = r.normal(0.0, 0.5, (n, 2))
        light = r.normal(0.0, 0.5, n)
        human = r.integers(0, 2, n) * (r.random(n) < 0.05)
    elif axis == "background":            # break spurious correlation
        bg = r.integers(0, 4, n)
        distractor = r.poisson(0.5, n)
        pos = r.normal(0.0, 0.5, (n, 2))
        light = r.normal(0.0, 0.5, n)
        human = r.integers(0, 2, n) * (r.random(n) < 0.05)
    elif axis == "background_anti":       # actively anti-correlated
        bg = (y + 1) % 4
        distractor = r.poisson(0.5, n)
        pos = r.normal(0.0, 0.5, (n, 2))
        light = r.normal(0.0, 0.5, n)
        human = r.integers(0, 2, n) * (r.random(n) < 0.05)
    elif axis == "position":
        bg = np.where(r.random(n) < 0.95, y, r.integers(0, 4, n))
        distractor = r.poisson(0.5, n)
        pos = r.normal(2.5, 0.5, (n, 2))
        light = r.normal(0.0, 0.5, n)
        human = r.integers(0, 2, n) * (r.random(n) < 0.05)
    elif axis == "distractor":
        bg = np.where(r.random(n) < 0.95, y, r.integers(0, 4, n))
        distractor = r.poisson(3.0, n)
        pos = r.normal(0.0, 0.5, (n, 2))
        light = r.normal(0.0, 0.5, n)
        human = r.integers(0, 2, n) * (r.random(n) < 0.05)
    elif axis == "lighting":
        bg = np.where(r.random(n) < 0.95, y, r.integers(0, 4, n))
        distractor = r.poisson(0.5, n)
        pos = r.normal(0.0, 0.5, (n, 2))
        light = r.normal(3.0, 1.0, n)
        human = r.integers(0, 2, n) * (r.random(n) < 0.05)
    elif axis == "unseen_instance":       # compositional split, unseen shape-colour pairs
        keep = ((shape + color) % 2 == 0)
        shape, color = shape[keep], color[keep]
        n = len(shape)
        task = task[keep]
        y = y[keep]
        bg = np.where(r.random(n) < 0.95, y, r.integers(0, 4, n))
        distractor = r.poisson(0.5, n)
        pos = r.normal(0.0, 0.5, (n, 2))
        light = r.normal(0.0, 0.5, n)
        human = r.integers(0, 2, n) * (r.random(n) < 0.05)
    elif axis == "human":                 # human hand + partial occlusion of the cue
        bg = np.where(r.random(n) < 0.95, y, r.integers(0, 4, n))
        distractor = r.poisson(0.5, n)
        pos = r.normal(0.0, 0.5, (n, 2))
        light = r.normal(0.0, 0.5, n)
        human = r.integers(0, 2, n) * (r.random(n) < 0.5)
        occ = r.random(n) < 0.2
        shape = np.where(occ, -1, shape)
        color = np.where(occ, -1, color)
    else:
        raise ValueError(axis)

    x = np.zeros((n, DIM))
    x[np.arange(n), task] = 1.0
    for j, idx in enumerate([shape, color, bg]):
        valid = idx >= 0
        block = np.where(valid[:, None], onehot(np.clip(idx, 0, 3)), 0.0)
        x[:, [SHAPE, COLOR, BG][j]] = block
    x[:, DISTRACTOR] = distractor / 3.0
    x[:, POS] = pos
    x[:, LIGHT] = light
    x[:, HUMAN] = human
    return x, y, task


def perturb(x, gate, r):
    """Replace factors selected by the per-sample gate with random values."""
    x2 = x.copy()
    # category groups
    for cols in (SHAPE, COLOR, BG):
        m = gate[:, cols[0]] > 0
        if m.any():
            x2[np.ix_(np.where(m)[0], cols)] = onehot(r.integers(0, 4, m.sum()))
    # continuous / count nuisances
    m = gate[:, DISTRACTOR] > 0
    if m.any():
        x2[m, DISTRACTOR] = r.poisson(1.0, m.sum()) / 3.0
    m = gate[:, POS[0]] > 0
    if m.any():
        x2[m][:, POS] += r.normal(0.0, 1.0, (m.sum(), 2))
    m = gate[:, LIGHT] > 0
    if m.any():
        x2[m, LIGHT] += r.normal(0.0, 1.0, m.sum())
    m = gate[:, HUMAN] > 0
    if m.any():
        x2[m, HUMAN] = r.integers(0, 2, m.sum())
    return x2


def gate_for(x, mode):
    n = len(x)
    g = np.zeros((n, DIM))
    task = x[:, 1].astype(int)  # 0 -> T1, 1 -> T2
    if mode == "erm":
        return g
    if mode == "inv_all":
        cols = SHAPE + COLOR + BG + [DISTRACTOR] + POS + [LIGHT, HUMAN]
        g[:, cols] = 1.0
        return g
    # TCI: remove only task-nuisance cues
    # T1 (move): shape relevant -> keep shape; perturb colour/bg/nuisance
    # T2 (sort): colour relevant -> keep colour; perturb shape/bg/nuisance
    t1 = task == 0
    t2 = task == 1
    g[np.ix_(np.where(t1)[0], COLOR + BG + [DISTRACTOR] + POS + [LIGHT, HUMAN])] = 1.0
    g[np.ix_(np.where(t2)[0], SHAPE + BG + [DISTRACTOR] + POS + [LIGHT, HUMAN])] = 1.0
    return g


class MLP:
    def __init__(self, hidden=64, seed=0):
        r = np.random.default_rng(seed)
        self.W1 = r.normal(0, np.sqrt(2 / DIM), (DIM, hidden))
        self.b1 = np.zeros(hidden)
        self.W2 = r.normal(0, np.sqrt(2 / hidden), (hidden, 8))
        self.b2 = np.zeros(8)

    def forward(self, x):
        h = np.tanh(x @ self.W1 + self.b1)
        return h @ self.W2 + self.b2, h

    def params(self):
        return [self.W1, self.b1, self.W2, self.b2]


def train(mode, steps=6000, bs=512, lr=3e-3, lam=1.0, hidden=64, seed=0):
    xtr, ytr, ttr = make(40000, "id", seed=1 + 10 * SEED, cue_noise=0.5)
    model = MLP(hidden, seed)
    params = model.params()
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    r = np.random.default_rng(seed + 100 + 10 * SEED)
    b1, b2 = 0.9, 0.999
    for step in range(1, steps + 1):
        idx = r.integers(0, len(xtr), bs)
        x, y, t = xtr[idx], ytr[idx], ttr[idx]
        g = gate_for(x, mode)
        xp = perturb(x, g, r) if g.any() else x
        z, h = model.forward(x)
        zp, hp = model.forward(xp)
        # task-specific logits, shape (bs, 4)
        cols = (t[:, None] * NCLS + np.arange(NCLS)[None, :])
        logits = z[np.arange(len(t))[:, None], cols]
        logits_p = zp[np.arange(len(t))[:, None], cols]
        # softmax CE
        mx = logits.max(1, keepdims=True)
        p = np.exp(logits - mx)
        p /= p.sum(1, keepdims=True)
        oh = np.zeros_like(p)
        oh[np.arange(len(t)), y] = 1.0
        loss = -np.log(p[np.arange(len(t)), y] + 1e-12).mean()
        # dL/dlogits expanded to the full (bs, 8) multi-task output
        rows = np.arange(len(t))[:, None]
        dz = np.zeros_like(z)
        dzp = np.zeros_like(zp)
        dz[rows, cols] = (p - oh) / len(t)
        if lam > 0 and g.any():
            diff = (logits - logits_p)
            cons = (diff ** 2).mean()
            loss += lam * cons
            ddiff = (2.0 * lam / diff.size) * diff
            dz[rows, cols] += ddiff
            dzp[rows, cols] -= ddiff
        # backward
        grads = []
        for dzz, hh, xx in ((dz, h, x), (dzp, hp, xp)):
            dW2 = hh.T @ dzz
            db2 = dzz.sum(0)
            dh = (dzz @ model.W2.T) * (1 - hh ** 2)
            dW1 = xx.T @ dh
            db1 = dh.sum(0)
            grads.append([dW1, db1, dW2, db2])
        gsum = [grads[0][i] + grads[1][i] for i in range(4)]
        for i, (p, gr) in enumerate(zip(params, gsum)):
            m[i] = b1 * m[i] + (1 - b1) * gr
            v[i] = b2 * v[i] + (1 - b2) * gr * gr
            mh = m[i] / (1 - b1 ** step)
            vh = v[i] / (1 - b2 ** step)
            p -= lr * mh / (np.sqrt(vh) + 1e-8)
    return model


def acc(model, axis, seed=999):
    x, y, t = make(8000, axis, seed=seed + 10 * SEED)
    z, _ = model.forward(x)
    cols = (t[:, None] * NCLS + np.arange(NCLS)[None, :])
    logits = z[np.arange(len(t))[:, None], cols]
    pred = logits.argmax(1)
    per_task = {}
    for k in (0, 1):
        mask = t == k
        per_task[k] = float((pred[mask] == y[mask]).mean())
    return float((pred == y).mean()), per_task


AXES = ["id", "background", "background_anti", "position", "distractor",
        "lighting", "unseen_instance", "human"]

results = {}
for mode, lam in [("erm", 0.0), ("inv_all", 1.0), ("tci", 1.0)]:
    model = train(mode, lam=lam)
    row = {}
    for axis in AXES:
        a, pt = acc(model, axis)
        row[axis] = {"acc": round(a, 4), "T1": round(pt[0], 4), "T2": round(pt[1], 4)}
    ood = [row[a]["acc"] for a in AXES if a != "id"]
    row["worst_axis"] = round(min(ood), 4)
    row["ood_mean"] = round(float(np.mean(ood)), 4)
    results[mode] = row
    print(mode, json.dumps(row, indent=None))

with open(os.path.join(HERE, f"tci_results_seed{SEED}.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
# compact markdown table for the artifact
print("\n| method | id | background | bg-anti | position | distractor | lighting | unseen | human | worst | ood-mean |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for mode in results:
    r = results[mode]
    vals = [mode] + [f"{r[a]['acc']:.3f}" for a in AXES] + [f"{r['worst_axis']:.3f}", f"{r['ood_mean']:.3f}"]
    print("| " + " | ".join(vals) + " |")
