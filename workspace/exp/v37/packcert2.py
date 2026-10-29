"""PACK-CERT/2: nonpreemptive window packing with compulsory parts.

For a window [a,b):
  S_full = { i : r_i >= a, d_i <= b }          must run entirely inside
  for i not in S_full, the compulsory part
      [d_i - p_i, r_i + p_i)                   must run inside
  is subtracted from the capacity profile.  Then ask whether S_full can be
  packed nonpreemptively into the residual profile.  The test keeps the
  indivisibility that energy inequalities discard.
"""
import sys, time
sys.path[:0] = ['exp/v13']


def profile_available(cap, s, p):
    for t in range(s, s + p):
        if cap[t] <= 0:
            return False
    return True


def place(cap, s, p, d):
    for t in range(s, s + p):
        cap[t] += d


def profile_packable(items, cap, L, nodecap=200000):
    """Exact cumulative packing of items into profile cap[0:L]."""
    items = sorted(items, reverse=True)
    n = len(items)
    # quick energy / max checks
    if sum(items) > sum(cap):
        return False
    if items and items[0] > L:
        return False
    cap = list(cap)
    nodes = [0]
    seen = set()

    def rec(k):
        nodes[0] += 1
        if nodes[0] > nodecap:
            return None
        if k == n:
            return True
        # remaining energy bound
        if sum(items[k:]) > sum(cap):
            return False
        key = (k, tuple(cap))
        if key in seen:
            return False
        rem = items[k]
        tried = set()
        for s in range(0, L - rem + 1):
            # skip identical residual profiles at this start: cheap check on cap slice
            sig = tuple(cap[s:s + rem])
            if sig in tried:
                continue
            tried.add(sig)
            if not profile_available(cap, s, rem):
                continue
            place(cap, s, rem, -1)
            r = rec(k + 1)
            place(cap, s, rem, +1)
            if r is True:
                return True
            if r is None:
                return None
        seen.add(key)
        return False

    return rec(0)


def check(inst, h, est, q, stats=None, nodecap=200000):
    n, m, p = inst['n'], inst['m'], inst['p']
    r = [est[i] for i in range(n)]
    d = [h - q[i] for i in range(n)]
    rs = sorted(set(r)); ds = sorted(set(d))
    tested = 0; t0 = time.time()
    for a in rs:
        for b in ds:
            if b <= a:
                continue
            L = b - a
            S = [i for i in range(n) if r[i] >= a and d[i] <= b]
            if sum(p[i] for i in S) > m * L:
                if stats is not None:
                    stats['pack2'] = ('energy', a, b, S, L, sum(p[i] for i in S), m * L)
                return False
            cap = [m] * L
            for i in range(n):
                if i in S:
                    continue
                lo = max(a, d[i] - p[i])
                hi = min(b, r[i] + p[i])
                for t in range(lo, hi):
                    cap[t - a] -= 1
            if min(cap) < 0:
                # compulsory parts already overload
                if stats is not None:
                    stats['pack2'] = ('mand', a, b, S, L)
                return False
            if not S:
                continue
            if sum(p[i] for i in S) > sum(cap):
                if stats is not None:
                    stats['pack2'] = ('energy2', a, b, S, L, sum(p[i] for i in S), sum(cap))
                return False
            if sum(p[i] for i in S) <= sum(cap) * 0.5 and max(p[i] for i in S) <= max(cap):
                # likely packable; skip exact test only when a simple greedy works
                pass
            tested += 1
            ok = profile_packable([p[i] for i in S], cap, L, nodecap)
            if ok is False:
                if stats is not None:
                    stats['pack2'] = ('packing', a, b, S, L, sum(p[i] for i in S), sum(cap))
                    stats['pack2_us'] = (time.time() - t0) * 1e6
                return False
            if ok is None:
                # budget hit: inconclusive
                continue
    if stats is not None:
        stats['pack2_tested'] = tested
        stats['pack2_us'] = (time.time() - t0) * 1e6
    return True
