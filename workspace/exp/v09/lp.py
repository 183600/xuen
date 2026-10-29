"""Fractional (configuration-LP) bin-packing bound + dual weight witness.

tau*(caps) = min sum_S y_S  s.t.  sum_{S ni i} y_S >= 1, y_S >= 0,
             S a subset of items that fits in at least one machine capacity.

Dual:  max sum_i w_i  s.t.  sum_{i in S} w_i <= 1  for every feasible S,  w>=0.
So any w with sum w > (#machines) certifies integer infeasibility.

The LP is solved by full column enumeration + primal simplex (n <= ~14).
"""
INF = float('inf')


def _subsets_fitting(sizes, caps, eligible):
    """All nonempty item subsets that fit (eligible) in at least one machine."""
    n = len(sizes)
    good = []
    worst = max(caps) if caps else -1
    for mask in range(1, 1 << n):
        s = 0
        ok_any = False
        # fast size check first
        idx = [i for i in range(n) if (mask >> i) & 1]
        s = sum(sizes[i] for i in idx)
        if s > worst:
            continue
        for k, C in enumerate(caps):
            if s <= C and all(i in eligible[k] for i in idx):
                ok_any = True
                break
        if ok_any:
            good.append((mask, s))
    return good


def _inv(M):
    n = len(M)
    A = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(M)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(A[r][col]))
        if abs(A[piv][col]) < 1e-12:
            raise ValueError('singular')
        A[col], A[piv] = A[piv], A[col]
        pv = A[col][col]
        A[col] = [x / pv for x in A[col]]
        for r in range(n):
            if r != col and abs(A[r][col]) > 0:
                f = A[r][col]
                A[r] = [a - f * b for a, b in zip(A[r], A[col])]
    return [row[n:] for row in A]


def frac_pack(sizes, caps, eligible=None, max_iter=2000):
    """Return (tau, w, info). tau > m  <=>  fractional LP already infeasible."""
    n = len(sizes)
    caps = [c for c in caps if c >= 0]
    m = len(caps)
    if eligible is None:
        eligible = [set(range(n)) for _ in caps]
    if n == 0:
        return 0.0, [], {'trivial': True}
    for i in range(n):
        if not any(i in eligible[k] and sizes[i] <= caps[k] for k in range(m)):
            return INF, [0.0] * n, {'infeasible_item': i}
    cols = _subsets_fitting(sizes, caps, eligible)
    # distinct 0/1 columns; key by mask
    seen = set(); C = []
    for mask, _ in cols:
        if mask in seen:
            continue
        seen.add(mask)
        C.append(mask)
    # initial basis: singletons (must exist)
    basis = [1 << i for i in range(n)]
    xB = [1.0] * n
    it = 0
    while it < max_iter:
        it += 1
        B = [[1.0 if (basis[j] >> i) & 1 else 0.0 for j in range(n)] for i in range(n)]
        try:
            Binv = _inv(B)
        except ValueError:
            return INF, [0.0] * n, {'singular': True}
        # pi = 1^T Binv
        pi = [sum(Binv[j][i] for j in range(n)) for i in range(n)]
        # reduced cost 1 - pi.a ; pick most negative
        best = 1.0; bestmask = None
        for mask in C:
            val = 0.0
            mm = mask
            while mm:
                b = mm & -mm; i = b.bit_length() - 1; mm ^= b
                val += pi[i]
            if val > best + 1e-12:
                best = val; bestmask = mask
        if bestmask is None:
            w = [max(0.0, x) for x in pi]
            return sum(xB), w, {'iters': it, 'cols': len(C), 'infeasible': False}
        # direction
        a = [((bestmask >> i) & 1) for i in range(n)]
        d = [sum(Binv[r][c] * a[c] for c in range(n)) for r in range(n)]
        theta = INF; leave = -1
        for r in range(n):
            if d[r] > 1e-12:
                t = xB[r] / d[r]
                if t < theta - 1e-12 or (abs(t - theta) <= 1e-12 and basis[r] > basis[leave if leave >= 0 else r]):
                    theta = t; leave = r
        if leave < 0:
            return INF, [0.0] * n, {'unbounded': True}
        xB = [xB[r] - theta * d[r] for r in range(n)]
        xB[leave] = theta
        basis[leave] = bestmask
        if it > 5 and sum(xB) < 1e-9:
            break
    w = [max(0.0, x) for x in pi]
    return sum(xB), w, {'iters': it, 'max_iter': True}


def check_witness(sizes, caps, eligible, w, m, tol=1e-7):
    """Verify: w >= 0, sum w > m, every feasible config has weight <= 1."""
    n = len(sizes)
    if any(x < -tol for x in w):
        return False, 'negative weight'
    if sum(w) <= m + tol:
        return False, 'weight sum not exceeding m'
    for k, C in enumerate(caps):
        # exact-ish knapsack over eligible items with float weights
        items = [(sizes[i], w[i]) for i in range(n) if i in eligible[k] and sizes[i] <= C]
        dp = [0.0] * (C + 1)
        for s, v in items:
            for c in range(C, s - 1, -1):
                if dp[c - s] + v > dp[c]:
                    dp[c] = dp[c - s] + v
        if max(dp) > 1 + tol:
            return False, 'config weight %r > 1 on machine %d' % (max(dp), k)
    return True, 'ok'


def frac_lb(sizes, m, lo, hi, eligible=None):
    """Smallest H in [lo,hi] with tau*(H) <= m ; hi+1 if none."""
    caps_at = lambda H: [H] * m
    if frac_pack(sizes, caps_at(lo), eligible)[0] <= m + 1e-9:
        return lo
    if frac_pack(sizes, caps_at(hi), eligible)[0] > m + 1e-9:
        return hi + 1
    a, b = lo, hi
    while a < b:
        mid = (a + b) // 2
        if frac_pack(sizes, caps_at(mid), eligible)[0] <= m + 1e-9:
            b = mid
        else:
            a = mid + 1
    return a
