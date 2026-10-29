"""Interval Capacity Certificate (ICC), v2.4.

A window [a,b] is a dual certificate for the time-indexed LP relaxation:
every task i with r_i >= a and d_i <= b must execute entirely inside the
window, so sum p_i <= capacity(a,b).  A second form uses the mandatory
overlap of *every* task with the window.

Only NO is ever returned; when no window violates capacity the result is
UNKNOWN (here (True, None)), never a claim of feasibility.
"""
import sys
sys.path[:0] = ['exp/v13']


def _cap_prefix(A, m, h):
    c = [sum(1 for k in range(m) if A[k] <= t) for t in range(h)]
    pc = [0] * (h + 1)
    for t in range(h):
        pc[t + 1] = pc[t] + c[t]
    return c, pc


def icc(inst, rem, A, est, q, h, stats=None):
    """Return (False, witness) if a window cut proves NO, else (True, None).

    witness = ('icc-full', a, b, S_mask, demand, cap) or
              ('icc-mand', a, b, mand_tuple, demand, cap).
    """
    n, p, m = inst['n'], inst['p'], inst['m']
    tasks = [i for i in range(n) if (rem >> i) & 1]
    if not tasks:
        return True, None
    r = {i: est[i] for i in tasks}
    d = {i: h - q[i] for i in tasks}
    c, pc = _cap_prefix(A, m, h)
    starts = sorted(set([r[i] for i in tasks] + [d[i] - p[i] for i in tasks]))
    ends = sorted(set([r[i] + p[i] for i in tasks] + [d[i] for i in tasks]))
    if stats is not None:
        stats['icc_calls'] = stats.get('icc_calls', 0) + 1
        stats['icc_windows'] = stats.get('icc_windows', 0)
    for a in starts:
        if a < 0 or a >= h:
            continue
        for b in ends:
            if b <= a or b > h:
                continue
            C = pc[b] - pc[a]
            if stats is not None:
                stats['icc_windows'] += 1
            # (1) all jobs fully contained in the window
            S = 0
            F = 0
            for i in tasks:
                if r[i] >= a and d[i] <= b:
                    S |= 1 << i
                    F += p[i]
            if F > C:
                w = ('icc-full', a, b, S, F, C)
                if stats is not None:
                    stats['icc_hits'] = stats.get('icc_hits', 0) + 1
                return False, w
            # (2) mandatory overlap of every job with the window
            L = b - a
            M = 0
            vec = []
            for i in tasks:
                v = p[i]
                t = r[i] + p[i] - a
                if t < v:
                    v = t
                t = b - (d[i] - p[i])
                if t < v:
                    v = t
                if L < v:
                    v = L
                if v < 0:
                    v = 0
                vec.append(v)
                M += v
            if M > C:
                w = ('icc-mand', a, b, tuple(vec), M, C)
                if stats is not None:
                    stats['icc_hits'] = stats.get('icc_hits', 0) + 1
                return False, w
    return True, None


def check(inst, rem, A, est, q, h, w):
    """Independent recheck of an ICC witness (recomputes everything)."""
    n, p, m = inst['n'], inst['p'], inst['m']
    tasks = [i for i in range(n) if (rem >> i) & 1]
    r = {i: est[i] for i in tasks}
    d = {i: h - q[i] for i in tasks}
    c, pc = _cap_prefix(A, m, h)
    kind, a, b, payload, demand, cap = w
    if not (0 <= a < b <= h):
        return False
    C = pc[b] - pc[a]
    if C != cap or not (demand > cap):
        return False
    if kind == 'icc-full':
        S = payload
        F = 0
        for i in tasks:
            if (S >> i) & 1:
                if not (r[i] >= a and d[i] <= b):
                    return False
                F += p[i]
        return F == demand and F > cap
    if kind == 'icc-mand':
        vec = list(payload)
        if len(vec) != len(tasks):
            return False
        L = b - a
        M = 0
        for j, i in enumerate(tasks):
            v = p[i]
            t = r[i] + p[i] - a
            if t < v:
                v = t
            t = b - (d[i] - p[i])
            if t < v:
                v = t
            if L < v:
                v = L
            if v < 0:
                v = 0
            if v != vec[j]:
                return False
            M += v
        return M == demand and M > cap
    return False
