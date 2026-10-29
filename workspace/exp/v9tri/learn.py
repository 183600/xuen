"""A small learned pivot predictor for TRIAD.

The predictor is deliberately modest: ridge regression on cheap instance
features.  It predicts the largest NO horizon OPT-1, i.e. the boundary
between the NO and YES regions.  It is never part of the certificate; a
wrong prediction changes only the next probe, not the soundness of the
bracket.  We use leave-one-out for the 252-case corpus and a fixed
train/test split for the synthetic large-gap experiments.
"""
from __future__ import annotations

import sys
import numpy as np

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from po import heads_tails
from apex import bound_lb


def features(inst):
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    cp = max(est[i] + p[i] + q[i] for i in range(n))
    bl = bound_lb(inst)
    edges = sum(len(x) for x in inst['pred'])
    elig = [len(set(e)) for e in inst['elig']]
    ps = np.asarray(p, dtype=float)
    return [
        float(n), float(m), float(ps.sum()), float(ps.max()),
        float(ps.mean()), float(ps.std()), float(cp), float(bl),
        float(ps.sum() / m), float(edges / max(1, n)),
        float(max(elig)), float(min(elig)), float(np.mean(elig)),
        float(inst.get('pmax', ps.max())),
    ]


def matrix(insts):
    return np.asarray([features(x) for x in insts], dtype=float)


class Ridge:
    def __init__(self, lam=0.1):
        self.lam = float(lam)
        self.mu = None
        self.sd = None
        self.w = None

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        self.mu = X.mean(0)
        self.sd = X.std(0)
        self.sd[self.sd < 1e-9] = 1.0
        Z = (X - self.mu) / self.sd
        A = np.c_[np.ones(len(Z)), Z]
        reg = self.lam * np.eye(A.shape[1])
        reg[0, 0] = 0.0
        self.w = np.linalg.solve(A.T @ A + reg, A.T @ y)
        return self

    def predict(self, X):
        X = np.atleast_2d(np.asarray(X, dtype=float))
        Z = (X - self.mu) / self.sd
        return np.c_[np.ones(len(Z)), Z] @ self.w


def _loo_mae(X, y, lam):
    pred = np.empty(len(y))
    for i in range(len(y)):
        mask = np.ones(len(y), dtype=bool)
        mask[i] = False
        r = Ridge(lam).fit(X[mask], y[mask])
        pred[i] = r.predict(X[i:i + 1])[0]
    return float(np.abs(pred - y).mean()), pred


def choose_lambda(X, y, grid=(0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0)):
    best = None
    for lam in grid:
        mae, _ = _loo_mae(X, y, lam)
        if best is None or mae < best[0]:
            best = (mae, lam)
    return best


def loo_predictions(rows, lam=None):
    """rows: (inst, target).  Returns (predictions, mae, chosen lambda)."""
    X = matrix([r[0] for r in rows])
    y = np.asarray([r[1] for r in rows], dtype=float)
    if lam is None:
        mae, lam = choose_lambda(X, y)
    else:
        mae, _ = _loo_mae(X, y, lam)
    pred = np.empty(len(y))
    for i in range(len(y)):
        mask = np.ones(len(y), dtype=bool)
        mask[i] = False
        r = Ridge(lam).fit(X[mask], y[mask])
        pred[i] = r.predict(X[i:i + 1])[0]
    return pred, mae, lam


def train_predictor(rows, lam=None):
    X = matrix([r[0] for r in rows])
    y = np.asarray([r[1] for r in rows], dtype=float)
    if lam is None:
        _, lam = choose_lambda(X, y)
    return Ridge(lam).fit(X, y), lam


def predict_row(model, inst):
    return float(model.predict(matrix([inst]))[0])


def error_stats(pred, y):
    pred = np.asarray(pred, dtype=float)
    y = np.asarray(y, dtype=float)
    return dict(
        mae=round(float(np.abs(pred - y).mean()), 4),
        within1=round(float(np.mean(np.abs(pred - y) <= 1)), 4),
        within2=round(float(np.mean(np.abs(pred - y) <= 2)), 4),
        exact=round(float(np.mean(np.round(pred) == y)), 4),
        maxerr=round(float(np.abs(pred - y).max()), 4),
    )
