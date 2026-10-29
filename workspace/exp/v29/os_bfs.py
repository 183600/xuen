"""v2.6d OS-BFS: layer-by-layer DP over masks with per-mask Pareto merge.

Layer k = states with k tasks scheduled.  A state is (cp, avail, rp);
pc/rdy are functions of the mask alone.  All incoming states of a mask are
collected before the mask is expanded, so the Pareto front taken there is the
true one -- unlike DFS, where a dominator that arrives late cannot un-expand
an already-expanded dominated state.

Dominance is exact: same mask => same remaining set; cp_A >= cp_B pointwise
and rp_A <= rp_B pointwise => every completion of B is a completion of A.
"""
import sys
sys.path[:0] = ['exp/v13']


def sgs_bfs(inst, h, rem=None, A=None, est=None, q=None, nodecap=300000,
            stats=None, rsi=True, force=True, dom=True):
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
    predm = {i: sum(BITI[j] for j in inst['pred'][i] if (rem >> j) & 1)
             for i in tasks}
    rdy_cache = {}

    def rdy_of(mask):
        v = rdy_cache.get(mask)
        if v is None:
            v = 0
            r = mask
            while r:
                low = r & -r
                i = low.bit_length() - 1
                r ^= low
                if not (predm[i] & mask):
                    v |= BITI[i]
            rdy_cache[mask] = v
        return v

    def pareto(lst):
        if len(lst) < 2:
            return list(dict.fromkeys(lst))
        if not dom:
            return list(dict.fromkeys(lst))
        keep = []
        for a in lst:
            ca, aa, ra = a
            bad = False
            for cb, ab, rb in keep:
                if (((cb | GUARD) - ca) & GUARD) == GUARD and \
                   (((ra | GUARDR) - rb) & GUARDR) == GUARDR:
                    bad = True
                    break
            if bad:
                continue
            nk = []
            for cb, ab, rb in keep:
                if (((ca | GUARD) - cb) & GUARD) == GUARD and \
                   (((rb | GUARDR) - ra) & GUARDR) == GUARDR:
                    continue
                nk.append((cb, ab, rb))
            nk.append(a)
            keep = nk
        return keep

    cur = {rem: [(cp0, avail0, rp0)]}
    nodes = 0
    rsi_hits = 0
    force_hits = 0
    layer_sizes = []
    for k in range(len(tasks)):
        nxt = {}
        layer_sizes.append((k, sum(len(v) for v in cur.values())))
        for mask, states in cur.items():
            rdy = rdy_of(mask)
            for cp, avail, rp in states:
                nodes += 1
                if nodes > nodecap:
                    if stats is not None:
                        stats['nodes'] = nodes
                        stats['status'] = 'timeout'
                        stats['layer_sizes'] = layer_sizes
                    return None, {}
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
                            qq = 1
                            while qq < pi:
                                c &= (x >> qq)
                                if c == 0:
                                    break
                                qq += 1
                            if c:
                                c &= (1 << (last - ri + 1)) - 1
                    if c == 0:
                        if rsi:
                            rsi_hits += 1
                            cand = None
                            break
                        continue
                    t = ri + (c & -c).bit_length() - 1
                    if force and (c & (c - 1)) == 0:
                        forced = (i, t)
                        break
                    cand.append((i, t))
                if cand is None:
                    continue
                if forced is not None:
                    cand = [forced]
                    force_hits += 1
                elif not cand:
                    continue
                cand.sort(key=lambda z: (-p[z[0]], d[z[0]], z[0]))
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
                    bad = False
                    nmask = mask ^ BITI[i]
                    for j in succm[i]:
                        if (mask >> j) & 1:
                            old = (nrp >> (rw2 * j)) & rmask
                            new = t + pi
                            if new > old:
                                nrp += (new - old) << (rw2 * j)
                                if new + p[j] > d[j]:
                                    bad = True
                            if not (predm[j] & nmask):
                                pass  # rdy is recomputed per mask
                    if bad:
                        continue
                    if nmask == 0:
                        if stats is not None:
                            stats['nodes'] = nodes
                            stats['status'] = 'yes'
                            stats['layer_sizes'] = layer_sizes
                        return True, {}
                    nxt.setdefault(nmask, []).append((ncp, navail, nrp))
        if not nxt:
            if stats is not None:
                stats['nodes'] = nodes
                stats['rsi_hits'] = rsi_hits
                stats['force_hits'] = force_hits
                stats['status'] = 'no'
                stats['layer_sizes'] = layer_sizes
            return False, {}
        for mask in nxt:
            nxt[mask] = pareto(nxt[mask])
        cur = nxt
    if stats is not None:
        stats['nodes'] = nodes
        stats['status'] = 'end'
        stats['layer_sizes'] = layer_sizes
    return False, {}
