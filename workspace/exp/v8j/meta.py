"""Learned verdict-aware branch policy for PRISM.

The HPO sweep shows a real trade-off: a low split quantile (0.25) is
better on NO probes, while 0.5 is better on YES probes.  This module
learns a probe classifier from cheap root-LP/instance features and uses
its prediction only to choose between two sound branch policies:

    predicted NO  -> split 0.25
    predicted YES -> split 0.50

The classifier never changes a verdict, a certificate or a schedule.  A
wrong prediction only changes the order/size of the proof search, and
every leaf is still replayed by IntervalBranchProof.audit_rdf().

Evaluation is leave-one-instance-out over the 105 probes visited by
PRISM on the 252-instance corpus (58 NO, 47 YES).
"""
import json
import sys
import math

sys.path[:0] = ['exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

import numpy as np
from scipy.optimize import minimize

from tune import load_probes
from prism import interval_branch_decide
from sdecc import SDLP
from po import heads_tails


POL_NO = dict(heur='frac', split=0.25, side='left', closure=True)
POL_YES = dict(heur='frac', split=0.5, side='left', closure=True)
POL_BASE = dict(heur='frac', split=0.5, side='left', closure=True)


def features(inst, h):
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    lo = list(est)
    hi = [h - q[i] - p[i] for i in range(n)]
    widths = [hi[i] - lo[i] + 1 for i in range(n)]
    edges = sum(len(inst['succ'][i]) for i in range(n))
    elig = sum(1 for i in range(n) if len(set(inst['elig'][i])) < m)
    load = sum(p)
    cp = max(est[i] + p[i] + q[i] for i in range(n))
    x = [n, m, np.mean(p), np.max(p), np.std(p),
         np.mean(q), np.max(q), edges, edges / max(1.0, n * n),
         elig / n, h, cp, load / max(1.0, m), np.mean(widths),
         np.max(widths), np.std(widths)]
    # root LP fractionality features
    try:
        lp = SDLP(inst, h, est=est, q=q, use_dom=True,
                  elig_aware=elig > 0)
        res = lp.solve()
        if res.status == 2:
            x += [1.0, 0.0, 0.0, 0.0, 0.0]
        elif res.status == 0:
            z = res.x
            frac_cols = 0
            frac_mass = 0.0
            frac_jobs = set()
            for c, key in enumerate(lp.cols):
                if 1e-7 < z[c] < 1 - 1e-7:
                    frac_cols += 1
                    frac_mass += min(z[c], 1 - z[c])
                    frac_jobs.add(key[0])
            x += [0.0, frac_cols / max(1, lp.N),
                  frac_mass / max(1, n), len(frac_jobs) / n,
                  1.0 if not frac_cols else 0.0]
        else:
            x += [0.0, 0.0, 0.0, 0.0, 0.0]
    except Exception:
        x += [0.0, 0.0, 0.0, 0.0, 0.0]
    return np.asarray(x, dtype=float)


def standardize(X, mu=None, sd=None):
    if mu is None:
        mu = X.mean(axis=0)
        sd = X.std(axis=0)
        sd[sd < 1e-9] = 1.0
    return (X - mu) / sd, mu, sd


def fit_logistic(X, y, lam=1.0):
    Z = np.hstack([np.ones((len(X), 1)), X])

    def obj(w):
        s = Z.dot(w)
        loss = np.logaddexp(0.0, s).sum() - y.dot(s)
        loss += 0.5 * lam * w[1:].dot(w[1:])
        g = Z.T.dot(1.0 / (1.0 + np.exp(-s)) - y)
        g[1:] += lam * w[1:]
        return loss, g

    r = minimize(obj, np.zeros(Z.shape[1]), jac=True, method='L-BFGS-B',
                 options=dict(maxiter=500))
    return r.x


def predict_logistic(w, x):
    s = w[0] + x.dot(w[1:])
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, s))))


def loo(probes, X, y, policy_no=POL_NO, policy_yes=POL_YES,
        threshold=0.5, lam=1.0, group=True):
    uids = sorted(set(p['uid'] for p in probes))
    pred = {}
    prob = {}
    for uid in uids:
        test = [j for j, p in enumerate(probes) if p['uid'] == uid]
        train = [j for j, p in enumerate(probes) if p['uid'] != uid]
        Xtr, mu, sd = standardize(X[train])
        w = fit_logistic(Xtr, y[train], lam=lam)
        for j in test:
            z, _, _ = standardize(X[j:j + 1], mu, sd)
            pr = predict_logistic(w, z[0])
            prob[j] = pr
            pred[j] = 1 if pr >= threshold else 0
    # costs
    rows = []
    for j, p in enumerate(probes):
        pol = policy_no if pred[j] else policy_yes
        r = interval_branch_decide(p['inst'], p['h'], nodecap=96,
                                   depthcap=24, policy=pol)
        rows.append(dict(uid=p['uid'], true=p['v'], prob=prob[j],
                         pred='NO' if pred[j] else 'YES',
                         nodes=r['nodes'], cert=r['cert_lp'],
                         verdict=r['verdict']))
    return rows


def fixed_cost(probes, policy):
    out = []
    for p in probes:
        r = interval_branch_decide(p['inst'], p['h'], nodecap=96,
                                   depthcap=24, policy=policy)
        out.append((r['nodes'], r['cert_lp']))
    return out


def summarize(rows, name):
    n = len(rows)
    acc = sum((r['true'] == 'NO') == (r['pred'] == 'NO')
              for r in rows) / n
    tp = sum(r['true'] == 'NO' and r['pred'] == 'NO' for r in rows)
    fp = sum(r['true'] == 'YES' and r['pred'] == 'NO' for r in rows)
    fn = sum(r['true'] == 'NO' and r['pred'] == 'YES' for r in rows)
    return dict(name=name, n=n, acc=round(acc, 4),
                tp=tp, fp=fp, fn=fn,
                nodes=sum(r['nodes'] for r in rows),
                cert=sum(r['cert'] for r in rows),
                unknown=sum(r['verdict'] is None for r in rows))


if __name__ == '__main__':
    probes = load_probes()
    X = np.vstack([features(p['inst'], p['h']) for p in probes])
    y = np.asarray([1.0 if p['v'] == 'NO' else 0.0 for p in probes])
    Xs, _, _ = standardize(X)

    rows = loo(probes, Xs, y, lam=1.0, threshold=0.5)
    learned = summarize(rows, 'learned-0.5')
    print(learned)

    no = fixed_cost(probes, POL_NO)
    yes = fixed_cost(probes, POL_YES)
    base = fixed_cost(probes, POL_BASE)
    def agg(cost):
        return dict(nodes=sum(c[0] for c in cost),
                    cert=sum(c[1] for c in cost))
    print('always-0.25', agg(no))
    print('always-0.50', agg(yes))
    print('always-base', agg(base))

    out = dict(probes=len(probes), yes=sum(1 for p in probes if p['v'] == 'YES'),
               learned=learned,
               always_no=agg(no), always_yes=agg(yes), always_base=agg(base),
               rows=rows)
    json.dump(out, open('exp/v8j/meta_results.json', 'w'), indent=1)
