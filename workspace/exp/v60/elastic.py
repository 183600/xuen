"""Elastic start-time LP: bounded relaxation whose dual is a Farkas certificate."""
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix


def elastic_cert(inst, h, est, q):
    n, m, p = inst['n'], inst['m'], inst['p']
    T = h
    nz = {}
    cols = []
    for i in range(n):
        for t in range(est[i], h - q[i] - p[i] + 1):
            nz[(i, t)] = len(cols); cols.append(('z', i, t))
    Nz = len(cols)
    # elastic vars: s+ n, s- n, ecap T, eprec E
    ncap = T
    edges = [(i, j) for i in range(n) for j in inst['succ'][i]]
    ne = len(edges)
    N = Nz + 2 * n + ncap + ne
    off_sp, off_sm, off_cap, off_pre = Nz, Nz + n, Nz + 2 * n, Nz + 2 * n + ncap

    rows, lo, hi = [], [], []
    for i in range(n):
        row = {c: 1.0 for (a, t), c in nz.items() if a == i}
        row[off_sp + i] = 1.0
        row[off_sm + i] = -1.0
        rows.append(row); lo.append(1.0); hi.append(1.0)
    for t in range(T):
        row = {}
        for (i, s), c in nz.items():
            if s <= t < s + p[i]:
                row[c] = 1.0
        row[off_cap + t] = -1.0
        rows.append(row); lo.append(-np.inf); hi.append(float(m))
    for eidx, (i, j) in enumerate(edges):
        row = {}
        for (a, t), c in nz.items():
            if a == i: row[c] = float(t)
            if a == j: row[c] = row.get(c, 0.0) - float(t)
        row[off_pre + eidx] = -1.0
        rows.append(row); lo.append(-np.inf); hi.append(-float(p[i]))
    A = lil_matrix((len(rows), N))
    for r, row in enumerate(rows):
        for c, v in row.items(): A[r, c] = v
    A = A.tocsr()
    lo = np.array(lo); hi = np.array(hi)
    c = np.zeros(N)
    c[Nz:] = 1.0
    bounds = [(0, 1)] * Nz + [(0, None)] * (2 * n + ncap + ne)
    res = linprog(c, A_ub=A, b_ub=hi, A_eq=A[:n], b_eq=lo[:n], bounds=bounds, method='highs')
    out = {'status': res.status, 'opt': res.fun, 'nz': nz, 'cols': cols, 'edges': edges,
           'off': (off_sp, off_sm, off_cap, off_pre)}
    if res.status == 0:
        ycap = -np.asarray(res.ineqlin.marginals)[:T]
        ypre = -np.asarray(res.ineqlin.marginals)[T:T + ne]
        alpha = -np.asarray(res.eqlin.marginals)
        out['beta'] = np.maximum(ycap, 0.0)
        out['gamma'] = {(i, j): max(0.0, ypre[k]) for k, (i, j) in enumerate(edges)}
        out['alpha'] = alpha
        # evaluate D from the extracted certificate
        from ada import evaluate
        D, a2, ts = evaluate(inst, h, est, q, out['beta'], out['gamma'])
        out['D'] = D
        out['nz_beta'] = int((out['beta'] > 1e-9).sum())
        out['nz_gamma'] = int(sum(1 for v in out['gamma'].values() if v > 1e-9))
    return out
