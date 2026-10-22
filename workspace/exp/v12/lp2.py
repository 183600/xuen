"""v1.2 audited relaxations.

The v1.1 "configuration LP" (exp/v09/lp.py) enumerates item subsets that fit
*some* machine and then bounds only the total number of patterns by m.  It
never enforces that patterns which only fit machine k do not exceed machine
k's one-bin budget.  With heterogeneous eligibility that is unsound: it can
report tau* <= m, and return a dual vector lambda with sum lambda > m, even
when a subset of items has total size larger than the capacity of the machines
they are allowed to use.

This module implements the *assignment LP* (ALP):

    sum_{k in E_i} x_{ik} = 1          for every item i
    sum_i p_i x_{ik} <= C_k            for every machine k
    x >= 0

ALP is a sound relaxation: any integral packing is feasible for it.  Its dual
is the Farkas certificate

    alpha_i <= p_i beta_k   for every k in E_i
    alpha_i >= 0, beta_k >= 0
    sum_i alpha_i > sum_k C_k beta_k    =>  PACK = NO.

We solve ALP exactly with a Fraction two-phase simplex for the small
benchmarks (n <= 16).  The routine is deliberately independent of v1.1's LP.
"""
from fractions import Fraction


def _pivot(T, basis, r, c):
    """Pivot tableau T (list of rows, last column rhs) on row r, column c."""
    piv = T[r][c]
    T[r] = [v / piv for v in T[r]]
    for i in range(len(T)):
        if i == r:
            continue
        f = T[i][c]
        if f:
            T[i] = [a - f * b for a, b in zip(T[i], T[r])]
    basis[r] = c


def assignment_lp(p, caps, elig):
    """Exact ALP feasibility with a Fraction simplex.

    p: list[int], caps: list[int], elig: list[list[int]].
    Returns (feasible: bool, x: dict[(i,k)] -> Fraction, dual: list[Fraction]).
    For n <= ~16 only (dense tableau).  Bland's rule, no cycling.
    """
    n = len(p)
    m = len(caps)
    if n == 0:
        return True, {}, [Fraction(0)] * m
    # structural variables x_{i,k}, only for eligible k
    cols = []
    for i in range(n):
        for k in elig[i]:
            cols.append((i, k))
    nv = len(cols)
    if nv == 0:
        return False, {}, []
    # rows: n equality rows, m capacity rows (<=)
    nrows = n + m
    # columns: nv structural + m slacks + n artificials + rhs
    ncols = nv + m + n + 1
    T = [[Fraction(0) for _ in range(ncols)] for _ in range(nrows)]
    for j, (i, k) in enumerate(cols):
        T[i][j] = Fraction(1)
        T[n + k][j] = Fraction(p[i])
    for k in range(m):
        T[n + k][nv + k] = Fraction(1)
    for i in range(n):
        T[i][nv + m + i] = Fraction(1)
        T[i][-1] = Fraction(1)
    for k in range(m):
        T[n + k][-1] = Fraction(caps[k])
    basis = [nv + m + i for i in range(n)] + [nv + k for k in range(m)]
    # phase-1 objective: minimize sum artificials.
    # objective row = c - c_B B^{-1} A; B = I, c_B = 1 on the n artificials.
    obj = [Fraction(0) for _ in range(ncols)]
    for j in range(nv):
        obj[j] = -sum(T[i][j] for i in range(n))
    for k in range(m):
        obj[nv + k] = Fraction(0)
    for i in range(n):
        obj[nv + m + i] = Fraction(0)
    obj[-1] = -sum(T[i][-1] for i in range(n))  # negative of current sum
    # We keep the objective row in the convention: value = obj[-1] (min).
    T.append(obj)
    objrow = nrows

    def simplex():
        it = 0
        while True:
            it += 1
            if it > 10000:
                raise RuntimeError('simplex iteration limit')
            # Bland: smallest index with negative reduced cost
            enter = -1
            for j in range(ncols - 1):
                if T[objrow][j] < 0:
                    enter = j
                    break
            if enter < 0:
                return
            # ratio test
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
                return  # unbounded (cannot happen in phase 1)
            _pivot(T, basis, leave, enter)

    simplex()
    # phase-1 objective value = -T[objrow][-1] (should be 0)
    infeas = -T[objrow][-1]
    if infeas > Fraction(1, 10**9):
        # Farkas dual: y = c_B B^{-1}; recover from the artificial columns'
        # reduced costs is messy; return the phase-1 multiplier on each row
        # by solving y B = c_B.  B is the current basis matrix, so y = c_B B^{-1}.
        # Build B and invert by Gauss-Jordan (exact).
        y = _basis_dual(T, basis, n, m, nv, n, nrows)
        return False, {}, y
    # drive artificials out of the basis if any are basic at zero
    for i in range(nrows):
        if basis[i] >= nv + m:
            # find a non-artificial column with nonzero entry in this row
            for j in range(nv + m):
                if T[i][j] > 0:
                    _pivot(T, basis, i, j)
                    break
    x = {}
    for i in range(nrows):
        if basis[i] < nv:
            x[cols[basis[i]]] = T[i][-1]
    dual = _basis_dual(T, basis, n, m, nv, n, nrows)
    return True, x, dual


def _basis_dual(T, basis, n, m, nv, nart, nrows):
    """Return y with y B = c_B for the original phase-1 costs.

    For phase 1 c_B is 1 for artificial columns and 0 otherwise.  This yields
    the Farkas multipliers on the n equality rows and m capacity rows.
    """
    # Solve B^T y^T = c_B^T by Gauss-Jordan on the basis columns.
    A = [[T[i][basis[j]] for j in range(nrows)] + [Fraction(1) if i == j else Fraction(0)
                                                   for j in range(nrows)] for i in range(nrows)]
    for c in range(nrows):
        piv = None
        for r in range(c, nrows):
            if A[r][c] != 0:
                piv = r
                break
        if piv is None:
            continue
        A[c], A[piv] = A[piv], A[c]
        pv = A[c][c]
        A[c] = [v / pv for v in A[c]]
        for r in range(nrows):
            if r != c and A[r][c] != 0:
                f = A[r][c]
                A[r] = [a - f * b for a, b in zip(A[r], A[c])]
    # inverse columns: B^{-1}[i][j] = A[j][nrows + i]
    Binv = [[A[j][nrows + i] for j in range(nrows)] for i in range(nrows)]
    cB = [Fraction(1) if basis[j] >= nv + m else Fraction(0) for j in range(nrows)]
    # y = cB^T Binv
    y = [sum(cB[j] * Binv[j][i] for j in range(nrows)) for i in range(nrows)]
    return y


def check_farkas(p, caps, elig, y, tol=0):
    """Check a Farkas certificate produced by assignment_lp.

    y = [alpha_1..alpha_n, beta_1..beta_m] (phase-1 multipliers).
    Returns (ok, margin) for: alpha_i >= 0, beta_k >= 0,
    alpha_i <= p_i beta_k for k in E_i, sum alpha > sum C beta.
    """
    n = len(p); m = len(caps)
    al = y[:n]; be = y[n:n + m]
    ok = all(a >= -tol for a in al) and all(b >= -tol for b in be)
    for i in range(n):
        for k in elig[i]:
            if al[i] - p[i] * be[k] > tol:
                ok = False
    margin = sum(al) - sum(caps[k] * be[k] for k in range(m))
    return ok and margin > tol, margin
