"""v2.6b OS-MASK2: SWAR capacity decrement + inlined transitions.

CP -= ONES(t,p) does all p field decrements in one subtraction.  The fields
that hit zero are found with the word-parallel trick
    hz = (z - ONES_ALL) & ~z & HI
where HI has the top bit of every cw-bit field.  Only the (few) zero fields
are then translated back to AV bits, so the per-placement Python loop over p
slots disappears.
"""
import sys
sys.path[:0] = ['exp/v13']


def sgs_mask2(inst, h, rem=None, A=None, est=None, q=None, nodecap=300000,
              order='lpt', rng=None, stats=None, rsi=True, force=True):
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
    SHU = [cw * u for u in range(h)]
    ONES_ALL = 0
    HI = 0
    LOWM = 0
    for u in range(h):
        ONES_ALL |= 1 << (cw * u)
        HI |= 1 << (cw * u + cw - 1)
        LOWM |= ((1 << (cw - 1)) - 1) << (cw * u)
    ONES = [[0] * (max(p) + 1 if p else 1) for _ in range(h)]
    for t in range(h):
        acc = 0
        for k in range(len(ONES[t])):
            ONES[t][k] = acc
            if t + k < h:
                acc |= 1 << (cw * (t + k))
    cap0 = [sum(1 for k in range(m) if A[k] <= t) for t in range(h)]
    cp0 = 0
    avail0 = 0
    for t in range(h):
        cp0 |= cap0[t] << SHU[t]
        if cap0[t] > 0:
            avail0 |= BIT[t]
    rp0 = 0
    for i in tasks:
        rp0 |= est[i] << (rw * i)
    pc0 = 0
    rdy0 = 0
    for i in tasks:
        pc0 |= len([j for j in inst['pred'][i] if (rem >> j) & 1]) << (4 * i)
        if not inst['pred'][i] or all(not ((rem >> j) & 1) for j in inst['pred'][i]):
            rdy0 |= BIT[i]
    nodes = [0]
    rsi_hits = [0]
    force_hits = [0]
    no_cand = [0]
    seen = set()
    sched = {}
    shift_rp = cw * h
    shift_m = cw * h + rw * n
    pL = p
    dL = d
    succL = succm
    ONESL = ONES
    ONESA = ONES_ALL
    HIL = HI
    LOWL = LOWM
    BITL = BIT
    cwL = cw
    cmL = cmask
    rwL = rw
    rmL = rmask

    def dfs(depth, mask, cp, avail, rp, pc, rdy):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if mask == 0:
            return True
        key = cp | (rp << shift_rp) | (mask << shift_m)
        if key in seen:
            return False
        # ---- breadth-first sweep over the ready set ----
        cand = []
        forced = None
        r = rdy
        while r:
            low = r & -r
            i = low.bit_length() - 1
            r ^= low
            ri = (rp >> (rwL * i)) & rmL
            pi = pL[i]
            last = dL[i] - pi
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
                    rsi_hits[0] += 1
                    seen.add(key)
                    return False
                continue
            t = ri + (c & -c).bit_length() - 1
            if force and (c & (c - 1)) == 0:
                forced = (i, t)
                break
            cand.append((i, t, c.bit_count()))
        if forced is not None:
            cand = [(forced[0], forced[1], 1)]
        elif not cand:
            no_cand[0] += 1
            seen.add(key)
            return False
        elif rng is not None:
            rng.shuffle(cand)
        elif order == 'lpt':
            cand.sort(key=lambda z: (-pL[z[0]], dL[z[0]], z[0]))
        elif order == 'edd':
            cand.sort(key=lambda z: (dL[z[0]], -pL[z[0]], z[0]))
        elif order == 'spt':
            cand.sort(key=lambda z: (pL[z[0]], dL[z[0]], z[0]))
        elif order == 'mrv':
            cand.sort(key=lambda z: (z[2], -pL[z[0]], dL[z[0]], z[0]))
        if forced is not None:
            force_hits[0] += 1
        for i, t, nb in cand:
            pi = pL[i]
            ncp = cp - ONESL[t][pi]
            # exact per-field zero flags, no borrow across fields
            hz = ~((((ncp & LOWL) + LOWL) | ncp | LOWL)) & HIL
            navail = avail
            while hz:
                b = hz & -hz
                navail &= ~BITL[(b.bit_length() - 1) // cwL]
                hz ^= b
            nrp = rp & ~(rmL << (rwL * i))
            npc = pc
            nrdy = rdy & ~BITL[i]
            bad = False
            for j in succL[i]:
                if (mask >> j) & 1:
                    old = (nrp >> (rwL * j)) & rmL
                    new = t + pi
                    if new > old:
                        nrp += (new - old) << (rwL * j)
                        if new + pL[j] > dL[j]:
                            bad = True
                    v = ((npc >> (4 * j)) & 15) - 1
                    npc -= 1 << (4 * j)
                    if v == 0:
                        nrdy |= BITL[j]
            if bad:
                continue
            sched[i] = t
            if dfs(depth + 1, mask ^ BITL[i], ncp, navail, nrp, npc, nrdy):
                return True
            del sched[i]
        seen.add(key)
        return False

    try:
        ok = dfs(0, rem, cp0, avail0, rp0, pc0, rdy0)
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes[0]
        stats['memo'] = len(seen)
        stats['rsi_hits'] = rsi_hits[0]
        stats['force_hits'] = force_hits[0]
        stats['no_cand'] = no_cand[0]
    return ok, dict(sched)
