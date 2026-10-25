"""v8.10 PIVOT-1: learned singleton-backdoor pruning around PACT.

A pivot is a single job i such that Search(h, {i}) returns NO (or YES).
PIVOT-1-SEARCH tries a learned ranking of jobs, then falls back to the full
PACT search, so every accepted certificate is still a PACT certificate.
"""
import json
import math
import sys
import time

sys.path[:0] = ['exp/v8q', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np
from scipy.optimize import minimize

from sdecc import SDLP
from po import heads_tails
from pact import pact_decide as _pact_decide, _elig_aware

FEATURE_NAMES = [
    'p', 'q', 'est', 'slack', 'width', 'succ', 'pred', 'elig',
    'frac', 'ntimes', 'peak', 'ent', 'spread', 'mean_t', 'index',
    'index_n', 'n', 'm', 'load_m', 'density', 'use_elig', 'mean_width',
    'max_width', 'sd_width', 'cp', 'h',
]
PRIOR_ORDER = [3, 4, 6, 7, 8, 9, 10, 11, 5, 12, 13, 14, 0, 1, 2]


def prior_order(n):
    order = [i for i in PRIOR_ORDER if i < n]
    order += [i for i in range(n) if i not in order]
    return order


def root_features(inst, h, lp=None, res=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    widths = [max(0, h - q[i] - p[i] - est[i] + 1) for i in range(n)]
    edges = sum(len(inst['succ'][i]) for i in range(n))
    elig = [len(set(inst['elig'][i])) for i in range(n)]
    use_elig = any(e < m for e in elig)
    if lp is None:
        lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=use_elig)
    if res is None:
        res = lp.solve()
    if res.status != 0:
        return None, lp, res
    per = {}
    for c, key in enumerate(lp.cols):
        i, t = key[0], key[-1]
        d = per.setdefault(i, {})
        d[t] = d.get(t, 0.0) + res.x[c]
    instfeat = [n, m, sum(p) / max(1, m), edges / max(1, n * n),
                float(use_elig), sum(widths) / n, max(widths),
                float(np.std(widths)),
                max(est[i] + p[i] + q[i] for i in range(n)), h]
    X = []
    for i in range(n):
        d = per.get(i, {})
        times = sorted(d)
        vals = np.array([d[t] for t in times])
        mass = vals.sum()
        frac = vals[(vals > 1e-7) & (vals < 1 - 1e-7)].sum()
        peak = vals.max() if len(vals) else 0.0
        ent = -sum(v * math.log(v) for v in vals if v > 1e-12)
        mean_t = sum(t * v for t, v in zip(times, vals)) / max(mass, 1e-12)
        var_t = sum(v * (t - mean_t) ** 2
                    for t, v in zip(times, vals)) / max(mass, 1e-12)
        jf = [p[i], q[i], est[i], h - q[i] - p[i] - est[i], widths[i],
              len(inst['succ'][i]), len(inst['pred'][i]), elig[i],
              frac, len(vals), peak, ent, math.sqrt(var_t), mean_t,
              i, i / max(1, n - 1)]
        X.append(jf + instfeat)
    return np.asarray(X, dtype=float), lp, res


class PivotRanker:
    def __init__(self, names, mean, scale, weights):
        self.names = list(names)
        self.mean = np.asarray(mean, dtype=float)
        self.scale = np.asarray(scale, dtype=float)
        self.weights = np.asarray(weights, dtype=float)

    @classmethod
    def fit_groups(cls, groups_x, groups_y, lam=1.0):
        X = np.vstack(groups_x)
        y = np.concatenate(groups_y)
        mean = X.mean(0)
        scale = X.std(0)
        scale[scale < 1e-9] = 1.0
        Z = np.hstack([np.ones((len(X), 1)), (X - mean) / scale])

        def obj(w):
            s = Z.dot(w)
            loss = np.logaddexp(0, s).sum() - y.dot(s)
            loss += 0.5 * lam * w[1:].dot(w[1:])
            g = Z.T.dot(1 / (1 + np.exp(-s)) - y)
            g[1:] += lam * w[1:]
            return loss, g

        r = minimize(obj, np.zeros(Z.shape[1]), jac=True,
                     method='L-BFGS-B', options=dict(maxiter=500))
        return cls(FEATURE_NAMES, mean.tolist(), scale.tolist(),
                   r.x.tolist())

    def scores(self, X):
        return self.weights[0] + ((X - self.mean) / self.scale).dot(
            self.weights[1:])

    def order(self, X, inst=None, h=None):
        return [int(i) for i in np.argsort(-self.scores(X))]

    def to_json(self):
        return dict(names=self.names, mean=self.mean.tolist(),
                    scale=self.scale.tolist(),
                    weights=self.weights.tolist())

    @classmethod
    def from_json(cls, path):
        d = json.load(open(path))
        return cls(d['names'], d['mean'], d['scale'], d['weights'])


def _merge_stats(attempts, root_lp_solves, fallback=None):
    nodes = 1 + sum(a['nodes'] - 1 for a in attempts)
    leaves = sum(a['leaves'] for a in attempts)
    lp = root_lp_solves + sum(a['lp'] for a in attempts)
    cert = sum(a['cert'] for a in attempts)
    depth = max([a['depth'] for a in attempts] or [0])
    if fallback is not None:
        nodes += fallback['nodes'] - 1
        leaves += fallback['leaves']
        lp += fallback['lp_solves']
        cert += fallback['cert_lp']
        depth = max(depth, fallback['depth'])
    return dict(nodes=nodes, leaves=leaves, depth=depth,
                lp_solves=lp, cert_lp=cert)


def pivot_decide(inst, h, depthcap=None, nodecap=None, policy=None,
                 seed=0, ranker=None, max_attempts=4, fallback=True,
                 root_lp=None, root_res=None):
    t0 = time.time()
    X, lp, root_res = root_features(inst, h, root_lp, root_res)
    if X is None:
        r = _pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                         policy=policy, seed=seed, root_lp=lp,
                         root_res=root_res)
        r = dict(r)
        r['pivot'] = dict(order=[], attempts=[], success=None,
                          fallback=True, max_attempts=max_attempts)
        return r
    order = (ranker.order(X, inst, h) if ranker is not None
             else prior_order(inst['n']))
    attempts = []
    for i in order[:max_attempts]:
        r = _pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                         policy=policy, seed=seed, root_lp=lp,
                         root_res=root_res, branch_jobs=[i])
        attempts.append(dict(job=int(i), verdict=r['verdict'],
                             nodes=r['nodes'], leaves=r['leaves'],
                             depth=r['depth'], lp=r['lp_solves'],
                             cert=r['cert_lp']))
        if r['verdict'] is not None:
            out = dict(r)
            out.update(_merge_stats(attempts, 1))
            out['pivot'] = dict(order=[int(x) for x in order],
                                attempts=attempts, success=int(i),
                                fallback=False,
                                max_attempts=max_attempts)
            out['t'] = round(time.time() - t0, 5)
            return out
    if not fallback:
        out = dict(verdict=None, proof=None, schedule=None, machine=None,
                   unknown=True, holes=len(attempts), branch_jobs=[],
                   insufficient=True, root_reused=len(attempts),
                   yes_depth=None, **_merge_stats(attempts, 1))
        out['pivot'] = dict(order=[int(x) for x in order],
                            attempts=attempts, success=None,
                            fallback=False,
                            max_attempts=max_attempts)
        out['t'] = round(time.time() - t0, 5)
        return out
    r = _pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                     policy=policy, seed=seed, root_lp=lp,
                     root_res=root_res)
    out = dict(r)
    out.update(_merge_stats(attempts, 1, dict(
        nodes=r['nodes'], leaves=r['leaves'], depth=r['depth'],
        lp_solves=r['lp_solves'], cert_lp=r['cert_lp'])))
    out['pivot'] = dict(order=[int(x) for x in order],
                        attempts=attempts, success=None, fallback=True,
                        max_attempts=max_attempts)
    out['t'] = round(time.time() - t0, 5)
    return out
