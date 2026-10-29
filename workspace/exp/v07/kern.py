"""v0.7 kernel-certificate core: exact feasibility, kernel restriction, MUS.

Key implementation trick: a zero-slack task has latest start == earliest start,
so it is *forced*; restricting the exact DFS to  K + (zero-slack tasks)  while
dropping all other tasks is a relaxation of the H-decision problem.
"""
import sys, time
sys.path.insert(0, '..')
import exp_da as E

INF = 10**9


def bits(mask):
    while mask:
        b = mask & -mask
        yield b.bit_length() - 1
        mask ^= b


def _dfs(inst, A, H, est, q, tasks, nodecap, memo):
    """Exact DFS over `tasks` only.  Returns (feasible, nodes).
    `tasks` is a mask over currently unscheduled tasks; precedence to tasks
    outside `tasks` is ignored (a relaxation when tasks != R)."""
    p, m = inst['p'], len(A)
    nodes = [0]
    pm = inst['pmask']
    suc = inst['succ']

    def rec(rem, A, est):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if rem == 0:
            return True
        key = (rem, A) + tuple(est[i] for i in bits(rem))
        v = memo.get(key)
        if v is not None:
            return v
        for i in bits(rem):
            if est[i] + p[i] + q[i] > H:
                memo[key] = False
                return False
        ready = [i for i in bits(rem) if not (pm[i] & rem)]
        ready.sort(key=lambda i: (H - q[i] - p[i]) - est[i])
        for i in ready:
            for k in range(m):
                t = max(A[k], est[i])
                if t + p[i] + q[i] > H:
                    continue
                nA = list(A); nA[k] = t + p[i]; nA = tuple(sorted(nA))
                nest = list(est)
                for j in suc[i]:
                    if (rem >> j) & 1 and t + p[i] > nest[j]:
                        nest[j] = t + p[i]
                if rec(rem & ~(1 << i), nA, tuple(nest)):
                    memo[key] = True
                    return True
        memo[key] = False
        return False

    ok = rec(tasks, tuple(A), tuple(est))
    return ok, nodes[0]


def feasible_full(inst, S, A, c, H, nodecap=3_000_000, stats=None):
    n = inst['n']
    full = (1 << n) - 1
    if S == full:
        return max(A) <= H
    if max(A) > H:
        return False
    est, q = E.heads_tails(inst, S, c)
    memo = {}
    try:
        ok, nd = _dfs(inst, A, H, est, q, full & ~S, nodecap, memo)
    finally:
        if stats is not None:
            stats['nodes'] = stats.get('nodes', 0) + (nd if 'nd' in dir() else 0)
    return ok


def state_opt(inst, S, A, c, nodecap=3_000_000):
    L0 = E.lower_L0(inst, S, A, c)
    U = E.guide(inst, S, A, c)
    for H in range(max(L0, max(A)), U + 1):
        if feasible_full(inst, S, A, c, H, nodecap=nodecap):
            return H
    return U


def zero_slack(inst, S, c, H):
    est, q = E.heads_tails(inst, S, c)
    n, p = inst['n'], inst['p']
    R = (1 << n) - 1 ^ S
    sl = {}
    for i in bits(R):
        sl[i] = (H - q[i] - p[i]) - est[i]
    bars = 0
    for i in bits(R):
        if sl[i] == 0:
            bars |= 1 << i
    return est, q, sl, bars


def kernel_feasible(inst, S, A, c, H, Kmask, use_bars=True,
                    nodecap=800_000, stats=None):
    """True = no proof found; False = K+forced is infeasible => H infeasible."""
    n = inst['n']
    full = (1 << n) - 1
    if S == full:
        return max(A) <= H
    if max(A) > H:
        return False
    est, q, sl, bars = zero_slack(inst, S, c, H)
    R = full ^ S
    K = Kmask & R
    if any(sl[i] < 0 for i in bits(K)):
        return False
    tasks = K | (bars & R) if use_bars else K
    memo = {}
    try:
        ok, nd = _dfs(inst, A, H, est, q, tasks, nodecap, memo)
    except TimeoutError:
        return None
    if stats is not None:
        stats['nodes'] = stats.get('nodes', 0) + nd
        stats['calls'] = stats.get('calls', 0) + 1
    return ok


def mus(inst, S, A, c, H, use_bars=True, nodecap=800_000, order=None):
    """Greedy minimal infeasible kernel (requires H < state_opt)."""
    full = (1 << inst['n']) - 1
    K = full ^ S
    if kernel_feasible(inst, S, A, c, H, K, use_bars=use_bars, nodecap=nodecap):
        return None
    ids = order if order is not None else list(bits(K))
    for i in ids:
        if not ((K >> i) & 1):
            continue
        K2 = K & ~(1 << i)
        if K2 == 0:
            continue
        r = kernel_feasible(inst, S, A, c, H, K2, use_bars=use_bars, nodecap=nodecap)
        if r is False:
            K = K2
    return K
