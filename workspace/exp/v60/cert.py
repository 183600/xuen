"""Integer Farkas packing certificates for the SD/ECC start-time LP."""
import sys
import numpy as np
from scipy.optimize import linprog
import scipy.sparse as sp

sys.path[:0] = ['exp/v60', 'exp/v13']
from sdecc import SDLP
from po import heads_tails

DENS = tuple(range(1, 201)) + (240, 300, 360, 420, 480, 600, 720, 840,
                               1000, 1200, 1500, 2000, 3000, 5000, 10000)


def _farkas_lp(lp):
    A, hi, n_eq, N = lp.A, lp.hi, lp.n_eq, lp.N
    nr = A.shape[0]
    r = nr - n_eq
    B = sp.hstack([A[:n_eq].T, A[n_eq:].T]).tocsr()
    c = np.zeros(n_eq + r)
    c[:n_eq] = 1.0
    c[n_eq:] = hi[n_eq:]
    A_eq = np.zeros((1, n_eq + r))
    A_eq[0, n_eq:] = 1.0
    bounds = [(None, None)] * n_eq + [(0, None)] * r
    return linprog(c, A_ub=-B, b_ub=np.zeros(N), A_eq=A_eq, b_eq=[1.0],
                   bounds=bounds, method='highs')


def _row_meta(lp):
    """Return a list describing rows after the assignment block."""
    n = lp.n
    meta = []
    if lp.elig_aware:
        for k in range(lp.m):
            for t in range(lp.T):
                meta.append(('cap', k, t))
    else:
        for t in range(lp.T):
            meta.append(('cap', None, t))
    if lp.use_expect:
        for i in range(n):
            for j in lp.inst['succ'][i]:
                meta.append(('exp', i, j, None))
    if lp.use_dom:
        last = [lp.T - lp.q[i] - lp.p[i] for i in range(n)]
        for i in range(n):
            for j in lp.inst['succ'][i]:
                tlo = max(0, lp.est[j] - lp.p[i])
                for t in range(tlo, last[i]):
                    meta.append(('dom', i, j, t))
    return meta


def integer_certificate(inst, h, use_expect=False, use_dom=True,
                        elig_aware=None, forbid=None, dens=DENS):
    """Return a verified integer Farkas certificate or None."""
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    for i in range(inst['n']):
        if est[i] + inst['p'][i] + q[i] > h:
            return dict(kind='cp', job=i, est=est[i], p=inst['p'][i],
                        q=q[i], h=h, scale=1, beta=[], dom=[], exp=[],
                        alpha=[], obj=-1, cuts=[])
    if elig_aware is None:
        elig_aware = any(len(set(inst['elig'][i])) < inst['m']
                         for i in range(inst['n']))
    lp = SDLP(inst, h, use_expect=use_expect, use_dom=use_dom,
              elig_aware=elig_aware, forbid=forbid)
    if not hasattr(lp, 'A'):
        lp.A, lp.hi = lp.matrix()
    r = _farkas_lp(lp)
    if r.status != 0 or r.fun >= 0:
        return None
    n = lp.n
    A = lp.A.tocsr()
    meta = _row_meta(lp)
    for D in dens:
        y = np.rint(r.x * D).astype(np.int64)
        ATy = A.T.dot(y)
        bt = int(lp.hi[n:].dot(y[n:])) + int(y[:n].sum())
        if ATy.min() >= 0 and bt < 0:
            yb = y[n:]
            nz = [(meta[k], int(yb[k])) for k in range(len(meta)) if yb[k]]
            return dict(kind='packing', scale=D, beta=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                                       if m[0] == 'cap' and yb[k]],
                        dom=[(m[1], m[2], m[3], int(yb[k])) for k, m in enumerate(meta)
                             if m[0] == 'dom' and yb[k]],
                        exp=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                             if m[0] == 'exp' and yb[k]],
                        alpha=[int(v) for v in y[:n]],
                        obj=bt, cuts=nz, farkas=r.fun)
    return None


