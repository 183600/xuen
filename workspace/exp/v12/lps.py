"""Three relaxations used in the v1.2 audit.

assignment_lp : x_{ik}, per-machine weighted capacity (sound, poly-size)
config_lp     : per-machine configuration LP (sound, stronger; exponential
                columns, enumerated for n <= 12 here)
old_lp        : v1.1's machine-blind column LP (exp/v09/lp.py)
"""
from simplex import feasible


def assignment_lp(p, caps, elig):
    n = len(p); m = len(caps)
    cols = []
    for i in range(n):
        for k in elig[i]:
            cols.append({i: 1, n + k: p[i]})
    if not cols:
        return False
    ok, x = feasible(cols, n, m, [1] * n + list(caps))
    return ok


def config_lp(p, caps, elig):
    """Per-machine configuration LP.

    y_{k,S} >= 0 for S subset of E_k with p(S) <= C_k.
    sum_{k,S ni i} y = 1,  sum_S y_{k,S} <= 1,  min sum y.
    Feasibility == (min sum y <= m), but with sum_S y <= 1 per machine the
    total is automatically <= m, so phase-1 feasibility is exactly the test.
    """
    n = len(p); m = len(caps)
    # group items by eligibility signature to cut enumeration
    groups = {}
    for i in range(n):
        groups.setdefault(tuple(elig[i]), []).append(i)
    # Enumerate patterns per machine; n <= 12 so 2^n is fine.
    cols = []
    for k in range(m):
        idx = [i for i in range(n) if k in elig[i]]
        L = len(idx)
        for mask in range(1, 1 << L):
            s = 0
            col = {n + k: 1}
            ok = True
            for b in range(L):
                if (mask >> b) & 1:
                    i = idx[b]
                    s += p[i]
                    if s > caps[k]:
                        ok = False
                        break
                    col[i] = 1
            if ok and s <= caps[k]:
                cols.append(col)
    if not cols:
        return False
    ok, x = feasible(cols, n, m, [1] * n + [1] * m)
    return ok
