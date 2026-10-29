"""DUAL-CERT/2: fast exact Farkas certificate for the time-indexed LP."""
import sys, time
sys.path[:0] = ['exp/v35', 'exp/v13']
import numpy as np
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
    return A, b, eq_end


def solve(inst, h, time_limit=2.0):
    z = build(inst, h)
    if z is None:
        return False, ('single-job',)
    A, b, eq_end = z
    Aeq, Aub = A[:eq_end], A[eq_end:]
    beq, bub = b[:eq_end], b[eq_end:]
    nv = Aeq.shape[0] + Aub.shape[0]
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
    yi = np.rint(y).astype(np.int64)
    if np.max(np.abs(y - yi)) > 1e-7:
        return None, ('noninteger',)
    if np.any(yi[eq_end:] < 0):
        return None, ('sign',)
    ATy = A.T.dot(yi)
    bt = int(beq.dot(yi[:eq_end]) + bub.dot(yi[eq_end:]))
    if ATy.min() >= 0 and bt < 0:
        return False, ('farkas', int(np.count_nonzero(ATy)),
                       int(np.count_nonzero(yi[eq_end:])), bt)
    return None, ('verify-failed', int(ATy.min()), bt)


if __name__ == '__main__':
    import pickle
    for name, f in [('holdout50', 'exp/v20/holdout_cases50.pkl'),
                    ('hard3', 'exp/v13/hard3.pkl'),
                    ('deep8', 'exp/v18/deep.pkl'),
                    ('synth45', 'exp/v28/synth2_45.pkl')]:
        d = pickle.load(open(f, 'rb'))
        for hm in (-1, 0):
            no = unk = nonint = 0; t0 = time.time()
            for z in d:
                inst = z[0] if isinstance(z[0], dict) else z['inst']
                opt = z[1] if isinstance(z[1], int) else z['opt']
                v, info = solve(inst, opt + hm)
                if v is False: no += 1
                elif v is None:
                    unk += 1
                    if info[0] == 'noninteger': nonint += 1
            print(name, 'hm', hm, 'cert', no, 'unk', unk, 'nonint', nonint,
                  't %.4f' % (time.time() - t0))
