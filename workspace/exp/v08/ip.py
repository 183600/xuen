"""Integer-programming lower bounds for P|prec|Cmax.

L_E   : volume / LP bound            (v0.7)
L_DFF : harmonic dual-feasible bound (cheap integrality-aware)
L_PACK: exact assignment-relaxation bound (bin packing with eligibility)
"""
import sys, math
sys.path.insert(0, '..'); sys.path.insert(0, '.'); sys.path.insert(0, '../v07')
import exp_da as E
from kern import bits


def dff_lb(inst, S, A, c):
    """max_t t*ceil(sum_i floor(p_i/t)/m), valid for any state."""
    n, p, m = inst['n'], inst['p'], inst['m']
    R = [i for i in range(n) if not ((S >> i) & 1)]
    if not R:
        return max(A)
    best = max(A)
    for t in range(1, max(p[i] for i in R) + 1):
        st = sum(p[i] // t for i in R)
        lb = t * ((st + m - 1) // m)
        if lb > best:
            best = lb
    return best


def _pack2(sizes, caps):
    if not sizes:
        return True
    tot = sum(sizes)
    if tot > caps[0] + caps[1]:
        return False
    lo = max(0, tot - caps[1]); hi = caps[0]
    if lo > hi:
        return False
    b = 1
    for s in sizes:
        b |= b << s
    mask = ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)
    return (b & mask) != 0


def pack_feas(inst, S, A, c, H):
    """Exact assignment relaxation with eligibility, at horizon H."""
    n, p, m = inst['n'], inst['p'], len(A)
    est, q = E.heads_tails(inst, S, c)
    caps = [H - A[k] for k in range(m)]
    if any(x < 0 for x in caps):
        return False
    flex = []
    for i in range(n):
        if (S >> i) & 1:
            continue
        el = [k for k in range(m) if max(A[k], est[i]) + p[i] + q[i] <= H]
        if not el:
            return False
        if len(el) == 1:
            k = el[0]
            if p[i] > caps[k]:
                return False
            caps[k] -= p[i]
        else:
            flex.append(i)
    if m == 2:
        return _pack2([p[i] for i in flex], caps)
    items = []
    for i in flex:
        el = [k for k in range(m) if max(A[k], est[i]) + p[i] + q[i] <= H]
        items.append((len(el), -p[i], i, el))
    items.sort()
    bins = caps[:]
    ln = len(items)
    def dfs(idx):
        if idx == ln:
            return True
        _, negp, i, el = items[idx]
        s = -negp
        for k in el:
            if bins[k] < s:
                continue
            bins[k] -= s
            if dfs(idx + 1):
                bins[k] += s
                return True
            bins[k] += s
        return False
    return dfs(0)


def pack_lb(inst, S, A, c, lo, hi):
    """Smallest H in [lo,hi] with pack_feas; hi+1 if none."""
    if pack_feas(inst, S, A, c, lo):
        return lo
    if not pack_feas(inst, S, A, c, hi):
        return hi + 1
    a, b = lo, hi
    while a < b:
        mid = (a + b) // 2
        if pack_feas(inst, S, A, c, mid):
            b = mid
        else:
            a = mid + 1
    return a


def pack_feas_mask(inst, mask, A, est, q, H):
    """pack_feas restricted to `mask` (same A/est/q)."""
    n, p, m = inst['n'], inst['p'], len(A)
    caps = [H - A[k] for k in range(m)]
    if any(x < 0 for x in caps):
        return False
    flex = []
    for i in bits(mask):
        el = [k for k in range(m) if max(A[k], est[i]) + p[i] + q[i] <= H]
        if not el:
            return False
        if len(el) == 1:
            k = el[0]
            if p[i] > caps[k]:
                return False
            caps[k] -= p[i]
        else:
            flex.append(i)
    if m == 2:
        return _pack2([p[i] for i in flex], caps)
    items = []
    for i in flex:
        el = [k for k in range(m) if max(A[k], est[i]) + p[i] + q[i] <= H]
        items.append((len(el), -p[i], i, el))
    items.sort()
    bins = caps[:]
    ln = len(items)
    def dfs(idx):
        if idx == ln:
            return True
        _, negp, i, el = items[idx]
        s = -negp
        for k in el:
            if bins[k] < s:
                continue
            bins[k] -= s
            if dfs(idx + 1):
                bins[k] += s
                return True
            bins[k] += s
        return False
    return dfs(0)


def pack_core(inst, S, A, c, H):
    """Greedy minimal infeasible subset at horizon H, or None if feasible."""
    n = inst['n']
    est, q = E.heads_tails(inst, S, c)
    K = ((1 << n) - 1) ^ S
    if pack_feas_mask(inst, K, A, est, q, H):
        return None
    for i in list(bits(K)):
        K2 = K & ~(1 << i)
        if K2 and not pack_feas_mask(inst, K2, A, est, q, H):
            K = K2
    return K