def verify(inst, h, c, use_expect=False, elig_aware=None, forbid=None):
    """Exact integer replay of a certificate (SD rows only if exp==[])."""
    n, m, p = inst['n'], inst['m'], inst['p']
    forbid = set(forbid or ())
    est, q = heads_tails(inst, 0, [0] * n)
    if c.get('kind') == 'cp':
        i = c['job']
        return est[i] + p[i] + q[i] > h
    if elig_aware is None:
        elig_aware = any(len(set(inst['elig'][i])) < m for i in range(n))
    edges = [(i, j) for i in range(n) for j in inst['succ'][i]]
    # beta[(k,t)] for eligibility-aware, beta[t] for full
    beta = {}
    for k, t, w in c['beta']:
        beta[(k, t)] = beta.get((k, t), 0) + w
    lam = {}
    for i, j, t, w in c['dom']:
        lam[(i, j, t)] = lam.get((i, j, t), 0) + w
    # dominance coefficients per (job, start)
    # incoming edges shift by p_k
    for i in range(n):
        lo, hi = est[i], h - q[i] - p[i]
        if lo > hi:
            return False
        for s in range(lo, hi + 1):
            if (i, s) in forbid:
                continue
            val = c['alpha'][i]
            if elig_aware:
                for k in inst['elig'][i]:
                    val += sum(beta.get((k, u), 0)
                               for u in range(s, min(s + p[i], h)))
            else:
                val += sum(beta.get((None, u), 0)
                           for u in range(s, min(s + p[i], h)))
            for j in inst['succ'][i]:
                val -= sum(w for (a, b, t), w in lam.items()
                           if a == i and b == j and t >= s)
            for k in inst['pred'][i]:
                val += sum(w for (a, b, t), w in lam.items()
                           if a == k and b == i and t >= s - p[k])
            if val < 0:
                return False
    obj = sum(c['alpha'])
    if elig_aware:
        obj += sum(w for w in beta.values())
    else:
        obj += m * sum(w for w in beta.values())
    return obj < 0


def integer_certificate_from_lp(lp, inst, h, dens=DENS):
    """Integer Farkas certificate for an already-built SDLP or LazySD.

    LazySD stores only the separated dominance rows in lp.cuts; the
    resulting certificate is therefore much sparser than the full LP one,
    and remains valid for the full LP because every added cut is valid.
    """
    est, q = lp.est, lp.q
    for i in range(inst['n']):
        if est[i] + inst['p'][i] + q[i] > h:
            return dict(kind='cp', job=i, est=est[i], p=inst['p'][i],
                        q=q[i], h=h, scale=1, beta=[], dom=[], exp=[],
                        alpha=[], obj=-1, cuts=[])
    if not hasattr(lp, 'A'):
        lp.A, lp.hi = lp.matrix()
    r = _farkas_lp(lp)
    if r.status != 0 or r.fun >= 0:
        return None
    n = lp.n
    A = lp.A.tocsr()
    meta = _row_meta(lp.base) if hasattr(lp, 'base') else _row_meta(lp)
    if hasattr(lp, 'cuts'):
        meta += [('dom', i, j, t) for (i, j, t) in lp.cuts]
    for D in dens:
        y = np.rint(r.x * D).astype(np.int64)
        ATy = A.T.dot(y)
        bt = int(lp.hi[n:].dot(y[n:])) + int(y[:n].sum())
        if ATy.min() >= 0 and bt < 0:
            yb = y[n:]
            nz = [(meta[k], int(yb[k])) for k in range(len(meta)) if yb[k]]
            return dict(kind='packing', scale=D,
                        beta=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                              if m[0] == 'cap' and yb[k]],
                        dom=[(m[1], m[2], m[3], int(yb[k])) for k, m in enumerate(meta)
                             if m[0] == 'dom' and yb[k]],
                        exp=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                             if m[0] == 'exp' and yb[k]],
                        alpha=[int(v) for v in y[:n]], obj=bt, cuts=nz,
                        farkas=r.fun)
    return None
