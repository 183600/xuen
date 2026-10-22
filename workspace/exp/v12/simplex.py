"""Exact small LP feasibility (Fraction simplex) for the v1.2 audit.

Rows 0..n_eq-1 are equalities; rows n_eq..n_eq+n_ub-1 are <=.
Columns are dicts {row: coefficient}.  Phase-1 simplex with Bland's rule.
"""
from fractions import Fraction


def _pivot(T, basis, r, c):
    piv = T[r][c]
    T[r] = [v / piv for v in T[r]]
    for i in range(len(T)):
        if i == r:
            continue
        f = T[i][c]
        if f:
            T[i] = [a - f * b for a, b in zip(T[i], T[r])]
    basis[r] = c


def feasible(columns, n_eq, n_ub, rhs, max_iter=20000):
    """Return (feasible, x) where x[j] is the value of column j."""
    nrows = n_eq + n_ub
    nv = len(columns)
    ncols = nv + n_ub + n_eq + 1
    T = [[Fraction(0) for _ in range(ncols)] for _ in range(nrows)]
    for j, col in enumerate(columns):
        for r, a in col.items():
            T[r][j] = Fraction(a)
    for k in range(n_ub):
        T[n_eq + k][nv + k] = Fraction(1)
        T[n_eq + k][-1] = Fraction(rhs[n_eq + k])
    for i in range(n_eq):
        T[i][nv + n_ub + i] = Fraction(1)
        T[i][-1] = Fraction(rhs[i])
    basis = [nv + n_ub + i for i in range(n_eq)] + [nv + k for k in range(n_ub)]
    obj = [Fraction(0) for _ in range(ncols)]
    for j in range(nv):
        obj[j] = -sum(T[i][j] for i in range(n_eq))
    obj[-1] = -sum(T[i][-1] for i in range(n_eq))
    T.append(obj)
    objrow = nrows
    it = 0
    while True:
        it += 1
        if it > max_iter:
            raise RuntimeError('simplex iteration limit')
        enter = -1
        for j in range(ncols - 1):
            if T[objrow][j] < 0:
                enter = j
                break
        if enter < 0:
            break
        leave = -1
        best = None
        for i in range(nrows):
            a = T[i][enter]
            if a > 0:
                ratio = T[i][-1] / a
                if best is None or ratio < best or (ratio == best and basis[i] < basis[leave]):
                    best = ratio
                    leave = i
        if leave < 0:
            return False, None  # unbounded in phase 1: cannot happen
        _pivot(T, basis, leave, enter)
    if -T[objrow][-1] > Fraction(1, 10**9):
        return False, None
    for i in range(nrows):
        if basis[i] >= nv + n_ub:
            for j in range(nv + n_ub):
                if T[i][j] > 0:
                    _pivot(T, basis, i, j)
                    break
    x = [Fraction(0)] * nv
    for i in range(nrows):
        if basis[i] < nv:
            x[basis[i]] = T[i][-1]
    return True, x
