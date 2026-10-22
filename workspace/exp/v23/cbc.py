"""Clique Bound Certificate (CBC): pairwise machine-incompatibility graph.

Two remaining tasks i,j are *incompatible* if no single machine can run both
within their windows [est_i, h-q_i], [est_j, h-q_j], respecting precedence and
eligibility.  A clique of size m+1 therefore needs m+1 distinct machines and
certifies infeasibility.  This is a graph-only, polynomial-per-pair bound; the
clique search is a small branch-and-bound with a greedy-coloring upper bound.
"""

def incompat_graph(inst, rem, est, q, h):
    n = inst['n']; p = inst['p']; desc = inst['desc']; elig = inst['elig']
    tasks = [i for i in range(n) if (rem >> i) & 1]
    k = len(tasks)
    pos = {v: j for j, v in enumerate(tasks)}
    adj = [0] * k
    # precompute eligibility bitmasks
    em = []
    for i in tasks:
        z = 0
        for kk in elig[i]: z |= 1 << kk
        em.append(z)
    def one(a, b):
        # a before b on one machine
        if (desc[b] >> a) & 1:       # b must precede a
            return False
        ca = est[a] + p[a]
        if ca > h - q[a]:
            return False
        sb = ca if ca > est[b] else est[b]
        cb = sb + p[b]
        return cb <= h - q[b]
    for ai in range(k):
        i = tasks[ai]
        for bj in range(ai + 1, k):
            j = tasks[bj]
            if not (em[ai] & em[bj]):
                bad = True
            else:
                bad = not (one(i, j) or one(j, i))
            if bad:
                adj[ai] |= 1 << bj
                adj[bj] |= 1 << ai
    return tasks, adj

def _color_sort(P, adj):
    """Greedy coloring of the subgraph induced by P; returns (order, bounds)."""
    order = []; bounds = []
    U = P; color = 0
    while U:
        color += 1
        Q = U
        while Q:
            v = (Q & -Q).bit_length() - 1
            Q &= ~(1 << v)
            Q &= ~adj[v]          # proper greedy color class
            U &= ~(1 << v)
            order.append(v); bounds.append(color)
    return order, bounds

def clique_at_least(tasks, adj, target, nodecap=200000):
    """Return a clique of size >= target, or None.  Small Tomita-style B&B."""
    k = len(tasks)
    if target <= 1:
        return tasks[:1]
    best = []
    # greedy incumbent
    order = sorted(range(k), key=lambda v: -adj[v].bit_count())
    greedy = []
    for v in order:
        if all((adj[v] >> u) & 1 for u in greedy):
            greedy.append(v)
    if len(greedy) >= target:
        return [tasks[v] for v in greedy]
    bestn = len(greedy)
    best = greedy[:]
    nodes = 0
    def expand(P, cur):
        nonlocal best, bestn, nodes
        nodes += 1
        if nodes > nodecap:
            return False
        if not P:
            if len(cur) > bestn:
                best = cur[:]; bestn = len(cur)
            return bestn >= target
        order, bounds = _color_sort(P, adj)
        for idx in range(len(order) - 1, -1, -1):
            if len(cur) + bounds[idx] <= bestn:
                return False
            v = order[idx]
            if len(cur) + 1 > bestn:
                best = cur + [v]; bestn = len(cur) + 1
                if bestn >= target:
                    return True
            if expand(P & adj[v], cur + [v]):
                return True
            P &= ~(1 << v)
        return False
    P = (1 << k) - 1
    expand(P, [])
    if bestn >= target:
        return [tasks[v] for v in best]
    return None
