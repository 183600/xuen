"""Normalized Farkas-ray LP for the start-time LP.

Variables: alpha+ (n), alpha- (n), beta (T), gamma (E).
max  sum(alpha+ - alpha-) + m*sum(beta) - sum(p_i gamma_e)
s.t. alpha_i + B_i(t) + t*sigma_i >= 0   for all (i,t)
     sum(alpha+) + sum(alpha-) + sum(beta) + sum(gamma) <= 1
All variables >= 0.  Optimum > 0 iff the start-time LP is infeasible.
"""
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix


def farkas_ray(inst, h, est, q):
    n, m, p = inst['n'], inst['m'], inst['p']
    pred, succ = inst['pred'], inst['succ']
    T = h
    edges = [(i, j) for i in range(n) for j in succ[i]]
    E = len(edges)
    eidx = {e: k for k, e in enumerate(edges)}
    # var layout: ap n | am n | beta T | gamma E
    oa, ob, og = 0, 2 * n, 2 * n + T
    N = 2 * n + T + E
    rows, lo, hi = [], [], []
    for i in range(n):
        for t in range(est[i], h - q[i] - p[i] + 1):
            row = {oa + i: 1.0, oa + n + i: -1.0}
            for u in range(t, t + p[i]):
                if u < T:
                    row[ob + u] = row.get(ob + u, 0.0) - 1.0
            for j in succ[i]:
                row[og + eidx[(i, j)]] = row.get(og + eidx[(i, j)], 0.0) - t
            for k in pred[i]:
                row[og + eidx[(k, i)]] = row.get(og + eidx[(k, i)], 0.0) + t
            rows.append(row); lo.append(-np.inf); hi.append(0.0)
    # normalization
    row = {oa + i: 1.0 for i in range(n)}
    row.update({oa + n + i: 1.0 for i in range(n)})
    row.update({ob + t: 1.0 for t in range(T)})
    row.update({og + k: 1.0 for k in range(E)})
    rows.append(row); lo.append(-np.inf); hi.append(1.0)
    A = lil_matrix((len(rows), N))
    bub = np.zeros(len(rows))
    for r, rr in enumerate(rows):
        if lo[r] == 0.0 and hi[r] == np.inf:
            for c, v in rr.items():
                A[r, c] = -v
            bub[r] = 0.0
        else:
            for c, v in rr.items():
                A[r, c] = v
            bub[r] = hi[r]
    c = np.zeros(N)
    c[oa:oa + n] = 1.0
    c[oa + n:oa + 2 * n] = -1.0
    c[ob:ob + T] = -float(m)
    for k, (i, j) in enumerate(edges):
        c[og + k] = float(p[i])
    res = linprog(-c, A_ub=A.tocsr(), b_ub=bub, bounds=(0, None), method='highs')
    out = {'status': res.status, 'value': -res.fun if res.status == 0 else None,
           'edges': edges, 'oa': oa, 'ob': ob, 'og': og}
    if res.status == 0:
        x = res.x
        out['alpha'] = x[oa:oa + n] - x[oa + n:oa + 2 * n]
        out['beta'] = x[ob:ob + T]
        out['gamma'] = {e: x[og + k] for k, e in enumerate(edges)}
        out['nz_beta'] = int((out['beta'] > 1e-8).sum())
        out['nz_gamma'] = int(sum(1 for v in out['gamma'].values() if v > 1e-8))
    return out
