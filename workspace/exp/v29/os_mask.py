"""v2.6 OS-MASK: keep the full feasible-start bitmask `c`, not just its ctz.

One ready-set sweep computes c_i for every ready job i.  From the same c_i:
  - RSI      : c_i == 0                     -> state dead
  - M-FRC    : c_i has exactly one bit      -> i is forced, no branching
  - MRV      : c_i.bit_count()              -> deterministic branch order
All three are O(1) on top of the AND-chain that v2.5 already ran and threw
away.  `intkey` packs (mask, cp, rp) into one Python int for the memo.
"""
import sys
sys.path[:0] = ['exp/v13']


def sgs_mask(inst, h, rem=None, A=None, est=None, q=None, nodecap=300000,
             order='mrv', rng=None, stats=None, rsi=True, force=True,
             intkey=True, closure=False, record=None):
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
    expanded = [0]
    rsi_hits = [0]
    force_hits = [0]
    no_cand = [0]
    seen = set()
    masks = set()
    sched = {}
    shift_rp = cw * h
    shift_m = cw * h + rw * n

    def runmask(avail, t0, pi, hi):
        """bit s of the result = [t0+s, t0+s+pi) all free and t0+s <= hi-pi."""
        last = hi - pi
        if last < t0:
            return 0
        x = avail >> t0
        if x == 0:
            return 0
        c = x
        k = 1
        while k < pi:
            c &= (x >> k)
            if c == 0:
                return 0
            k += 1
        w = last - t0 + 1
        c &= (1 << w) - 1
        return c

    def key_of(mask, cp, rp):
        if intkey:
            return cp | (rp << shift_rp) | (mask << shift_m)
        return (mask, cp, rp)

    def apply(mask, cp, avail, rp, pc, rdy, i, t):
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
        return (mask ^ (1 << i), ncp, navail, nrp, npc, nrdy, bad)

    def scan(rdy, rp, avail):
        """one breadth-first pass over the ready set: returns (cand, forced, dead)."""
        cand = []
        forced = None
        r = rdy
        while r:
            low = r & -r
            i = low.bit_length() - 1
            r ^= low
            ri = (rp >> (rw * i)) & rmask
            c = runmask(avail, ri, p[i], d[i])
            if c == 0:
                if rsi:
                    return None, None, True
                continue
            t = ri + (c & -c).bit_length() - 1
            nb = c.bit_count()
            if force and nb == 1:
                forced = (i, t)
                break
            cand.append((i, t, nb))
        return cand, forced, False

    def dfs(depth, mask, cp, avail, rp, pc, rdy):
        while True:
            nodes[0] += 1
            if nodes[0] > nodecap:
                raise TimeoutError
            if mask == 0:
                return True
            masks.add(mask)
            if record is not None:
                record.append((mask, cp, rp))
            key = key_of(mask, cp, rp)
            if key in seen:
                return False
            cand, forced, dead = scan(rdy, rp, avail)
            if dead:
                rsi_hits[0] += 1
                seen.add(key)
                return False
            if forced is not None:
                force_hits[0] += 1
                i, t = forced
                mask, cp, avail, rp, pc, rdy, bad = apply(
                    mask, cp, avail, rp, pc, rdy, i, t)
                if bad:
                    seen.add(key)
                    return False
                sched[i] = t
                if mask == 0:
                    return True
                if not closure:
                    # lazy forcing: the forced child is the only child; recurse
                    if dfs(depth + 1, mask, cp, avail, rp, pc, rdy):
                        return True
                    del sched[i]
                    seen.add(key)
                    return False
                continue          # closure: propagate at the same node
            if not cand:
                no_cand[0] += 1
                seen.add(key)
                return False
            if rng is not None:
                rng.shuffle(cand)
            elif order == 'mrv':
                cand.sort(key=lambda z: (z[2], -p[z[0]], d[z[0]], z[0]))
            elif order == 'lpt':
                cand.sort(key=lambda z: (-p[z[0]], d[z[0]], z[0]))
            elif order == 'edd':
                cand.sort(key=lambda z: (d[z[0]], -p[z[0]], z[0]))
            elif order == 'spt':
                cand.sort(key=lambda z: (p[z[0]], d[z[0]], z[0]))
            for i, t, nb in cand:
                nmask, ncp, navail, nrp, npc, nrdy, bad = apply(
                    mask, cp, avail, rp, pc, rdy, i, t)
                if bad:
                    continue
                sched[i] = t
                if dfs(depth + 1, nmask, ncp, navail, nrp, npc, nrdy):
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
        stats['masks'] = len(masks)
        stats['expanded'] = expanded[0]
    return ok, dict(sched)
