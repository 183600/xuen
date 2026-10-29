"""v2.6e OS-MASK3: fully inlined kernel (no inner runmask/apply/key calls)."""
import sys
sys.path[:0] = ['exp/v13']


def sgs_mask3(inst, h, rem=None, A=None, est=None, q=None, nodecap=300000,
              order='lpt', stats=None, rsi=True, force=True):
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
    succm = {i: [j for j in inst['succ'][i] if (rem >> j) & 1] for i in tasks}
    BIT = [1 << u for u in range(h)]
    BITI = [1 << i for i in range(n)]
    cap0 = [sum(1 for k in range(m) if A[k] <= t) for t in range(h)]
    cp0 = 0
    avail0 = 0
    for t in range(h):
        cp0 |= cap0[t] << (cw * t)
        if cap0[t] > 0:
            avail0 |= BIT[t]
    rp0 = 0
    for i in tasks:
        rp0 |= est[i] << (rw * i)
    pc0 = 0
    rdy0 = 0
    for i in tasks:
        cnt = len([j for j in inst['pred'][i] if (rem >> j) & 1])
        pc0 |= cnt << (4 * i)
        if cnt == 0:
            rdy0 |= BITI[i]
    PL = p
    DL = d
    SL = succm
    BTL = BIT
    BIL = BITI
    nodes = 0
    expanded = 0
    rsi_hits = 0
    force_hits = 0
    no_cand = 0
    seen = set()
    sched = {}
    srp = cw * h
    sm = cw * h + rw * n
    cwL, cmL, rwL, rmL = cw, cmask, rw, rmask

    def dfs(mask, cp, avail, rp, pc, rdy):
        nonlocal nodes, expanded, rsi_hits, force_hits, no_cand
        nodes += 1
        if nodes > nodecap:
            raise TimeoutError
        if mask == 0:
            return True
        key = cp | (rp << srp) | (mask << sm)
        if key in seen:
            return False
        expanded += 1
        cand = []
        forced = None
        r = rdy
        while r:
            low = r & -r
            i = low.bit_length() - 1
            r ^= low
            ri = (rp >> (rwL * i)) & rmL
            pi = PL[i]
            last = DL[i] - pi
            c = 0
            if last >= ri:
                x = avail >> ri
                if x:
                    c = x
                    k = 1
                    while k < pi:
                        c &= (x >> k)
                        if c == 0:
                            break
                        k += 1
                    if c:
                        c &= (1 << (last - ri + 1)) - 1
            if c == 0:
                if rsi:
                    rsi_hits += 1
                    seen.add(key)
                    return False
                continue
            t = ri + (c & -c).bit_length() - 1
            if force and (c & (c - 1)) == 0:
                forced = (i, t)
                break
            cand.append((i, t))
        if forced is not None:
            cand = [(forced[0], forced[1])]
            force_hits += 1
        elif not cand:
            no_cand += 1
            seen.add(key)
            return False
        elif order == 'lpt':
            cand.sort(key=lambda z: (-PL[z[0]], DL[z[0]], z[0]))
        elif order == 'edd':
            cand.sort(key=lambda z: (DL[z[0]], -PL[z[0]], z[0]))
        elif order == 'spt':
            cand.sort(key=lambda z: (PL[z[0]], DL[z[0]], z[0]))
        for i, t in cand:
            pi = PL[i]
            ncp = cp
            navail = avail
            for u in range(t, t + pi):
                v = ((ncp >> (cwL * u)) & cmL) - 1
                ncp -= 1 << (cwL * u)
                if v == 0:
                    navail &= ~BTL[u]
            nrp = rp & ~(rmL << (rwL * i))
            npc = pc
            nrdy = rdy & ~BIL[i]
            bad = False
            for j in SL[i]:
                if (mask >> j) & 1:
                    old = (nrp >> (rwL * j)) & rmL
                    new = t + pi
                    if new > old:
                        nrp += (new - old) << (rwL * j)
                        if new + PL[j] > DL[j]:
                            bad = True
                    v = ((npc >> (4 * j)) & 15) - 1
                    npc -= 1 << (4 * j)
                    if v == 0:
                        nrdy |= BIL[j]
            if bad:
                continue
            sched[i] = t
            if dfs(mask ^ BIL[i], ncp, navail, nrp, npc, nrdy):
                return True
            del sched[i]
        seen.add(key)
        return False

    try:
        ok = dfs(rem, cp0, avail0, rp0, pc0, rdy0)
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes
        stats['expanded'] = expanded
        stats['memo'] = len(seen)
        stats['rsi_hits'] = rsi_hits
        stats['force_hits'] = force_hits
        stats['no_cand'] = no_cand
    return ok, dict(sched)
