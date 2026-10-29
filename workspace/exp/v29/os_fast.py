"""v2.5 OS-BBX: order-space B&B, packed state, RSI pruning.

State = (mask, cp, avail, rp):
  cp    packed capacity profile, 2 bits per time slot (m<=3 => values 0..3)
  avail bit t = 1 iff cp[t] > 0
  rp    packed release vector, 6 bits per task (h<64)
"""
import sys
sys.path[:0] = ['exp/v13']


def sgs_solve(inst, h, rem=None, A=None, est=None, q=None, nodecap=200000,
              order='lpt', rng=None, stats=None, rsi=True, rminkey=False):
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
    predm = {i: sum(1 << j for j in inst['pred'][i] if (rem >> j) & 1)
             for i in tasks}
    succm = {i: [j for j in inst['succ'][i] if (rem >> j) & 1]
             for i in tasks}
    # capacity profile and its packed form
    cap0 = [sum(1 for k in range(m) if A[k] <= t) for t in range(h)]
    cp0 = 0
    avail0 = 0
    for t in range(h):
        cp0 |= cap0[t] << (2 * t)
        if cap0[t] > 0:
            avail0 |= 1 << t
    rp0 = 0
    for i in tasks:
        rp0 |= est[i] << (6 * i)
    slot = [sum(1 << u for u in range(pi)) for pi in range(max(p) + 1)]
    nodes = [0]
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

    def dfs(mask, cp, avail, rp):
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
        ready = [i for i in tasks if (mask >> i) & 1 and not (predm[i] & mask)]
        if rminkey and ready:
            rmin = min((rp >> (6 * i)) & 63 for i in ready)
            key = (mask, cp & ~((1 << (2 * rmin)) - 1), rp)
        else:
            key = (mask, cp, rp)
        if key in seen:
            cur[0] = dep
            return False
        cand = []
        for i in ready:
            t = earliest(avail, (rp >> (6 * i)) & 63, p[i], d[i])
            if t is None:
                if rsi:
                    seen.add(key)
                    cur[0] = dep
                    return False
                continue
            cand.append((i, t))
        if not cand:
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
                v = ((ncp >> (2 * u)) & 3) - 1
                ncp -= 1 << (2 * u)
                if v == 0:
                    navail &= ~(1 << u)
            nrp = rp & ~(63 << (6 * i))
            bad = False
            for j in succm[i]:
                if (mask >> j) & 1:
                    old = (nrp >> (6 * j)) & 63
                    new = t + p[i]
                    if new > old:
                        nrp += (new - old) << (6 * j)
                        if new + p[j] > d[j]:
                            bad = True
            if bad:
                continue
            sched[i] = t
            before = nodes[0]
            if dfs(mask ^ (1 << i), ncp, navail, nrp):
                cur[0] = dep
                return True
            if mask == rem:
                root_sizes.append(nodes[0] - before)
            del sched[i]
        seen.add(key)
        cur[0] = dep
        return False

    try:
        ok = dfs(rem, cp0, avail0, rp0)
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes[0]
        stats['memo'] = len(seen)
        stats['root_sizes'] = root_sizes
        stats['depth_count'] = depth_count
    return ok, dict(sched)
