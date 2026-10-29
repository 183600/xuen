"""E-WOS/2: eligibility kernel with *busy masks* (gap filling, exact SGS).

State = (mask, M, RP) with M = tuple of m occupancy bitmasks over [0,h).
Placing job i at t on machine k ORs ((1<<p)-1)<<t into M[k].  The earliest
feasible t on a machine is the first run of p zero bits at or after r_i.
The serial SGS over occupancy maps is complete for active schedules; the
free-time-vector variant of v3.1-alpha is NOT (it loses gaps and returned
34 false NOs in 712 brute-force cases).
"""
import sys
sys.path[:0] = ['exp/v13']


def solve(inst, h, rem=None, est=None, q=None, nodecap=200000,
          force=True, rsi=True, order='lpt', stats=None, seen=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    if rem is None:
        rem = inst['full']
    if est is None or q is None:
        import po
        e0, q0 = po.heads_tails(inst, 0, [0] * n)
        est = est if est is not None else e0
        q = q if q is not None else q0
    d = [h - q[i] for i in range(n)]
    rw = max(1, max([h] + list(est)).bit_length())
    rmask = (1 << rw) - 1
    rp0 = 0
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
    elig = [list(inst['elig'][i]) for i in range(n)]
    bits = [(1 << p[i]) - 1 for i in range(n)]
    if seen is None:
        seen = set()
    nodes = [0]
    forced_n = [0]
    rsi_hits = [0]
    sched = {}

    def earliest(mk, r, pi, last):
        # first run of pi zero bits in [r, last] of mask mk
        if last < r:
            return -1
        span = last - r + pi
        x = (~mk >> r) & ((1 << span) - 1)
        if not x:
            return -1
        rr = x
        L = 1
        ok = True
        while 2 * L <= pi:
            rr &= rr >> L
            if not rr:
                ok = False
                break
            L <<= 1
        if ok and L < pi:
            rr &= rr >> (pi - L)
        if not ok or not rr:
            return -1
        return r + ((rr & -rr).bit_length() - 1)

    def dfs(mask, M, rp, pc, rdy):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        while True:
            if mask == 0:
                return True
            key = (M, rp, mask)
            if key in seen:
                return False
            cand = []
            forced = []
            r = rdy
            while r:
                lb = r & -r
                i = lb.bit_length() - 1
                r ^= lb
                ri = (rp >> (rw * i)) & rmask
                last = d[i] - p[i]
                best = -1
                for k in elig[i]:
                    t = earliest(M[k], ri, p[i], last)
                    if t >= 0 and (best < 0 or t < best):
                        best = t
                if best < 0:
                    if rsi:
                        rsi_hits[0] += 1
                        seen.add(key)
                        return False
                    continue
                cand.append((i, best))
                if force and best == last:
                    opts = []
                    for kk in elig[i]:
                        if earliest(M[kk], ri, p[i], last) == last:
                            NMk = list(M)
                            NMk[kk] |= bits[i] << last
                            NMk = tuple(NMk)
                            if NMk not in opts:
                                opts.append(NMk)
                    forced.append((i, opts))
            fi = -1
            if force and len(forced) == 1 and len(forced[0][1]) == 1:
                fi = forced[0][0]
            if fi < 0:
                break
            i = fi
            t = d[i] - p[i]
            NM = list(forced[0][1][0])
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
            sched[i] = (t, 0)
            forced_n[0] += 1
            mask ^= 1 << i
            M = tuple(NM)
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
            ri = (rp >> (rw * i)) & rmask
            seenM = set()
            for k in elig[i]:
                if earliest(M[k], ri, p[i], d[i] - p[i]) != t:
                    continue
                NM = list(M)
                NM[k] |= bits[i] << t
                NM = tuple(NM)
                if NM in seenM:
                    continue
                seenM.add(NM)
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
                sched[i] = (t, k)
                if dfs(mask ^ (1 << i), NM, nrp, npc, nrdy):
                    return True
                del sched[i]
        seen.add(key)
        return False

    try:
        ok = dfs(rem, tuple([0] * m), rp0, pc0, rdy0)
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes[0]
        stats['memo'] = len(seen)
        stats['forced'] = forced_n[0]
        stats['rsi_hits'] = rsi_hits[0]
    return ok, dict(sched)
