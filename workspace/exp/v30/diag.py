"""Count, on the states the v2.5 search actually expands, how often several
sound necessary conditions are violated.  No pruning is applied; this is a
pure diagnostic."""
import sys
sys.path[:0] = ['exp/v13']


def scan(inst, h, est, q, nodecap=200000):
    n, m, p = inst['n'], inst['m'], inst['p']
    rem = inst['full']
    cw = max(1, m.bit_length()); cmask = (1 << cw) - 1
    rw = max(1, max([h] + list(est)).bit_length()); rmask = (1 << rw) - 1
    d = [h - q[i] for i in range(n)]
    predm = {i: sum(1 << j for j in inst['pred'][i]) for i in range(n)}
    succm = {i: list(inst['succ'][i]) for i in range(n)}
    cap0 = [m] * h
    cp0 = sum(m << (cw * t) for t in range(h))
    avail0 = (1 << h) - 1
    rp0 = sum(est[i] << (rw * i) for i in range(n))
    pc0 = sum(len(inst['pred'][i]) << (4 * i) for i in range(n))
    rdy0 = sum(1 << i for i in range(n) if not predm[i])
    pref = [0] * (h + 1)
    for t in range(h): pref[t + 1] = pref[t] + m
    stat = dict(nodes=0, rwe=0, atpf=0, rset=0, rwe_ex=0, both=0)
    seen = set()

    def earliest(av, t0, pi, hi):
        last = hi - pi
        if last < t0: return None
        x = av >> t0
        c = x; k = 1
        while k < pi:
            c &= x >> k
            if not c: return None
            k += 1
        s = (c & -c).bit_length() - 1
        return t0 + s if t0 + s <= last else None

    def dfs(mask, cp, av, rp, pc, rdy):
        stat['nodes'] += 1
        if stat['nodes'] > nodecap: raise TimeoutError
        if mask == 0: return True
        key = (mask, cp, rp)
        if key in seen: return False
        cand = []
        r = rdy
        js = []
        while r:
            lb = r & -r; i = lb.bit_length() - 1; r ^= lb
            ri = (rp >> (rw * i)) & rmask
            t = earliest(av, ri, p[i], d[i])
            if t is None:
                seen.add(key); return False
            cand.append((i, t)); js.append(i)
        # condition A: ready-set aggregate over [min r, max d]
        a = min(((rp >> (rw * i)) & rmask) for i in js)
        b = max(d[i] for i in js)
        if sum(p[i] for i in js) > pref[b] - pref[a]:
            stat['rset'] += 1
        # condition B: RWE per ready job: window [r_i, d_i], demand of jobs inside
        fired = False
        for i in js:
            ri = (rp >> (rw * i)) & rmask
            dem = 0
            rr = mask
            while rr:
                lb = rr & -rr; j = lb.bit_length() - 1; rr ^= lb
                if ((rp >> (rw * j)) & rmask) >= ri and d[j] <= d[i]:
                    dem += p[j]
            if dem > pref[d[i]] - pref[ri]:
                fired = True; break
        if fired: stat['rwe'] += 1
        # condition C: ATPF -- every remaining job individually placeable
        bad = False
        rr = mask
        while rr:
            lb = rr & -rr; j = lb.bit_length() - 1; rr ^= lb
            if earliest(av, (rp >> (rw * j)) & rmask, p[j], d[j]) is None:
                bad = True; break
        if bad: stat['atpf'] += 1
        for i, t in sorted(cand, key=lambda it: (-p[it[0]], d[it[0]])):
            ncp = cp
            for u in range(t, t + p[i]):
                ncp -= 1 << (cw * u)
            nav = av
            for u in range(t, t + p[i]):
                if ((ncp >> (cw * u)) & cmask) == 0:
                    nav &= ~(1 << u)
            for u in range(t + p[i], h + 1): pref[u] -= 1
            nrp = rp & ~(rmask << (rw * i))
            npc = pc; nrdy = rdy & ~(1 << i)
            bad = False
            for j in succm[i]:
                if (mask >> j) & 1:
                    old = (nrp >> (rw * j)) & rmask
                    new = t + p[i]
                    if new > old:
                        nrp += (new - old) << (rw * j)
                        if new + p[j] > d[j]: bad = True
                    v = ((npc >> (4 * j)) & 15) - 1
                    npc -= 1 << (4 * j)
                    if v == 0: nrdy |= 1 << j
            if not bad:
                if dfs(mask ^ (1 << i), ncp, nav, nrp, npc, nrdy): return True
            for u in range(t + p[i], h + 1): pref[u] += 1
        seen.add(key)
        return False

    dfs(rem, cp0, avail0, rp0, pc0, rdy0)
    return stat
