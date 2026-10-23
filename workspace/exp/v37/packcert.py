"""PACK-CERT: exact nonpreemptive bin-packing certificate on a window.

For a window [a,b), every job i with r_i>=a and d_i<=b must be processed
entirely inside [a,b).  If those jobs cannot be packed into m bins of
capacity b-a, the instance is infeasible.  This is strictly stronger than
the aggregate energy inequality sum p_i <= m(b-a): it keeps the
indivisibility that the energy bound discards.
"""
import sys, functools, time
sys.path[:0] = ['exp/v13']


def packable(items, m, L, stats=None):
    """Exact bin packing: can items (list of ints) fit in m bins of size L?"""
    if not items:
        return True
    if max(items) > L:
        return False
    if sum(items) > m * L:
        return False
    items = sorted(items, reverse=True)
    # FFD is a *sufficient* test only: success proves packability.
    loads = [0] * m
    ffd_ok = True
    for x in items:  # first-fit decreasing
        for k in range(m):
            if loads[k] + x <= L:
                loads[k] += x
                break
        else:
            ffd_ok = False
            break
    if ffd_ok:
        return True
    # exact DFS with symmetry breaking
    bins = [0] * m
    n = len(items)
    # prune: if remaining total fits in current free capacity (always true)
    seen = set()
    def rec(k):
        if k == n:
            return True
        x = items[k]
        used = set()
        for j in range(m):
            if bins[j] in used:
                continue
            used.add(bins[j])
            if bins[j] + x <= L:
                bins[j] += x
                if rec(k + 1):
                    return True
                bins[j] -= x
            if bins[j] == 0:
                break
        return False
    return rec(0)


def windows(inst, h, est, q):
    n, m, p = inst['n'], inst['m'], inst['p']
    r = [est[i] for i in range(n)]
    d = [h - q[i] for i in range(n)]
    rs = sorted(set(r)); ds = sorted(set(d))
    out = []
    for a in rs:
        for b in ds:
            if b <= a:
                continue
            S = [i for i in range(n) if r[i] >= a and d[i] <= b]
            if not S:
                continue
            L = b - a
            tot = sum(p[i] for i in S)
            if tot <= m * L:
                out.append((a, b, S, L, tot))
    return out


def check(inst, h, est, q, stats=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    tested = 0; t0 = time.time()
    for a, b, S, L, tot in windows(inst, h, est, q):
        # only windows that are tight enough to have a chance
        if tot <= (m - 1) * L:
            continue
        tested += 1
        if not packable([p[i] for i in S], m, L):
            if stats is not None:
                stats['pack_cert'] = dict(a=a, b=b, S=S, L=L, need=tot)
                stats['pack_tested'] = tested
                stats['pack_us'] = (time.time() - t0) * 1e6
            return False
    if stats is not None:
        stats['pack_tested'] = tested
        stats['pack_us'] = (time.time() - t0) * 1e6
    return True
