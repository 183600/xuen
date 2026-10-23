"""GREEDY: sound YES certificate (list scheduling with several priorities)."""
import sys, random
sys.path[:0] = ['exp/v13']
import po


def schedule(inst, h, priority, order_machines=True):
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = po.heads_tails(inst, 0, [0] * n)
    d = [h - q[i] for i in range(n)]
    avail = [0] * m
    fin = [-1] * n
    uns = (1 << n) - 1
    sched = [None] * n
    for _ in range(n):
        ready = []
        u = uns
        while u:
            lb = u & -u; i = lb.bit_length() - 1; u ^= lb
            if all(fin[j] >= 0 for j in inst['pred'][i]):
                ready.append(i)
        if not ready:
            return None
        best = None
        for i in ready:
            ei = max(est[i], max((fin[j] for j in inst['pred'][i]), default=0))
            for k in inst['elig'][i]:
                t = max(avail[k], ei)
                if t + p[i] <= d[i]:
                    key = (priority(i), t, k)
                    if best is None or key < best[0]:
                        best = (key, i, k, t)
        if best is None:
            return None
        _, i, k, t = best
        sched[i] = (t, k)
        fin[i] = t + p[i]; avail[k] = t + p[i]; uns ^= 1 << i
    return sched


def verify(inst, h, sched):
    n, p = inst['n'], inst['p']
    if any(x is None for x in sched):
        return False
    est, q = po.heads_tails(inst, 0, [0] * n)
    d = [h - q[i] for i in range(n)]
    mach = [[] for _ in range(inst['m'])]
    for i, (t, k) in enumerate(sched):
        if k not in inst['elig'][i]: return False
        mach[k].append((t, t + p[i], i))
    for k in range(inst['m']):
        mach[k].sort()
        for a, b in zip(mach[k], mach[k][1:]):
            if a[1] > b[0]: return False
    end = [sched[i][0] + p[i] for i in range(n)]
    for j in range(n):
        for i in inst['pred'][j]:
            if end[i] > sched[j][0]: return False
    return all(sched[i][0] >= est[i] and sched[i][0] + p[i] <= d[i]
               for i in range(n))


def solve(inst, h, tries=200, seed=1):
    n, p = inst['n'], inst['p']
    est, q = po.heads_tails(inst, 0, [0] * n)
    d = [h - q[i] for i in range(n)]
    rules = [
        lambda i: d[i],
        lambda i: d[i] - p[i],
        lambda i: -p[i],
        lambda i: p[i],
        lambda i: -(p[i] + q[i]),
        lambda i: est[i],
    ]
    for f in rules:
        s = schedule(inst, h, f)
        if s is not None and verify(inst, h, s):
            return s
    rng = random.Random(seed)
    for _ in range(tries):
        pri = [rng.random() for _ in range(n)]
        s = schedule(inst, h, lambda i: pri[i])
        if s is not None and verify(inst, h, s):
            return s
    return None
