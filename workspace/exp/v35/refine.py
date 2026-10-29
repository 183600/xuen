"""Cutting-plane refinement for the PCLP relaxation.

Start from the capacity-only LP (EPC-strength, always feasible on the
benchmark), separate violated cumulative-precedence cuts, add them, re-solve.
Infeasibility of a subset of valid cuts already proves NO.
"""
import sys, time
sys.path[:0] = ['exp/v35', 'exp/v13']
import po
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix


def windows(inst, h):
    n = inst['n']
    est, q = po.heads_tails(inst, 0, [0] * n)
    lo = [max(0, est[i]) for i in range(n)]
    hi = [h - q[i] - inst['p'][i] for i in range(n)]
    if any(lo[i] > hi[i] for i in range(n)):
        return None
    return lo, hi


def base_lp(inst, h, lo, hi, elig_rows=False):
    n, m, p = inst['n'], inst['m'], inst['p']
    col = {}
    for i in range(n):
        for t in range(lo[i], hi[i] + 1):
            col[(i, t)] = len(col)
    N = len(col)
    rows, cols, vals, b = [], [], [], []
    r = 0
    for i in range(n):
        for t in range(lo[i], hi[i] + 1):
            rows.append(r); cols.append(col[(i, t)]); vals.append(1.0)
        b.append(1.0); r += 1
    eq_end = r
    # optional machine-subset capacity rows (sound, but costly; off by default)
    subs = [frozenset(range(m))]
    if elig_rows and m <= 4:
        for mask in range(1, 1 << m):
            subs.append(frozenset(k for k in range(m) if (mask >> k) & 1))
    subs = sorted(set(subs), key=len)
    for S in subs:
        ids = [i for i in range(n) if set(inst['elig'][i]) <= S]
        if not ids:
            continue
        for u in range(h):
            any_ = False
            for i in ids:
                for t in range(max(lo[i], u - p[i] + 1), min(hi[i], u) + 1):
                    rows.append(r); cols.append(col[(i, t)]); vals.append(1.0)
                    any_ = True
            if any_:
                b.append(float(len(S))); r += 1
    return col, np.array(rows), np.array(cols), np.array(vals), np.array(b), eq_end


def cut_row(col, lo, hi, i, j, t, pi, sign=1.0):
    """Row for  sum_{s<t} x_j,s - sum_{s<=t-1-pi} x_i,s <= 0."""
    rr, cc, vv = [], [], []
    for s in range(lo[j], min(hi[j], t - 1) + 1):
        rr.append(col[(j, s)]); vv.append(sign)
    for s in range(lo[i], min(hi[i], t - 1 - pi) + 1):
        rr.append(col[(i, s)]); vv.append(-sign)
    return rr, vv


def solve_cp(inst, h, max_rounds=50, violation_tol=1e-9, add='most', max_cuts=200):
    """Returns (verdict, info): verdict in {'NO','UNKNOWN'}, info with rounds/cuts/x."""
    n, m, p = inst['n'], inst['m'], inst['p']
    w = windows(inst, h)
    if w is None:
        return 'NO', dict(rounds=0, cuts=0, reason='window')
    lo, hi = w
    col, rr, cc, vv, b, eq_end = base_lp(inst, h, lo, hi)
    N = len(col)
    crr, ccc, cvv = [], [], []
    cut_meta = []
    for rnd in range(max_rounds):
        nrows = len(b) + len(cut_meta)
        rows = np.concatenate([rr, np.array(crr, dtype=int)]) if crr else rr
        cols = np.concatenate([cc, np.array(ccc, dtype=int)]) if crr else cc
        vals = np.concatenate([vv, np.array(cvv, dtype=float)]) if crr else vv
        bb = np.concatenate([b, np.zeros(len(cut_meta))]) if crr else b
        A = coo_matrix((vals, (rows, cols)), shape=(nrows, N)).tocsr()
        res = linprog(np.zeros(N), A_ub=A[eq_end:], b_ub=bb[eq_end:],
                      A_eq=A[:eq_end], b_eq=bb[:eq_end], bounds=(0, 1),
                      method='highs', options=dict(presolve=True))
        if res.status != 0:
            return 'NO', dict(rounds=rnd, cuts=len(cut_meta), status=res.status)
        x = res.x
        # separation
        viol = []
        for j in range(n):
            for i in inst['pred'][j]:
                pi = p[i]
                for t in range(1, h + 1):
                    lhs = 0.0
                    for s in range(lo[j], min(hi[j], t - 1) + 1):
                        lhs += x[col[(j, s)]]
                    rhs = 0.0
                    for s in range(lo[i], min(hi[i], t - 1 - pi) + 1):
                        rhs += x[col[(i, s)]]
                    if lhs - rhs > violation_tol:
                        viol.append((lhs - rhs, i, j, t))
        if not viol:
            return 'UNKNOWN', dict(rounds=rnd + 1, cuts=len(cut_meta), x=x,
                                   col=col, lo=lo, hi=hi)
        viol.sort(reverse=True)
        if add == 'most':
            chosen = viol[:max_cuts]
        else:
            chosen = [v for v in viol if v[0] > 1e-6][:max_cuts]
        if not chosen:
            return 'UNKNOWN', dict(rounds=rnd + 1, cuts=len(cut_meta), x=x,
                                   col=col, lo=lo, hi=hi,
                                   reason='cut budget exhausted')
        base_row = len(b) + len(cut_meta)
        for k, (v, i, j, t) in enumerate(chosen):
            ccx, vvx = cut_row(col, lo, hi, i, j, t, p[i])
            row = base_row + k
            for c_, v_ in zip(ccx, vvx):
                crr.append(row); ccc.append(c_); cvv.append(v_)
            cut_meta.append((i, j, t, v))
    return 'UNKNOWN', dict(rounds=max_rounds, cuts=len(cut_meta), reason='rounds')


if __name__ == '__main__':
    import pickle, json
    d = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    t0 = time.time()
    rows = []
    for idx, (inst, opt) in enumerate(d):
        t1 = time.time()
        v, info = solve_cp(inst, opt - 1)
        rows.append((idx, v, info.get('cuts'), info.get('rounds'),
                     round(time.time() - t1, 4)))
        print(rows[-1], flush=True)
    no = sum(1 for r in rows if r[1] == 'NO')
    print('NO', no, '/', len(d), 'time', round(time.time() - t0, 2))
    print('cuts', [r[2] for r in rows])
