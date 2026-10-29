"""v2.5 OS-BBX/2: packed capacity+release+predcount and an incremental ready set."""
import sys
sys.path[:0] = ['exp/v13']


def sgs_solve(inst, h, rem=None, A=None, est=None, q=None, nodecap=200000,
              order='lpt', rng=None, stats=None, rsi=True):
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
    cw = max(1, m.bit_length())          # capacity field: 0..2^cw-1 >= m
    cmask = (1 << cw) - 1
    rw = max(1, max([h] + list(est)).bit_length())   # release field
    rmask = (1 << rw) - 1
    d = [h - q[i] for i in range(n)]
    r0 = [est[i] for i in range(n)]
    predm = {i: sum(1 << j for j in inst['pred'][i] if (rem >> j) & 1)
             for i in tasks}
    succm = {i: [j for j in inst['succ'][i] if (rem >> j) & 1]
             for i in tasks}
    cap0 = [sum(1 for k in range(m) if A[k] <= t) for t in range(h)]
    cp0 = 0
    avail0 = 0
    for t in range(h):
        cp0 |= cap0[t] << (cw * t)
        if cap0[t] > 0:
            avail0 |= 1 << t
    rp0 = 0
    for i in tasks:
        rp0 |= est[i] << (rw * i)
    pc0 = 0
    rdy0 = 0
    for i in tasks:
        pc0 |= len([j for j in inst['pred'][i] if (rem >> j) & 1]) << (4 * i)
        if not predm[i]:
            rdy0 |= 1 << i
    nodes = [0]
    rsi_hits = [0]
    no_cand = [0]
    root_sizes = []
    depth_count = []
    cur = [0]
    seen = set()
    sched = {}

    def earliest(avail, t0, pi, hi):
        last = hi - pi
        if last < t0:
            return None
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

    def dfs(mask, cp, avail, rp, pc, rdy):
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
        key = (mask, cp, rp)
        if key in seen:
            cur[0] = dep
            return False
        cand = []
        r = rdy
        while r:
            low = r & -r
            i = low.bit_length() - 1
            r ^= low
            t = earliest(avail, (rp >> (rw * i)) & rmask, p[i], d[i])
            if t is None:
                if rsi:
                    rsi_hits[0] += 1
                    seen.add(key)
                    cur[0] = dep
                    return False
                continue
            cand.append((i, t))
        if not cand:
            no_cand[0] += 1
            seen.add(key)
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
            ncp = cp
            navail = avail
            for u in range(t, t + p[i]):
                v = ((ncp >> (cw * u)) & cmask) - 1
                ncp -= 1 << (cw * u)
                if v == 0:
                    navail &= ~(1 << u)
            nrp = rp & ~(rmask << (rw * i))
            npc = pc
            nrdy = rdy & ~(1 << i)
            bad = False
            for j in succm[i]:
                if (mask >> j) & 1:
                    old = (nrp >> (rw * j)) & rmask
                    new = t + p[i]
                    if new > old:
                        nrp += (new - old) << (rw * j)
                        if new + p[j] > d[j]:
                            bad = True
                    v = ((npc >> (4 * j)) & 15) - 1
                    npc -= 1 << (4 * j)
                    if v == 0:
                        nrdy |= 1 << j
            if bad:
                continue
            sched[i] = t
            before = nodes[0]
            if dfs(mask ^ (1 << i), ncp, navail, nrp, npc, nrdy):
                cur[0] = dep
                return True
            if mask == rem:
                root_sizes.append(nodes[0] - before)
            del sched[i]
        seen.add(key)
        cur[0] = dep
        return False

    try:
        ok = dfs(rem, cp0, avail0, rp0, pc0, rdy0)
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes[0]
        stats['memo'] = len(seen)
        stats['rsi_hits'] = rsi_hits[0]
        stats['no_cand'] = no_cand[0]
        stats['root_sizes'] = root_sizes
        stats['depth_count'] = depth_count
    return ok, dict(sched)
