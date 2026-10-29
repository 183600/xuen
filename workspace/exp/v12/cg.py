"""Column generation for the per-machine configuration LP (v1.2), corrected.

Feasibility form (phase 1).  Variables:
  y_{k,S} >= 0   pattern (machine k, item subset S)
  a_i     >= 0   deficit of item i (cost 1)
  s_i     >= 0   surplus of item i
  t_k     >= 0   unused capacity of machine k

    sum_{k,S ni i} y + a_i - s_i = 1        (lambda_i, 0 <= lambda_i <= 1)
    sum_S y_{k,S} + t_k = 1                 (mu_k >= 0)

min sum_i a_i.  The LP is feasible iff the optimum is 0.  The dual is

    max sum lambda_i - sum mu_k
    s.t. sum_{i in S} lambda_i <= mu_k  for every pattern (k,S)
         0 <= lambda_i <= 1, mu_k >= 0.

Pricing is a 0/1 knapsack per machine.  If max_S sum lambda_i > mu_k, the
pattern has negative reduced cost.  When no pattern prices out, the dual is
feasible for the full LP; a positive objective is then a valid Farkas
certificate that the per-machine configuration LP is infeasible.
"""
from fractions import Fraction
from simplex import _pivot


def simplex_min(costs, columns, n_eq, n_ub, rhs, art_start):
    nv = len(columns)
    ncols = nv + n_ub + 1
    T = [[Fraction(0) for _ in range(ncols)] for _ in range(n_eq + n_ub)]
    for j, col in enumerate(columns):
        for r, a in col.items():
            T[r][j] = Fraction(a)
    for k in range(n_ub):
        T[n_eq + k][nv + k] = Fraction(1)
        T[n_eq + k][-1] = Fraction(rhs[n_eq + k])
    for i in range(n_eq):
        T[i][-1] = Fraction(rhs[i])
    basis = [art_start + i for i in range(n_eq)] + [nv + k for k in range(n_ub)]
    obj = [Fraction(0) for _ in range(ncols)]
    for j in range(nv):
        obj[j] = Fraction(costs[j]) - sum(T[i][j] for i in range(n_eq))
    obj[-1] = -sum(T[i][-1] for i in range(n_eq))
    T.append(obj)
    objrow = n_eq + n_ub
    it = 0
    while True:
        it += 1
        if it > 50000:
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
        for i in range(n_eq + n_ub):
            a = T[i][enter]
            if a > 0:
                ratio = T[i][-1] / a
                if best is None or ratio < best or (ratio == best and basis[i] < basis[leave]):
                    best = ratio
                    leave = i
        if leave < 0:
            raise RuntimeError('unbounded master')
        _pivot(T, basis, leave, enter)
    objval = -T[objrow][-1]
    x = [Fraction(0)] * nv
    for i in range(n_eq + n_ub):
        if basis[i] < nv:
            x[basis[i]] = T[i][-1]
    dual = []
    for i in range(n_eq):
        dual.append(Fraction(1) - T[objrow][art_start + i])
    for k in range(n_ub):
        dual.append(-T[objrow][nv + k])
    return objval, x, dual


def knapsack(profits, weights, cap, elig_items):
    """0/1 knapsack, exact Fractions.  Returns (value, S)."""
    dp = [Fraction(0)] * (cap + 1)
    mask = [0] * (cap + 1)
    for i in elig_items:
        w = weights[i]
        if w > cap or profits[i] <= 0:
            continue
        pr = profits[i]
        bit = 1 << i
        for c in range(cap, w - 1, -1):
            v = dp[c - w] + pr
            if v > dp[c]:
                dp[c] = v
                mask[c] = mask[c - w] | bit
    best = max(dp)
    c = dp.index(best)
    S = [i for i in range(len(weights)) if (mask[c] >> i) & 1]
    return best, S


def config_lp_cg(p, caps, elig, max_rounds=1000, verbose=False):
    n = len(p); m = len(caps)
    patterns = []
    seen = set()
    for k in range(m):
        items = sorted([i for i in range(n) if k in elig[i]], key=lambda i: p[i])
        S = []; s = 0
        for i in items:
            if s + p[i] <= caps[k]:
                S.append(i); s += p[i]
        if S:
            key = (k, tuple(sorted(S)))
            if key not in seen:
                seen.add(key); patterns.append(key)
    for rnd in range(max_rounds):
        npat = len(patterns)
        columns = []
        for (k, S) in patterns:
            col = {n + k: 1}
            for i in S:
                col[i] = 1
            columns.append(col)
        for i in range(n):
            columns.append({i: -1})
        art_start = len(columns)
        for i in range(n):
            columns.append({i: 1})
        costs = [Fraction(0)] * (npat + n) + [Fraction(1)] * n
        obj, x, dual = simplex_min(costs, columns, n, m, [1] * n + [1] * m, art_start)
        lam = dual[:n]
        mu = [-dual[n + k] for k in range(m)]
        if verbose:
            print(' round', rnd, 'obj', obj, 'pat', npat,
                  'lam', [str(v) for v in lam], 'mu', [str(v) for v in mu])
        if obj == 0:
            return True, obj, dual, npat, rnd
        added = 0
        for k in range(m):
            items = [i for i in range(n) if k in elig[i]]
            val, S = knapsack(lam, p, caps[k], items)
            if val > mu[k] + Fraction(1, 10**12) and S:
                key = (k, tuple(sorted(S)))
                if key not in seen:
                    seen.add(key); patterns.append(key); added += 1
        if added == 0:
            return False, obj, dual, npat, rnd
    raise RuntimeError('column generation did not converge')
