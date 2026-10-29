"""Deliberately independent reference solver (no est propagation; c-vector)."""
import sys
sys.path.insert(0, '..')
import exp_da as E


def ref_feasible(inst, S, A, c, H, nodecap=2_000_000):
    n, p, m = inst['n'], inst['p'], len(A)
    full = (1 << n) - 1
    if max(A) > H:
        return False
    memo = set()
    nodes = [0]

    def rec(S, A, c):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if S == full:
            return True
        key = (S, A, c)
        if key in memo:
            return False
        rem = full ^ S
        for i in range(n):
            if (rem >> i) & 1:
                if c[i] >= 0:
                    base = c[i]
                else:
                    base = 0
                    for j in inst['pred'][i]:
                        if c[j] > base:
                            base = c[j]
                if base + p[i] + max(
                        [p[j] + 0 for j in ()] or [0]) > H:
                    pass
        # deadline check via heads_tails (allowed: it is an admissible bound)
        est, q = E.heads_tails(inst, S, c)
        for i in range(n):
            if (rem >> i) & 1 and est[i] + p[i] + q[i] > H:
                memo.add(key)
                return False
        order = sorted([i for i in range(n) if (rem >> i) & 1 and
                        not (inst['pmask'][i] & rem)],
                       key=lambda i: (-q[i]))
        for i in order:
            base = 0
            for j in inst['pred'][i]:
                if c[j] > base:
                    base = c[j]
            for k in range(m):
                t = max(A[k], base)
                if t + p[i] > H:
                    continue
                nA = list(A); nA[k] = t + p[i]; nA = tuple(sorted(nA))
                nc = list(c); nc[i] = t + p[i]
                if rec(S | (1 << i), nA, tuple(nc)):
                    return True
        memo.add(key)
        return False

    try:
        return rec(S, tuple(A), tuple(c))
    except TimeoutError:
        return None


def verify_schedule(inst, S0, A0, c0, H, sched):
    """Replay (task, machine, start) from scratch; independent of the search."""
    n, p, m = inst['n'], inst['p'], len(A0)
    A = list(A0)
    comp = {}
    for j in range(n):
        if (S0 >> j) & 1:
            comp[j] = c0[j]
    for (i, k, t) in sched:
        if i in comp:
            return False
        if not (0 <= k < m):
            return False
        if t < A[k]:
            return False
        for j in inst['pred'][i]:
            if j not in comp:
                return False
            if comp[j] > t:
                return False
        # no overlap with any task already placed on k is implied by A[k]
        A[k] = t + p[i]
        comp[i] = t + p[i]
        if t + p[i] > H:
            return False
    if len(comp) != n:
        return False
    return max(comp.values()) <= H
