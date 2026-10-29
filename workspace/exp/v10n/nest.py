"""NEST-PACT: neural-energy scalable tree search over a certified frontier.

NEST keeps BAM's sound outer bracket and memory-bounded frontier.  The
only new trusted-state changes are:

  * a *balanced* split rule (BAL) that chooses the split point minimizing
    the larger child's fractional mass;
  * a small neural energy critic that predicts, for an open leaf, the
    probability of a cheap NO closure and the immediate LP energy;
  * an optional LP-energy budget.  The critic may only order leaves; the
    certificate kernel is unchanged.

The critic is trained from logged probe events (features, LP cost,
verdict).  It never sees a proof and cannot remove a leaf.
"""
from __future__ import annotations

import json
import math
import sys
import time

import numpy as np

sys.path[:0] = ['exp/v10n', 'exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from bam import BAM, run_bam
from po import heads_tails


def static_features(inst):
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    cp = max(q[i] + p[i] for i in range(n))
    load = math.ceil(sum(p) / m)
    edges = sum(len(inst['succ'][i]) for i in range(n))
    elig = sum(len(inst['elig'][i]) for i in range(n)) / (n * m)
    return np.array([
        n / 25.0, m / 6.0,
        sum(p) / (m * 80.0), max(p) / 20.0, float(np.mean(p)) / 10.0,
        float(np.std(p)) / 10.0, cp / 80.0, load / 80.0,
        edges / (n * n), elig, n / max(1.0, m),
    ], dtype=np.float64)


def leaf_features(inst, f, U, L, nopen, W, probes, splits, peak):
    n = inst['n']
    widths = [int(f.hi[i]) - int(f.lo[i]) for i in range(n)]
    width = sum(widths)
    maxw = max(widths) if widths else 0
    minw = min(widths) if widths else 0
    sf = static_features(inst)
    return np.concatenate([sf, np.array([
        U / 80.0, (U - L) / 10.0, f.L / 80.0,
        (f.L - L) / 10.0, (U - f.L) / 10.0,
        f.depth / 10.0, width / (n * 20.0), maxw / 20.0, minw / 10.0,
        nopen / max(1.0, W), probes / 100.0, splits / 100.0,
        peak / max(1.0, W),
    ], dtype=np.float64)])


class TinyMLP:
    """One hidden layer, two heads: log1p(LP cost) and P(cheap NO)."""

    def __init__(self, d, hidden=24, seed=0):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, 1 / math.sqrt(d), (d, hidden))
        self.b1 = np.zeros(hidden)
        self.W2 = rng.normal(0, 1 / math.sqrt(hidden), (hidden, 2))
        self.b2 = np.zeros(2)
        self.params = [self.W1, self.b1, self.W2, self.b2]
        self.m = [np.zeros_like(p) for p in self.params]
        self.v = [np.zeros_like(p) for p in self.params]

    def forward(self, X):
        a = np.tanh(X @ self.W1 + self.b1)
        out = a @ self.W2 + self.b2
        return out, a

    def predict(self, X):
        out, _ = self.forward(X)
        cost = np.expm1(np.maximum(out[:, 0], 0.0))
        close = 1.0 / (1.0 + np.exp(-np.clip(out[:, 1], -30, 30)))
        return cost, close

    def step(self, X, ycost, yclose, lr=0.02, t=1):
        out, a = self.forward(X)
        p = 1.0 / (1.0 + np.exp(-np.clip(out[:, 1], -30, 30)))
        d0 = (out[:, 0] - ycost)[:, None] / len(X)
        d1 = (p - yclose)[:, None] / len(X)
        dout = np.concatenate([d0, d1], axis=1)
        gW2 = a.T @ dout
        gb2 = dout.sum(0)
        da = dout @ self.W2.T
        dz1 = da * (1 - a * a)
        gW1 = X.T @ dz1
        gb1 = dz1.sum(0)
        for i, (par, g) in enumerate(zip(self.params,
                                         [gW1, gb1, gW2, gb2])):
            self.m[i] = 0.9 * self.m[i] + 0.1 * g
            self.v[i] = 0.999 * self.v[i] + 0.001 * g * g
            mh = self.m[i] / (1 - 0.9 ** t)
            vh = self.v[i] / (1 - 0.999 ** t)
            par -= lr * mh / (np.sqrt(vh) + 1e-8)


class EnergyCritic:
    def __init__(self, X, ycost, yclose, seed=0, hidden=24, epochs=400):
        self.mu = X.mean(0)
        self.sd = X.std(0) + 1e-9
        Xn = (X - self.mu) / self.sd
        self.model = TinyMLP(X.shape[1], hidden=hidden, seed=seed)
        rng = np.random.default_rng(seed)
        t = 1
        for ep in range(epochs):
            idx = rng.permutation(len(Xn))
            for s in range(0, len(idx), 64):
                b = idx[s:s + 64]
                self.model.step(Xn[b], ycost[b], yclose[b], lr=0.02, t=t)
                t += 1

    def predict(self, X):
        Xn = (X - self.mu) / self.sd
        return self.model.predict(Xn)

    def score(self, X, mode='gain', L=None):
        cost, close = self.predict(X)
        if mode == 'cost':
            return -cost
        if mode == 'close':
            return close
        # expected cheap closure per unit energy
        gain = close / (cost + 1.0)
        if mode == 'gain' and L is not None:
            # mild preference for leaves that can lift the global lower bound
            gain = gain - 0.02 * np.asarray(L, dtype=float)
        return gain


