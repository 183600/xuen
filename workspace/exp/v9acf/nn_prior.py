"""A small neural side-prior and its distribution-shift gate.

The prior predicts which end of the certified bracket [L,U] is closer to
OPT: p_upper near 1 means "probe U-1 first", p_upper near 0 means
"probe L first".  It is trained on the 252-instance corpus.  Because the
gap-stress instances are a different distribution, we also fit a
Gaussian OOD score (Mahalanobis distance) on the training features; the
gate abstains when a test point is outside the 95% training quantile.

The NN is never part of a proof.  In DACS it may only order work; the
dual-end certificate coverage remains mandatory.
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora
from po import heads_tails


def features(inst, L, U):
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    cp = max(q[i] + p[i] for i in range(n))
    load = math.ceil(sum(p) / m)
    edges = sum(len(inst['pred'][i]) for i in range(n))
    elig = sum(len(inst['elig'][i]) for i in range(n)) / (n * m)
    return np.array([
        n / 25.0, m / 6.0, L / 80.0, U / 80.0, (U - L) / 10.0,
        sum(p) / (m * 80.0), max(p) / 20.0, cp / 80.0,
        sum(p) / 80.0, float(np.std(p)) / 10.0,
        edges / (n * n), elig,
        (U - cp) / 10.0, (L - cp) / 10.0,
        (U - load) / 10.0, (L - load) / 10.0,
        n / max(1.0, m), (U - L) / max(1.0, U),
        float(len([x for x in inst['succ'] if x])) / (n * n),
    ], dtype=np.float64)


class MLP:
    def __init__(self, d, hidden=16, seed=0):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, 1 / math.sqrt(d), (d, hidden))
        self.b1 = np.zeros(hidden)
        self.W2 = rng.normal(0, 1 / math.sqrt(hidden), (hidden, 1))
        self.b2 = np.zeros(1)
        self.params = [self.W1, self.b1, self.W2, self.b2]
        self.m = [np.zeros_like(p) for p in self.params]
        self.v = [np.zeros_like(p) for p in self.params]

    def forward(self, x):
        a = np.tanh(x @ self.W1 + self.b1)
        z = (a @ self.W2 + self.b2)[:, 0]
        return z, a

    def predict(self, x):
        z, _ = self.forward(x)
        return 1.0 / (1.0 + np.exp(-z))

    def step(self, x, y, lr=0.02, t=1):
        z, a = self.forward(x)
        p = 1.0 / (1.0 + np.exp(-z))
        dz = (p - y)[:, None] / len(x)
        gW2 = a.T @ dz
        gb2 = dz.sum(0)
        da = dz @ self.W2.T
        dz1 = da * (1 - a * a)
        gW1 = x.T @ dz1
        gb1 = dz1.sum(0)
        for i, (par, g) in enumerate(zip(self.params,
                                         [gW1, gb1, gW2, gb2])):
            self.m[i] = 0.9 * self.m[i] + 0.1 * g
            self.v[i] = 0.999 * self.v[i] + 0.001 * g * g
            mh = self.m[i] / (1 - 0.9 ** t)
            vh = self.v[i] / (1 - 0.999 ** t)
            par -= lr * mh / (np.sqrt(vh) + 1e-8)


def train_mlp(X, y, seed=0, epochs=600):
    m = MLP(X.shape[1], seed=seed)
    rng = np.random.default_rng(seed)
    for ep in range(epochs):
        idx = rng.permutation(len(X))
        for s in range(0, len(idx), 64):
            b = idx[s:s + 64]
            m.step(X[b], y[b], lr=0.02, t=ep * 10 + s // 64 + 1)
    return m


class NeuralPrior:
    def __init__(self, X, y, seed=123):
        self.mu = X.mean(0)
        self.sd = X.std(0) + 1e-9
        Xn = (X - self.mu) / self.sd
        self.model = train_mlp(Xn, y, seed=seed)
        cov = np.cov(Xn, rowvar=False) + np.eye(Xn.shape[1]) * 1e-6
        self.inv = np.linalg.pinv(cov)
        d = np.sqrt(np.einsum('ij,jk,ik->i', Xn - self.mu / self.sd,
                              self.inv, Xn - self.mu / self.sd))
        # Xn is already centered; recompute cleanly
        d = np.sqrt(np.einsum('ij,jk,ik->i', Xn, self.inv, Xn))
        self.train_dist = d
        self.threshold = float(np.quantile(d, 0.95))

    def __call__(self, inst, L, U):
        x = (features(inst, L, U) - self.mu) / self.sd
        p = float(self.model.predict(x[None, :])[0])
        dist = float(np.sqrt(x @ self.inv @ x))
        return p, bool(dist > self.threshold)


def source_data():
    init = {}
    for r in json.load(open('exp/v8u/bench_icf_lower-first.json')):
        init[(r['name'], r['idx'])] = (r['lb0'], r['ub0'], r['known'])
    rows = []
    for corpus, name, idx, inst, known in corpora():
        L, U, opt = init[(name, idx)]
        rows.append(dict(corpus=corpus, name=name, idx=idx, inst=inst,
                         L=L, U=U, opt=opt))
    X = np.array([features(r['inst'], r['L'], r['U']) for r in rows])
    y = np.array([1.0 if (r['opt'] - r['L']) > (r['U'] - r['opt'])
                  else 0.0 for r in rows])
    return rows, X, y


def gap_data():
    rows = []
    for d in json.load(open('exp/v10b/gap_stress.json')):
        rows.append(dict(name='gap%d' % d['idx'], idx=d['idx'],
                         inst=d['inst'], L=d['lb0'], U=d['ub0'],
                         opt=d['opt']))
    X = np.array([features(r['inst'], r['L'], r['U']) for r in rows])
    y = np.array([1.0 if (r['opt'] - r['L']) > (r['U'] - r['opt'])
                  else 0.0 for r in rows])
    return rows, X, y


def evaluate():
    rows, X, y = source_data()
    grows, Xg, yg = gap_data()
    names = sorted(set((r['name'], r['idx']) for r in rows))
    rng = np.random.default_rng(5)
    rng.shuffle(names)
    fold = {n: i % 5 for i, n in enumerate(names)}
    cv = []
    for f in range(5):
        idx = np.array([fold[(r['name'], r['idx'])] != f for r in rows])
        prior = NeuralPrior(X[idx], y[idx], seed=f)
        p = prior.model.predict((X[~idx] - prior.mu) / prior.sd)
        cv.append(float(np.mean((p > 0.5) == (y[~idx] > 0.5))))
    prior = NeuralPrior(X, y)
    pg = []
    for r in grows:
        p, ood = prior(r['inst'], r['L'], r['U'])
        xx = (features(r['inst'], r['L'], r['U']) - prior.mu) / prior.sd
        dist = float(np.sqrt(xx @ prior.inv @ xx))
        pg.append(dict(name=r['name'], opt=r['opt'], L=r['L'], U=r['U'],
                       p_upper=p, ood=ood, ood_dist=dist))
    out = dict(cv_accuracy=cv, cv_mean=float(np.mean(cv)),
               train_n=len(rows), gap_n=len(grows),
               ood_threshold=prior.threshold,
               gap_ood=sum(x['ood'] for x in pg),
               gap_side_accuracy=float(np.mean(
                   [(x['p_upper'] > 0.5) == (x['opt'] - x['L']
                                             > x['U'] - x['opt'])
                    for x in pg])),
               gap=pg)
    with open('exp/v9acf/nn_prior.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('cv', cv, 'mean', round(out['cv_mean'], 4))
    print('ood threshold', round(out['ood_threshold'], 3),
          'gap OOD', out['gap_ood'], '/', len(pg))
    print('gap side acc', round(out['gap_side_accuracy'], 4))
    for x in pg:
        print(x['name'], 'p', round(x['p_upper'], 3),
              'ood', x['ood'], round(x['ood_dist'], 1))
    return prior, out


if __name__ == '__main__':
    evaluate()
