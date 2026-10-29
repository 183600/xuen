"""Cheap constraint-programming explanations for the scheduling model.

These are *valid* NO certificates that do not need an LP:

  path       est_i + p_i + q_i > h
  timetable  mandatory load at a time point exceeds m
  energy     mandatory energy in a window [a,b) exceeds m*(b-a)
  empty      a task has no allowed start left

The energy certificate stores only the window; the verifier recomputes every
mandatory overlap from the precedence heads/tails.  Eligibility only weakens
the bound (we use total machine capacity m), so the rules remain sound with
heterogeneous machines.
"""
import sys
import random
sys.path[:0] = ['exp/v13']
from po import heads_tails


def _overlap(s, p, a, b):
    return max(0, min(s + p, b) - max(s, a))


def allowed_sets(inst, h, forbid=None):
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    forbid = set(forbid or ())
    out = []
    for i in range(n):
        lo, hi = est[i], h - q[i] - p[i]
        A = [t for t in range(lo, hi + 1) if (i, t) not in forbid]
        out.append(A)
    return est, q, out


def cp_conflict(inst, h, forbid=None, budget=None, seed=0):
    est, q, allowed = allowed_sets(inst, h, forbid)
    n, m, p = inst['n'], inst['m'], inst['p']
    for i in range(n):
        if not allowed[i]:
            return dict(kind='empty', job=i)
    r = [A[0] for A in allowed]
    d = [A[-1] for A in allowed]
    for i in range(n):
        if r[i] + p[i] + q[i] > h:
            return dict(kind='path', job=i)
    # timetable
    prof = [0] * (h + 2)
    for i in range(n):
        if d[i] < r[i] + p[i]:
            for t in range(max(0, d[i]), min(h, r[i] + p[i])):
                prof[t] += 1
    for t in range(h):
        if prof[t] > m:
            return dict(kind='timetable', t=t, load=prof[t])
    # Energetic reasoning is piecewise linear in (a,b): its breakpoints are
    # the task interval endpoints.  The maximum over the integer grid is
    # therefore attained at a pair of breakpoints, so O(n^3) enumeration is
    # exact and much cheaper than O(T^2 n) when T grows.
    B = {0, h}
    for i in range(n):
        for x in (r[i], d[i], r[i] + p[i], d[i] + p[i]):
            B.add(max(0, min(h, x)))
    B = sorted(B)
    pairs = [(a, b) for ia, a in enumerate(B) for b in B[ia + 1:]]
    if budget is not None:
        if budget <= 0:
            return None
        if budget < len(pairs):
            pairs = random.Random(seed).sample(pairs, budget)
    best = (-1, 0, 0, 0)
    for a, b in pairs:
        tot = 0
        for i in range(n):
            tot += min(_overlap(r[i], p[i], a, b),
                       _overlap(d[i], p[i], a, b))
        v = tot - m * (b - a)
        if v > best[0]:
            best = (v, a, b, tot)
    if best[0] > 0:
        return dict(kind='energy', a=best[1], b=best[2],
                    viol=best[0], energy=best[3])
    return None


def verify_cp(inst, h, cert, forbid=None):
    if not cert:
        return False
    est, q, allowed = allowed_sets(inst, h, forbid)
    n, m, p = inst['n'], inst['m'], inst['p']
    r = [A[0] if A else None for A in allowed]
    d = [A[-1] if A else None for A in allowed]
    k = cert.get('kind')
    if k == 'empty':
        i = cert['job']
        return 0 <= i < n and not allowed[i]
    if k == 'path':
        i = cert['job']
        return 0 <= i < n and r[i] is not None and r[i] + p[i] + q[i] > h
    if k == 'timetable':
        t = cert['t']
        if not (0 <= t < h):
            return False
        load = 0
        for i in range(n):
            if r[i] is not None and d[i] < r[i] + p[i] \
                    and d[i] <= t < r[i] + p[i]:
                load += 1
        return load > m
    if k == 'energy':
        a, b = cert['a'], cert['b']
        if not (0 <= a < b <= h):
            return False
        tot = 0
        for i in range(n):
            if r[i] is None:
                return False
            tot += min(_overlap(r[i], p[i], a, b),
                       _overlap(d[i], p[i], a, b))
        return tot > m * (b - a)
    return False
