"""v2.6c OS-DOM: mask kernel + guard-bit per-mask dominance.

Fields are stored with one guard bit: a CP field lives in cw+1 bits, value
< 2^cw, guard bit 0.  For two states at the SAME mask,
    A dominates B  <=>  CP_A >= CP_B pointwise  and  RP_A <= RP_B pointwise
and each pointwise test is one subtraction:
    G = sum 1<<(w*u + w-1)
    ((A | G) - B) & G == G   <=>   A_u >= B_u for every field u
because the +2^(w-1) guard makes every field difference positive, so no
borrow ever crosses a field boundary.

The per-mask Pareto list is append-only: a stored state is always already
fully expanded (same-mask states cannot be ancestors), so pruning against it
is sound without undo.
"""
import sys
sys.path[:0] = ['exp/v13']


def sgs_dom(inst, h, rem=None, A=None, est=None, q=None, nodecap=300000,
            order='lpt', rng=None, stats=None, rsi=True, force=True, dom=True):
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
    cw2 = cw + 1
    GUARD = 0
    for u in range(h):
        GUARD |= 1 << (cw2 * u + cw)
    rw = max(1, max([h] + list(est)).bit_length())
    rmask = (1 << rw) - 1
    rw2 = rw + 1
    GUARDR = 0
    for i in range(n):
        GUARDR |= 1 << (rw2 * i + rw)
    d = [h - q[i] for i in range(n)]
    succm = {i: [j for j in inst['succ'][i] if (rem >> j) & 1] for i in tasks}
    BIT = [1 << u for u in range(h)]
    BITI = [1 << i for i in range(n)]
    cap0 = [sum(1 for k in range(m) if A[k] <= t) for t in range(h)]
    cp0 = 0
    avail0 = 0
    for t in range(h):
        cp0 |= cap0[t] << (cw2 * t)
        if cap0[t] > 0:
            avail0 |= BIT[t]
    rp0 = 0
    for i in tasks:
        rp0 |= est[i] << (rw2 * i)
    pc0 = 0
    rdy0 = 0
    for i in tasks:
        cnt = len([j for j in inst['pred'][i] if (rem >> j) & 1])
        pc0 |= cnt << (4 * i)
        if cnt == 0:
            rdy0 |= BITI[i]
    nodes = [0]
    rsi_hits = [0]
    force_hits = [0]
    dom_hits = [0]
    no_cand = [0]
    seen = set()
    sched = {}
    front = {}
    shift_rp = cw2 * h
    shift_m = cw2 * h + rw2 * n

    def dfs(depth, mask, cp, avail, rp, pc, rdy):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if mask == 0:
            return True
        key = cp | (rp << shift_rp) | (mask << shift_m)
        if key in seen:
            return False
        if dom:
            lst = front.get(mask)
            if lst is not None:
                for c2, r2 in lst:
                    if (((c2 | GUARD) - cp) & GUARD) == GUARD and \
                       (((rp | GUARDR) - r2) & GUARDR) == GUARDR:
                        dom_hits[0] += 1
                        seen.add(key)
                        return False
        else:
            lst = None
        cand = []
        forced = None
        r = rdy
        while r:
            low = r & -r
            i = low.bit_length() - 1
            r ^= low
            ri = (rp >> (rw2 * i)) & rmask
            pi = p[i]
            last = d[i] - pi
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
            cand.append((i, t))
        if forced is not None:
            cand = [forced]
            force_hits[0] += 1
        elif not cand:
            no_cand[0] += 1
            seen.add(key)
            return False
        elif rng is not None:
            rng.shuffle(cand)
        elif order == 'lpt':
            cand.sort(key=lambda z: (-p[z[0]], d[z[0]], z[0]))
        elif order == 'edd':
            cand.sort(key=lambda z: (d[z[0]], -p[z[0]], z[0]))
        elif order == 'spt':
            cand.sort(key=lambda z: (p[z[0]], d[z[0]], z[0]))
        if dom:
            if lst is None:
                front[mask] = [(cp, rp)]
            else:
                lst.append((cp, rp))
        for i, t in cand:
            pi = p[i]
            ncp = cp
            navail = avail
            for u in range(t, t + pi):
                v = ((ncp >> (cw2 * u)) & cmask) - 1
                ncp -= 1 << (cw2 * u)
                if v == 0:
                    navail &= ~BIT[u]
            nrp = rp & ~(rmask << (rw2 * i))
            npc = pc
            nrdy = rdy & ~BITI[i]
            bad = False
            for j in succm[i]:
                if (mask >> j) & 1:
                    old = (nrp >> (rw2 * j)) & rmask
                    new = t + pi
                    if new > old:
                        nrp += (new - old) << (rw2 * j)
                        if new + p[j] > d[j]:
                            bad = True
                    v = ((npc >> (4 * j)) & 15) - 1
                    npc -= 1 << (4 * j)
                    if v == 0:
                        nrdy |= BITI[j]
            if bad:
                continue
            sched[i] = t
            if dfs(depth + 1, mask ^ BITI[i], ncp, navail, nrp, npc, nrdy):
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
        stats['dom_hits'] = dom_hits[0]
        stats['no_cand'] = no_cand[0]
    return ok, dict(sched)
