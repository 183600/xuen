"""E-WOS: eligibility-generalised word kernel.  v3.1 candidate.

State = (mask, A, RP).  A packs m machine-free-times, one w-bit field each.
For full eligibility this is *information-equivalent* to v3.0's CP profile
(c(t) = #{k : A_k <= t}); for arbitrary eligibility E_i it is the only
correct state, and v3.0's aggregate profile is no longer exact.
"""
import sys
sys.path[:0] = ['exp/v13']


def solve(inst, h, rem=None, est=None, q=None, nodecap=200000,
          force=True, rsi=True, order='lpt', elig=None, stats=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    if rem is None:
        rem = inst['full']
    if est is None or q is None:
        import po
        e0, q0 = po.heads_tails(inst, 0, [0] * n)
        est = est if est is not None else e0
        q = q if q is not None else q0
    if elig is None:
        elig = inst['elig']
    d = [h - q[i] for i in range(n)]
    w = max(1, (h + 1).bit_length())
    amask = (1 << w) - 1
    # A = 0 for every machine ; RP = est
    rw = max(1, max([h] + list(est)).bit_length())
    rmask = (1 << rw) - 1
    rp0 = 0
    emask = []
    for i in range(n):
        mk = 0
        for k in elig[i]:
            mk |= 1 << k
        emask.append(mk)
    for i in range(n):
        if (rem >> i) & 1:
            rp0 |= est[i] << (rw * i)
    pb = max(4, n.bit_length())
    pcmask = (1 << pb) - 1
    pc0 = 0
    rdy0 = 0
    for i in range(n):
        if (rem >> i) & 1:
            c = len([j for j in inst['pred'][i] if (rem >> j) & 1])
            pc0 |= c << (pb * i)
            if c == 0:
                rdy0 |= 1 << i
    succm = {i: [j for j in inst['succ'][i] if (rem >> j) & 1] for i in range(n)}
    ks = w * m
    ms = ks + rw * n
    seen = set()
    nodes = [0]
    forced_n = [0]
    rsi_hits = [0]
    sched = {}

    def dfs(mask, A, rp, pc, rdy):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        while True:
            if mask == 0:
                return True
            key = A | (rp << ks) | (mask << ms)
            if key in seen:
                return False
            cand = []
            fi = -1
            r = rdy
            while r:
                lb = r & -r
                i = lb.bit_length() - 1
                r ^= lb
                ri = (rp >> (rw * i)) & rmask
                pi = p[i]
                last = d[i] - pi
                t = -1
                if last >= ri:
                    mk = emask[i]
                    best = 1 << 30
                    while mk:
                        lbk = mk & -mk
                        k = lbk.bit_length() - 1
                        mk ^= lbk
                        ak = (A >> (w * k)) & amask
                        tt = ak if ak > ri else ri
                        if tt < best:
                            best = tt
                    if best <= last:
                        t = best
                if t < 0:
                    if rsi:
                        rsi_hits[0] += 1
                        seen.add(key)
                        return False
                    continue
                cand.append((i, t))
                if force and t == last:
                    fi = i
                    break
            if fi < 0:
                break
            i = fi
            t = d[i] - p[i]
            # choose machine: largest A_k <= t among eligible
            mk = emask[i]
            bk = -1
            ba = -1
            while mk:
                lbk = mk & -mk
                k = lbk.bit_length() - 1
                mk ^= lbk
                ak = (A >> (w * k)) & amask
                if ak <= t and ak > ba:
                    ba = ak
                    bk = k
            A += ((t + p[i] - ba) << (w * bk))
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
                    v = ((npc >> (pb * j)) & pcmask) - 1
                    npc -= 1 << (pb * j)
                    if v == 0:
                        nrdy |= 1 << j
            if bad:
                rsi_hits[0] += 1
                seen.add(key)
                return False
            sched[i] = t
            forced_n[0] += 1
            mask ^= 1 << i
            rp, pc, rdy = nrp, npc, nrdy
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
            mk = emask[i]
            bk = -1
            ba = -1
            while mk:
                lbk = mk & -mk
                k = lbk.bit_length() - 1
                mk ^= lbk
                ak = (A >> (w * k)) & amask
                if ak <= t and ak > ba:
                    ba = ak
                    bk = k
            nA = A + ((t + p[i] - ba) << (w * bk))
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
                    v = ((npc >> (pb * j)) & pcmask) - 1
                    npc -= 1 << (pb * j)
                    if v == 0:
                        nrdy |= 1 << j
            if bad:
                continue
            sched[i] = t
            if dfs(mask ^ (1 << i), nA, nrp, npc, nrdy):
                return True
            del sched[i]
        seen.add(key)
        return False

    try:
        ok = dfs(rem, 0, rp0, pc0, rdy0)
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes[0]
        stats['memo'] = len(seen)
        stats['rsi_hits'] = rsi_hits[0]
        stats['forced'] = forced_n[0]
    return ok, dict(sched)