class NEST(BAM):
    def __init__(self, inst, critic=None, selector='default',
                 split_mode='balance', max_energy=None, trace=False,
                 **kw):
        super().__init__(inst, **kw)
        self.critic = critic
        self.selector = selector
        self.split_mode = split_mode
        self.max_energy = max_energy
        self.trace = [] if trace else None
        self._last_feat = None
        self._static = static_features(inst)

    def energy(self):
        return int(self.stats['lp'] + self.stats['cert_lp']
                   + self.stats['pin_lp'])

    def _leaf_feat(self, f, openf):
        return leaf_features(self.inst, f, self.U, self.L, len(openf),
                             self.W, self.stats['probes'],
                             self.stats['splits'],
                             self.stats['peak_leaves'])

    def _select_leaf(self, openf):
        if self.critic is None or self.selector == 'default':
            f = super()._select_leaf(openf)
            self._last_feat = self._leaf_feat(f, openf)
            return f
        if self.selector == 'neural_critical':
            Lmin = min(f.L for f in openf)
            cands = [f for f in openf if f.L == Lmin]
            X = np.array([self._leaf_feat(f, cands) for f in cands])
            scores = self.critic.score(X, mode='cost', L=[f.L for f in cands])
            best = int(np.argmax(scores))
            f = cands[best]
            self._last_feat = X[best]
            return f
        X = np.array([self._leaf_feat(f, openf) for f in openf])
        mode = self.selector.replace('neural_', '')
        Ls = [f.L for f in openf]
        scores = self.critic.score(X, mode=mode, L=Ls)
        best = int(np.argmax(scores))
        f = openf[best]
        self._last_feat = X[best]
        return f

    def _probe(self, f):
        if self.max_energy is not None and self.energy() >= self.max_energy:
            return 'unknown', None
        before = self.energy()
        feat = self._last_feat
        status, payload = super()._probe(f)
        after = self.energy()
        if self.trace is not None and feat is not None:
            self.trace.append(dict(
                x=[float(v) for v in feat], cost=int(after - before),
                status=status, h=int(f.L), U=int(self.U), L=int(self.L),
                probes=int(self.stats['probes']),
                splits=int(self.stats['splits'])))
        return status, payload

    def _choose_split(self, lp, z, a, b):
        if self.split_mode == 'default':
            return super()._choose_split(lp, z, a, b)
        inst = self.inst
        n = inst['n']
        q = getattr(lp, 'q', [0] * n)
        cand = []
        for i in range(n):
            times = list(range(a[i], b[i] + 1))
            if len(times) <= 1:
                continue
            mass = 0.0
            frac = 0.0
            dist = []
            for t in times:
                v = 0.0
                for c, key in enumerate(lp.cols):
                    if key[0] == i and key[-1] == t:
                        v += float(z[c])
                if v > 1e-12:
                    dist.append((t, v))
                    mass += v
                    if 1e-7 < v < 1 - 1e-7:
                        frac += v
            if len(dist) <= 1 or mass <= 1e-12:
                continue
            cand.append((i, dist, mass, frac))
        if not cand:
            i = max(range(n), key=lambda j: (b[j] - a[j], q[j], -j))
            if b[i] <= a[i]:
                return None, None
            return i, (a[i] + b[i]) // 2

        def mid_of(dist):
            total = sum(v for _, v in dist)
            acc = 0.0
            mid = dist[0][0]
            for t, v in dist:
                acc += v
                if acc >= 0.5 * total:
                    mid = t
                    break
            ts = [t for t, _ in dist]
            if not any(t > mid for t in ts) or not any(t <= mid for t in ts):
                mid = ts[len(ts) // 2 - 1]
            if not any(t > mid for t in ts) or not any(t <= mid for t in ts):
                return None
            return mid

        def key(c):
            i, dist, mass, frac = c
            mid = mid_of(dist)
            if mid is None:
                return (-1,)
            lm = sum(v for t, v in dist if t <= mid)
            rm = mass - lm
            bal = max(lm, rm) / max(mass, 1e-12)
            return (-bal, mass, frac, q[i], len(dist), -i)

        cand.sort(key=key, reverse=True)
        i, dist, mass, frac = cand[0]
        mid = mid_of(dist)
        if mid is None:
            return None, None
        return i, mid


def run_nest(inst, known, name, idx, critic=None, selector='default',
             split_mode='balance', max_energy=None, **kw):
    co = NEST(inst, critic=critic, selector=selector,
              split_mode=split_mode, max_energy=max_energy, **kw)
    co.name, co.idx, co.known = name, idx, known
    r = co.run()
    r.update(name=name, idx=idx, known=known,
             selector=selector, split_mode=split_mode,
             max_energy=max_energy,
             energy=co.energy())
    return r


def collect(inst, known, name, idx, split_mode='balance', **kw):
    co = NEST(inst, critic=None, selector='default', split_mode=split_mode,
              trace=True, **kw)
    co.name, co.idx, co.known = name, idx, known
    r = co.run()
    return r, co.trace


def train_critic(events, seed=0, epochs=400, hidden=24):
    X = np.array([e['x'] for e in events], dtype=np.float64)
    ycost = np.array([math.log1p(max(0, e['cost'])) for e in events])
    yclose = np.array([1.0 if e['status'] == 'no' else 0.0
                       for e in events])
    return EnergyCritic(X, ycost, yclose, seed=seed, epochs=epochs,
                        hidden=hidden)
