"""Order-space SGS decision procedure for PACE states (v2.3 prototype).

State sigma = (R, A, est) with deadline h, full eligibility.
Windows: r_i = est_i, d_i = h - q_i(R).
Capacity profile: c(t) = #{k : A_k <= t}   (exact for full eligibility).

Branching is on the *order* (which ready task is scheduled next); the start
time is not a decision variable -- it is propagated to the earliest feasible
slot (serial schedule generation scheme, SGS).  Every leaf is an active
schedule; by the active-schedule theorem an optimal active schedule exists for
any regular measure, so exhausting orders decides feasibility exactly.
"""
import sys
sys.path[:0] = ['exp/v13']


def _topo(inst, rem):
    n = inst['n']
    indeg = [0] * n
    nodes = [i for i in range(n) if (rem >> i) & 1]
    for i in nodes:
        for j in inst['succ'][i]:
            if (rem >> j) & 1:
                indeg[j] += 1
    q = [i for i in nodes if indeg[i] == 0]
    out = []
    while q:
        u = q.pop()
        out.append(u)
        for v in inst['succ'][u]:
            if (rem >> v) & 1:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
    return out


def sgs_solve(inst, h, rem=None, A=None, est=None, q=None, nodecap=200000,
              dom=False, order='lpt', rng=None, stats=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    if rem is None:
        rem = inst['full']
    if A is None:
        A = tuple([0] * m)
    if est is None or q is None:
        # only valid with A == 0 (root); general states must pass est/q
        import po
        est0, q0 = po.heads_tails(inst, 0, [0] * n)
        est = est if est is not None else est0
        q = q if q is not None else q0
    tasks = [i for i in range(n) if (rem >> i) & 1]
    d = {i: h - q[i] for i in tasks}
    r0 = {i: est[i] for i in tasks}
    predm = {i: sum(1 << j for j in inst['pred'][i] if (rem >> j) & 1) for i in tasks}
    succm = {i: [j for j in inst['succ'][i] if (rem >> j) & 1] for i in tasks}
    cap0 = [sum(1 for k in range(m) if A[k] <= t) for t in range(h)]
    nodes = [0]
    root_sizes = []
    depth_count = []
    cur = [0]
    fails = {}          # mask -> list[(cap, rel)]
    seen = set()
    sched = {}

    def key_rel(mask, rel):
        return tuple(rel[i] for i in tasks if (mask >> i) & 1)

    def dom_leq(c2, r2, cap, rel, mask):
        # (c2, r2) dominates (cap, rel): more capacity, earlier releases
        if any(a < b for a, b in zip(c2, cap)):
            return False
        return all(a <= b for a, b in zip(r2, rel))

    def dominated(mask, cap, rel):
        for c2, r2 in fails.get(mask, ()):
            if dom_leq(c2, r2, cap, rel, mask):
                return True
        return False

    def add_fail(mask, cap, rel):
        lst = fails.setdefault(mask, [])
        if dom:
            if any(dom_leq(c2, r2, cap, rel, mask) for c2, r2 in lst):
                return
            lst[:] = [(c2, r2) for c2, r2 in lst
                      if not dom_leq(cap, rel, c2, r2, mask)]
        lst.append((tuple(cap), tuple(rel)))

    def earliest(cap, t0, pi, hi):
        t = max(t0, 0)
        while t + pi <= hi:
            ok = True
            for u in range(t, t + pi):
                if cap[u] <= 0:
                    ok = False
                    break
            if ok:
                return t
            t += 1
        return None

    def dfs(mask, cap, rel):
        nodes[0] += 1
        dep = cur[0]
        if dep >= len(depth_count):
            depth_count.append(0)
        depth_count[dep] += 1
        cur[0] = dep + 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if mask == 0:
            cur[0] = dep
            return True
        if dom and dominated(mask, cap, rel):
            cur[0] = dep
            return False
        if not dom:
            k = (mask, tuple(cap), key_rel(mask, rel))
            if k in seen:
                cur[0] = dep
                return False
        ready = [i for i in tasks if (mask >> i) & 1 and not (predm[i] & mask)]
        cand = []
        for i in ready:
            t = earliest(cap, rel[i], p[i], d[i])
            if t is not None:
                cand.append((i, t))
        if not cand:
            if dom:
                add_fail(mask, cap, rel)
            else:
                seen.add((mask, tuple(cap), key_rel(mask, rel)))
            cur[0] = dep
            return False
        if rng is not None:
            rng.shuffle(cand)
        elif order == 'lpt':
            cand.sort(key=lambda it: (-p[it[0]], d[it[0]]))
        elif order == 'edd':
            cand.sort(key=lambda it: (d[it[0]], -p[it[0]]))
        elif order == 'spt':
            cand.sort(key=lambda it: (p[it[0]], d[it[0]]))
        for i, t in cand:
            ncap = list(cap)
            for u in range(t, t + p[i]):
                ncap[u] -= 1
            nrel = list(rel)
            for j in succm[i]:
                if (mask >> j) & 1 and t + p[i] > nrel[j]:
                    nrel[j] = t + p[i]
            sched[i] = t
            before = nodes[0]
            if dfs(mask ^ (1 << i), ncap, nrel):
                cur[0] = dep
                return True
            if mask == rem:
                root_sizes.append(nodes[0] - before)
            del sched[i]
        if dom:
            add_fail(mask, cap, rel)
        else:
            seen.add((mask, tuple(cap), key_rel(mask, rel)))
        cur[0] = dep
        return False

    try:
        ok = dfs(rem, cap0, [r0[i] for i in range(n)])
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes[0]
        stats['memo'] = len(seen) + sum(len(v) for v in fails.values())
        stats['root_sizes'] = root_sizes
        stats['depth_count'] = depth_count
    return ok, dict(sched)


def validate(inst, h, sched, A=None):
    """Independent check of a full schedule sched: i -> start."""
    n, m, p, full = inst['n'], inst['m'], inst['p'], inst['full']
    A = A or tuple([0] * m)
    if set(sched) != set(range(n)):
        return False, 'coverage'
    for i in range(n):
        if sched[i] < 0 or sched[i] + p[i] > h:
            return False, 'horizon'
        for j in inst['pred'][i]:
            if sched[i] < sched[j] + p[j]:
                return False, 'precedence'
    free = list(A)
    used = {i: set() for i in range(n)}
    for i in sorted(range(n), key=lambda z: (sched[z], z)):
        cand = [k for k in inst['elig'][i] if free[k] <= sched[i]]
        if not cand:
            return False, 'eligibility'
        # any machine whose last task ends by sched[i]
        cand = [k for k in cand if free[k] <= sched[i]]
        k = min(cand)
        free[k] = sched[i] + p[i]
        used[i].add(k)
    return True, 'ok'
