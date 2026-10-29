"""v2.5 OS-BBX: order-space B&B with RSI pruning and bit-parallel capacity."""
import sys
sys.path[:0] = ['exp/v13']


def sgs_solve(inst, h, rem=None, A=None, est=None, q=None, nodecap=200000,
              dom=False, order='lpt', rng=None, stats=None, rsi=True,
              bit=True, keymode='tuple', atpf=False, chain=False, edf_depth=0, ricc=0):
    n, m, p = inst['n'], inst['m'], inst['p']
    if rem is None:
        rem = inst['full']
    if A is None:
        A = tuple([0] * m)
    if est is None or q is None:
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
    avail0 = 0
    for t in range(h):
        if cap0[t] > 0:
            avail0 |= 1 << t
    nodes = [0]
    root_sizes = []
    depth_count = []
    cur = [0]
    fails = {}
    seen = set()
    sched = {}
    keycap = (lambda c: tuple(c)) if keymode == 'tuple' else (lambda c: bytes(c))

    def key_rel(mask, rel):
        return tuple(rel[i] for i in tasks if (mask >> i) & 1)

    def dom_leq(c2, r2, cap, rel):
        if any(a < b for a, b in zip(c2, cap)):
            return False
        return all(a <= b for a, b in zip(r2, rel))

    def dominated(mask, cap, rel):
        for c2, r2 in fails.get(mask, ()):
            if dom_leq(c2, r2, cap, rel):
                return True
        return False

    def add_fail(mask, cap, rel):
        lst = fails.setdefault(mask, [])
        if dom:
            if any(dom_leq(c2, r2, cap, rel) for c2, r2 in lst):
                return
            lst[:] = [(c2, r2) for c2, r2 in lst if not dom_leq(cap, rel, c2, r2)]
        lst.append((tuple(cap), tuple(rel)))

    if bit:
        def earliest(cap, avail, t0, pi, hi):
            if t0 < 0:
                t0 = 0
            last = hi - pi
            if last < t0:
                return None
            # mask only t >= t0; the run may extend past `last`, so check
            # the start index against `last` *after* finding the run.
            x = avail >> t0
            if x == 0:
                return None
            c = x
            k = 1
            while k < pi:
                c &= (x >> k)
                if c == 0:
                    return None
                k += 1
            s = (c & -c).bit_length() - 1
            if t0 + s > last:
                return None
            return t0 + s

        def place(cap, avail, t, pi):
            nc = cap[:]
            na = avail
            for u in range(t, t + pi):
                v = nc[u] - 1
                nc[u] = v
                if v == 0:
                    na &= ~(1 << u)
            return nc, na
    else:
        def earliest(cap, avail, t0, pi, hi):
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

        def place(cap, avail, t, pi):
            nc = cap[:]
            for u in range(t, t + pi):
                nc[u] -= 1
            return nc, avail

    import heapq

    def edf_ok(remtasks, cap, rel):
        # preemptive EDF relaxation: necessary condition, unit-time simulation
        remp = {i: p[i] for i in remtasks}
        order_r = sorted(remtasks, key=lambda i: rel[i])
        heap = []
        idx = 0
        for t in range(h):
            while idx < len(order_r) and rel[order_r[idx]] <= t:
                j = order_r[idx]; heapq.heappush(heap, (d[j], j)); idx += 1
            c = cap[t]
            while heap and remp[heap[0][1]] == 0:
                heapq.heappop(heap)
            while c > 0 and heap:
                dj, j = heapq.heappop(heap)
                take = c if c < remp[j] else remp[j]
                remp[j] -= take; c -= take
                if remp[j] > 0:
                    heapq.heappush(heap, (dj, j)); break
            while heap and remp[heap[0][1]] == 0:
                heapq.heappop(heap)
            if heap and heap[0][0] <= t:
                return False
        return True

    def dfs(mask, cap, avail, rel):
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
            k = (mask, keycap(cap), key_rel(mask, rel))
            if k in seen:
                cur[0] = dep
                return False
        remtasks = [i for i in tasks if (mask >> i) & 1]
        if chain:
            for i in remtasks:
                if rel[i] + p[i] + q[i] > h:
                    if dom: add_fail(mask, cap, rel)
                    else: seen.add((mask, keycap(cap), key_rel(mask, rel)))
                    cur[0] = dep
                    return False
        if atpf:
            for i in remtasks:
                if earliest(cap, avail, rel[i], p[i], d[i]) is None:
                    if dom: add_fail(mask, cap, rel)
                    else: seen.add((mask, keycap(cap), key_rel(mask, rel)))
                    cur[0] = dep
                    return False
        ready = [i for i in remtasks if not (predm[i] & mask)]
        if ricc and len(ready) <= ricc:
            # Hall/interval cut restricted to the ready set (necessary)
            pc = [0] * (h + 1)
            for t in range(h):
                pc[t + 1] = pc[t] + cap[t]
            ra = sorted(set([rel[i] for i in ready] + [d[i] - p[i] for i in ready]))
            rb = sorted(set([rel[i] + p[i] for i in ready] + [d[i] for i in ready]))
            hit = False
            for a in ra:
                for b in rb:
                    if b <= a:
                        continue
                    D = sum(p[i] for i in ready if rel[i] >= a and d[i] <= b)
                    if D > pc[b] - pc[a]:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                if dom: add_fail(mask, cap, rel)
                else: seen.add((mask, keycap(cap), key_rel(mask, rel)))
                cur[0] = dep
                return False
        if edf_depth and len(remtasks) <= edf_depth:
            if not edf_ok(remtasks, cap, rel):
                if dom: add_fail(mask, cap, rel)
                else: seen.add((mask, keycap(cap), key_rel(mask, rel)))
                cur[0] = dep
                return False
        cand = []
        for i in ready:
            t = earliest(cap, avail, rel[i], p[i], d[i])
            if t is None:
                if rsi:
                    # every ready job must be placeable NOW: cap only shrinks,
                    # rel only grows, so an unplaceable ready job kills the node
                    if dom:
                        add_fail(mask, cap, rel)
                    else:
                        seen.add((mask, keycap(cap), key_rel(mask, rel)))
                    cur[0] = dep
                    return False
                continue
            cand.append((i, t))
        if not cand:
            if dom:
                add_fail(mask, cap, rel)
            else:
                seen.add((mask, keycap(cap), key_rel(mask, rel)))
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
            ncap, navail = place(cap, avail, t, p[i])
            nrel = list(rel)
            bad = False
            for j in succm[i]:
                if (mask >> j) & 1 and t + p[i] > nrel[j]:
                    nrel[j] = t + p[i]
                    if nrel[j] + p[j] > d[j]:
                        bad = True
            if bad:
                continue
            sched[i] = t
            before = nodes[0]
            if dfs(mask ^ (1 << i), ncap, navail, nrel):
                cur[0] = dep
                return True
            if mask == rem:
                root_sizes.append(nodes[0] - before)
            del sched[i]
        if dom:
            add_fail(mask, cap, rel)
        else:
            seen.add((mask, keycap(cap), key_rel(mask, rel)))
        cur[0] = dep
        return False

    try:
        ok = dfs(rem, cap0, avail0, [r0[i] for i in range(n)])
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes[0]
        stats['memo'] = len(seen) + sum(len(v) for v in fails.values())
        stats['root_sizes'] = root_sizes
        stats['depth_count'] = depth_count
    return ok, dict(sched)
