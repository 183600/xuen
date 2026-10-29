"""WOS: Word-level OS.  v3.0 kernel.

The node state is a *word*, not a tuple of containers:

    CP = sum_t c(t) * 2^(cw*t)        capacity profile, cw = bit_length(m)
    RP = sum_i r_i * 2^(rw*i)         release vector,     rw = bit_length(max(h,est))
    M  = remaining-job mask           RDY = ready set

Every node operation is a constant number of word (big-int) operations:

  * EARLIEST  -- run-of-p-ones search by doubling on the derived bitmap AV
  * PLACE     -- ONE subtraction  CP -= rep[p] << (cw*t)
  * AV        -- derived, not stored:  AV = OR_{k<cw} (CP >> k) & ONES

PLACE is exact because EARLIEST only returns t when every field in
[t, t+p) is >= 1, so the single multi-field subtraction never borrows.
"""
import sys
sys.path[:0] = ['exp/v13']


def sgs_solve(inst, h, rem=None, A=None, est=None, q=None, nodecap=200000,
              order='lpt', rsi=True, stats=None):
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
    cw = max(1, m.bit_length())
    rw = max(1, max([h] + list(est)).bit_length())
    rmask = (1 << rw) - 1
    d = [h - q[i] for i in range(n)]
    tasks = [i for i in range(n) if (rem >> i) & 1]
    cap0 = [sum(1 for k in range(m) if A[k] <= t) for t in range(h)]
    cp0 = 0
    for t in range(h):
        cp0 |= cap0[t] << (cw * t)
    rp0 = 0
    for i in tasks:
        rp0 |= est[i] << (rw * i)
    pc0 = 0
    rdy0 = 0
    for i in tasks:
        c = len([j for j in inst['pred'][i] if (rem >> j) & 1])
        pc0 |= c << (4 * i)
        if c == 0:
            rdy0 |= 1 << i
    succm = {i: [j for j in inst['succ'][i] if (rem >> j) & 1] for i in tasks}
    ONES = 0
    for t in range(h):
        ONES |= 1 << (cw * t)
    rep = [0] * (max(p) + 2)
    for k in range(1, len(rep)):
        rep[k] = (rep[k - 1] << cw) | 1
    kshift = cw * h
    mshift = kshift + rw * n
    seen = set()
    nodes = [0]
    rsi_hits = [0]
    put = seen.add
    get = seen.__contains__
    sched = {}

    def dfs(mask, cp, rp, pc, rdy):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if mask == 0:
            return True
        key = cp | (rp << kshift) | (mask << mshift)
        if key in seen:
            return False
        # AV: bit cw*u set iff c(u)>0
        av = cp
        k = 1
        while k < cw:
            av |= cp >> k
            k += 1
        av &= ONES
        cand = []
        r = rdy
        while r:
            lb = r & -r
            i = lb.bit_length() - 1
            r ^= lb
            pi = p[i]
            ri = (rp >> (rw * i)) & rmask
            last = d[i] - pi
            if last < ri:
                if rsi:
                    rsi_hits[0] += 1
                    seen.add(key)
                    return False
                continue
            x = av >> (cw * ri)
            if not x:
                if rsi:
                    rsi_hits[0] += 1
                    seen.add(key)
                    return False
                continue
            rr = x
            L = 1
            okrun = True
            while 2 * L <= pi:
                rr &= rr >> (cw * L)
                if not rr:
                    okrun = False
                    break
                L <<= 1
            if okrun and L < pi:
                rr &= rr >> (cw * (pi - L))
            if not okrun or not rr:
                if rsi:
                    rsi_hits[0] += 1
                    seen.add(key)
                    return False
                continue
            t = ri + (((rr & -rr).bit_length() - 1) // cw)
            if t > last:
                if rsi:
                    rsi_hits[0] += 1
                    seen.add(key)
                    return False
                continue
            cand.append((i, t))
        if not cand:
            seen.add(key)
            return False
        if order == 'lpt':
            cand.sort(key=lambda it: (-p[it[0]], d[it[0]]))
        elif order == 'edd':
            cand.sort(key=lambda it: (d[it[0]], -p[it[0]]))
        elif order == 'spt':
            cand.sort(key=lambda it: (p[it[0]], d[it[0]]))
        for i, t in cand:
            ncp = cp - (rep[p[i]] << (cw * t))
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
            if dfs(mask ^ (1 << i), ncp, nrp, npc, nrdy):
                return True
            del sched[i]
        seen.add(key)
        return False

    try:
        ok = dfs(rem, cp0, rp0, pc0, rdy0)
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes[0]
        stats['memo'] = len(seen)
        stats['rsi_hits'] = rsi_hits[0]
    return ok, dict(sched)
