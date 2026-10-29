"""DUAL-CERT: polynomial-time Farkas certificate for the time-indexed LP.

Primal relaxation:
  A_eq x = b_eq,  A_ub x <= b_ub,  x >= 0.
Farkas:
  y_eq free, y_ub >= 0,
  A_eq^T y_eq + A_ub^T y_ub >= 0,
  b_eq^T y_eq + b_ub^T y_ub < 0.
We normalize b^T y = -1, find a rational point, and verify exactly.
"""
import sys, time
sys.path[:0] = ['exp/v35', 'exp/v13']
import numpy as np
from fractions import Fraction
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
import refine


def build(inst, h):
    n, m, p = inst['n'], inst['m'], inst['p']
    w = refine.windows(inst, h)
    if w is None:
        return None
    lo, hi = w
    col, rr, cc, vv, b, eq_end = refine.base_lp(inst, h, lo, hi)
    A = coo_matrix((vv, (rr, cc)), shape=(len(b), len(col))).tocsr()
    return A, b, eq_end, col, lo, hi


def solve(inst, h, time_limit=2.0):
    t0 = time.time()
    z = build(inst, h)
    if z is None:
        return False, ('single-job',)
    A, b, eq_end, col, lo, hi = z
    Aeq, Aub = A[:eq_end], A[eq_end:]
    beq, bub = b[:eq_end], b[eq_end:]
    nv = Aeq.shape[0] + Aub.shape[0]
    # -A^T y <= 0  and  b^T y = -1
    A_ub = (-A.T).tocsr()
    b_ub = np.zeros(A.shape[1])
    A_eq = np.concatenate([beq, bub])[None, :]
    b_eq = np.array([-1.0])
    bounds = [(None, None)] * Aeq.shape[0] + [(0, None)] * Aub.shape[0]
    res = linprog(np.zeros(nv), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=bounds, method='highs',
                  options=dict(time_limit=time_limit))
    if res.status != 0:
        return None, ('dual-infeasible', res.status)
    y = res.x
    ye = y[:Aeq.shape[0]]
    yu = y[Aeq.shape[0]:]
    # Try integer, then rational roundings; exact verification.
    for den in (1, 2, 3, 4, 6, 12, 60, 1000, 10**6):
        yef = [Fraction(round(float(x) * den), den) for x in ye]
        yuf = [Fraction(round(float(x) * den), den) for x in yu]
        if any(x < 0 for x in yuf):
            continue
        ok = True
        for j in range(A.shape[1]):
            s = Fraction(0)
            for i, jj, v in zip(A.indptr, A.indices, A.data):
                pass
            # use CSR rows below instead
        # column-wise exact check
        ATy = [Fraction(0) for _ in range(A.shape[1])]
        for i in range(A.shape[0]):
            start, end = A.indptr[i], A.indptr[i + 1]
            yi = yef[i] if i < eq_end else yuf[i - eq_end]
            if yi == 0:
                continue
            for k in range(start, end):
                ATy[A.indices[k]] += yi * int(A.data[k])
        if any(q < 0 for q in ATy):
            continue
        bt = sum(beq[i] * yef[i] for i in range(len(beq))) + \
             sum(bub[i] * yuf[i] for i in range(len(bub)))
        if bt < 0:
            return False, ('farkas', int(sum(1 for q in ATy if q > 0)),
                           int(sum(1 for q in yuf if q > 0)), bt)
    return None, ('rounding-failed',)


if __name__ == '__main__':
    import pickle
    for name, f in [('holdout50', 'exp/v20/holdout_cases50.pkl'),
                    ('hard3', 'exp/v13/hard3.pkl'),
                    ('deep8', 'exp/v18/deep.pkl'),
                    ('synth45', 'exp/v28/synth2_45.pkl')]:
        d = pickle.load(open(f, 'rb'))
        for hm in (-1, 0):
            no = unk = 0; t0 = time.time(); err = 0
            for z in d:
                inst = z[0] if isinstance(z[0], dict) else z['inst']
                opt = z[1] if isinstance(z[1], int) else z['opt']
                v, info = solve(inst, opt + hm)
                if v is False: no += 1
                elif v is None: err += 1
                else: unk += 1
            print(name, 'hm', hm, 'cert', no, 'unk', unk, 't %.4f' % (time.time() - t0))
