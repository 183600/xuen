"""PCLP: precedence-cut LP certificate for the deadline decision.

Relaxation of the time-indexed nonpreemptive start-time formulation:

    x[i,t] >= 0,  sum_t x[i,t] = 1
    for every u:  sum_i sum_{t <= u < t+p_i} x[i,t] <= m
    for every edge i->j and every integer t:
        sum_{s < t} x[j,s]  <=  sum_{s <= t-1-p_i} x[i,s]

The last family is valid for every deterministic schedule (s_j >= s_i+p_i),
hence for every convex combination; so LP infeasibility at h proves NO.
"""
import sys
sys.path[:0] = ['exp/v13']
import po
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix


def windows(inst, h):
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = po.heads_tails(inst, 0, [0] * n)
    lo = [max(0, est[i]) for i in range(n)]
    hi = [h - q[i] - p[i] for i in range(n)]
    return lo, hi, est, q


def build(inst, h, cuts='all'):
    n, m, p = inst['n'], inst['m'], inst['p']
    lo, hi, est, q = windows(inst, h)
    col = {}
    for i in range(n):
        for t in range(lo[i], hi[i] + 1):
            col[(i, t)] = len(col)
    N = len(col)
    rows, cols, vals = [], [], []
    b = []
    r = 0
    # equality: one start per job
    for i in range(n):
        for t in range(lo[i], hi[i] + 1):
            rows.append(r); cols.append(col[(i, t)]); vals.append(1.0)
        b.append(1.0); r += 1
    eq_end = r
    # capacity
    for u in range(h):
        any_ = False
        for i in range(n):
            a = max(lo[i], u - p[i] + 1)
            z = min(hi[i], u)
            for t in range(a, z + 1):
                rows.append(r); cols.append(col[(i, t)]); vals.append(1.0)
                any_ = True
        if any_:
            b.append(float(m)); r += 1
    # precedence cumulative cuts, all t
    if cuts in ('all', 'iter'):
        for j in range(n):
            for i in inst['pred'][j]:
                for t in range(1, h + 1):
                    cnt = 0
                    for s in range(lo[j], min(hi[j], t - 1) + 1):
                        rows.append(r); cols.append(col[(j, s)]); vals.append(1.0)
                        cnt += 1
                    for s in range(lo[i], min(hi[i], t - 1 - p[i]) + 1):
                        rows.append(r); cols.append(col[(i, s)]); vals.append(-1.0)
                        cnt += 1
                    if cnt:
                        b.append(0.0); r += 1
    A = coo_matrix((vals, (rows, cols)), shape=(r, N)).tocsr()
    return A, np.array(b), eq_end, col, lo, hi


class WindowInfeasible:
    status = 2
    message = 'empty start window'
    x = None


def solve(inst, h, cuts='all', options=None):
    lo, hi, est, q = windows(inst, h)
    if any(lo[i] > hi[i] for i in range(inst['n'])):
        return WindowInfeasible(), (None, None, None, None, lo, hi)
    A, b, eq_end, col, lo, hi = build(inst, h, cuts)
    A_eq = A[:eq_end]
    b_eq = b[:eq_end]
    A_ub = A[eq_end:]
    b_ub = b[eq_end:]
    opts = dict(presolve=True)
    if options:
        opts.update(options)
    res = linprog(np.zeros(A.shape[1]), A_ub=A_ub, b_ub=b_ub,
                  A_eq=A_eq, b_eq=b_eq, bounds=(0, 1), method='highs',
                  options=opts)
    return res, (A, b, eq_end, col, lo, hi)


def feasible(inst, h, **kw):
    res, _ = solve(inst, h, **kw)
    return res.status == 0, res


if __name__ == '__main__':
    import pickle, time
    d = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    t0 = time.time(); no = yes = 0
    for idx, (inst, opt) in enumerate(d):
        f1, r1 = feasible(inst, opt - 1)
        f2, r2 = feasible(inst, opt)
        no += (not f1); yes += f2
        print(idx, 'h=opt-1 feas', f1, 'h=opt feas', f2,
              't', round(r2.elapsed if hasattr(r2, 'elapsed') else 0, 4), flush=True)
    print('NO proved', no, '/', len(d), 'YES feasible', yes, 'total t', round(time.time() - t0, 2))
