"""HEC: Hall energy certificate over eligible machine subsets.

For each non-empty machine subset M' (|M'| = r), a job with E_i subset of M'
can only ever run on M'.  For any window [a,b) the jobs whose whole window lies
inside [a,b), i.e.  est_i >= a and d_i <= b, must all be processed on M' inside
[a,b).  Hence   sum p_i <= r * (b - a)   is necessary.  Violation => NO, with a
witness (M', a, b, S).

Under full eligibility there is only one subset M' = [m] and HEC collapses to
the prefix energetic rule (v3.0's EPC).  Under eligibility it is *strictly*
stronger, and it is the root-level certificate that v3.0's ICC cannot see.
"""
import itertools


def check(inst, h, est, q, stats=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    d = [h - q[i] for i in range(n)]
    E = [set(inst['elig'][i]) for i in range(n)]
    order_d = sorted(range(n), key=lambda i: d[i])
    order_r = sorted(range(n), key=lambda i: -est[i])
    for r in range(1, m + 1):
        for M in itertools.combinations(range(m), r):
            Ms = set(M)
            ids = [i for i in range(n) if E[i] <= Ms]
            if len(ids) < 2:
                continue
            idset = set(ids)
            # deadline sweep: S = {i in ids : d_i <= b}, a = min est(S)
            need = 0
            a = 10 ** 9
            for i in order_d:
                if i not in idset:
                    continue
                need += p[i]
                if est[i] < a:
                    a = est[i]
                b = d[i]
                cap = r * (b - a)
                if cap < need:
                    if stats is not None:
                        stats['hec'] = (M, a, b, need, cap)
                    return False
            # release sweep: S = {i in ids : est_i >= a}, b = max d(S)
            need = 0
            b = -1
            for i in order_r:
                if i not in idset:
                    continue
                need += p[i]
                if d[i] > b:
                    b = d[i]
                a = est[i]
                cap = r * (b - a)
                if cap < need:
                    if stats is not None:
                        stats['hec'] = (M, a, b, need, cap)
                    return False
    return True
