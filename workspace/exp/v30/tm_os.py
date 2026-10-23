"""v3.0 TM-OS: OS kernel with an *energetic prefix cut* (EPC) at every node.

This is the round-1 prototype.  It keeps v2.5's packed state (mask, CP, RP)
and RSI, and adds a second, aggregate necessary condition:

  for every deadline threshold b, with S_b = {i in R : d_i <= b},
      sum_{i in S_b} p_i  <=  C(min_{i in S_b} r_i, b)

and its time-reversed twin over release thresholds.  `pref` is the capacity
prefix sum, maintained incrementally.
"""
import sys
sys.path[:0] = ['exp/v13']


def sgs_solve(inst, h, rem=None, A=None, est=None, q=None, nodecap=200000,
              order='lpt', rsi=True, epc='none', canon=False, stats=None):
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
    cw = max(1, m.bit_length())
    cmask = (1 << cw) - 1
    rw = max(1, max([h] + list(est)).bit_length())
    rmask = (1 << rw) - 1
    d = [h - q[i] for i in range(n)]
    predm = {i: sum(1 << j for j in inst['pred'][i] if (rem >> j) & 1)
             for i in tasks}
    succm = {i: [j for j in inst['succ'][i] if (rem >> j) & 1] for i in tasks}
    sucall = {i: list(inst['succ'][i]) for i in range(n)}
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
    pref = [0] * (h + 1)                     # pref[t] = C(0,t)
    for t in range(h):
        pref[t + 1] = pref[t] + cap0[t]

    # deadline order and release order, fixed for this root
    dorder = sorted(tasks, key=lambda i: (d[i], i))
    rorder = sorted(tasks, key=lambda i: (-est[i], i))
    nodes = [0]
    rsi_hits = [0]
    epc_hits = [0]
    epc_saved = [0]
    cache = {}

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

    def epc_dead(mask):
        # groups by deadline, ascending
        dem = 0
        minr = 10 ** 9
        i_prev = None
        for i in dorder:
            if not (mask >> i) & 1:
                continue
            if i_prev is not None and d[i] != d[i_prev]:
                if dem > pref[d[i_prev]] - pref[minr]:
                    return True
            dem += p[i]
            if est[i] < minr:
                minr = est[i]
            i_prev = i
        if i_prev is not None and dem > pref[d[i_prev]] - pref[minr]:
            return True
        return False

    def epc_rel(mask):
        dem = 0
        maxd = -1
        i_prev = None
        for i in rorder:
            if not (mask >> i) & 1:
                continue
            if i_prev is not None and est[i] != est[i_prev]:
                if dem > pref[maxd] - pref[est[i_prev]]:
                    return True
            dem += p[i]
            if d[i] > maxd:
                maxd = d[i]
            i_prev = i
        if i_prev is not None and dem > pref[maxd] - pref[est[i_prev]]:
            return True
        return False

    def dfs(mask, cp, avail, rp, pc, rdy):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if mask == 0:
            return True
        if canon:
            mn = 10 ** 9
            mx = -1
            rr = mask
            while rr:
                lb = rr & -rr
                i = lb.bit_length() - 1
                rr ^= lb
                if est[i] < mn:
                    mn = est[i]
                if d[i] > mx:
                    mx = d[i]
            hull = (((1 << (cw * (mx - mn))) - 1) << (cw * mn)) if mx > mn else 0
            key = (mask, cp & hull, rp)
        else:
            key = (mask, cp, rp)
        if key in cache:
            return cache[key]
        if epc in ('d', 'both') and epc_dead(mask):
            epc_hits[0] += 1
            cache[key] = False
            return False
        if epc in ('r', 'both') and epc_rel(mask):
            epc_hits[0] += 1
            cache[key] = False
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
                    cache[key] = False
                    return False
                continue
            cand.append((i, t))
        if not cand:
            cache[key] = False
            return False
        cand.sort(key=lambda it: (-p[it[0]], d[it[0]]))
        for i, t in cand:
            ncp = cp
            navail = avail
            for u in range(t, t + p[i]):
                v = ((ncp >> (cw * u)) & cmask) - 1
                ncp -= 1 << (cw * u)
                if v == 0:
                    navail &= ~(1 << u)
            for u in range(t + p[i], h + 1):
                pref[u] -= 1
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
            if not bad:
                if dfs(mask ^ (1 << i), ncp, navail, nrp, npc, nrdy):
                    return True
            for u in range(t + p[i], h + 1):
                pref[u] += 1
        cache[key] = False
        return False

    try:
        ok = dfs(rem, cp0, avail0, rp0, pc0, rdy0)
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes[0]
        stats['memo'] = len(cache)
        stats['rsi_hits'] = rsi_hits[0]
        stats['epc_hits'] = epc_hits[0]
        stats['canon'] = canon
    return ok, {}
