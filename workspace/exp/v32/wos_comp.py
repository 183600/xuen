"""WOS: Word-level OS with free singleton forcing.  v3.0 production kernel.

Two observations drive this kernel.

1. (word state)  Every node operation is a constant number of word ops:
   PLACE is one subtraction, AV is derived by SWAR, EARLIEST is a doubling
   run-search.

2. (free forcing)  The singleton-forcing test
        "job i has exactly one feasible start"  <=>  t_i == d_i - p_i
   needs only the value t_i that the branching scan already computes, so in
   the word kernel the test costs ~0.  v2.5 measured forcing at ce=3.70us
   per node against a 2.29us threshold and rejected it; here ce ~ 0.2us.
"""
import sys
sys.path[:0] = ['exp/v13']


def sgs_solve(inst, h, rem=None, A=None, est=None, q=None, nodecap=200000,
              order='lpt', rsi=True, force=True, stats=None):
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
    forced_n = [0]
    rsi_hits = [0]
    comp_hits = [0]
    sched = {}


    def comp_bad(mask, cp, rp):
        # compulsory part of each remaining job: [d_i-p_i, r_i+p_i)
        diff = [0] * (h + 2)
        any_part = False
        for i in range(n):
            if (mask >> i) & 1:
                ri = (rp >> (rw * i)) & rmask
                a = d[i] - p[i]
                b = ri + p[i]
                if a < b:
                    lo = a if a > 0 else 0
                    hi = b if b < h else h
                    if lo < hi:
                        diff[lo] += 1
                        diff[hi] -= 1
                        any_part = True
        if not any_part:
            return False
        cur = 0
        for t in range(h):
            cur += diff[t]
            if cur:
                c = (cp >> (cw * t)) & ((1 << cw) - 1)
                if cur > c:
                    return True
        return False

    def dfs(mask, cp, rp, pc, rdy):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        # ---- forcing fixpoint -------------------------------------------
        while True:
            if mask == 0:
                return True
            key = cp | (rp << kshift) | (mask << mshift)
            if key in seen:
                return False
            if comp_bad(mask, cp, rp):
                comp_hits[0] += 1
                seen.add(key)
                return False
            av = cp
            k = 1
            while k < cw:
                av |= cp >> k
                k += 1
            av &= ONES
            cand = []
            fi = -1
            r = rdy
            while r:
                lb = r & -r
                i = lb.bit_length() - 1
                r ^= lb
                pi = p[i]
                ri = (rp >> (rw * i)) & rmask
                last = d[i] - pi
                x = av >> (cw * ri) if last >= ri else 0
                t = -1
                if x:
                    rr = x
                    L = 1
                    ok = True
                    while 2 * L <= pi:
                        rr &= rr >> (cw * L)
                        if not rr:
                            ok = False
                            break
                        L <<= 1
                    if ok and L < pi:
                        rr &= rr >> (cw * (pi - L))
                    if ok and rr:
                        t = ri + (((rr & -rr).bit_length() - 1) // cw)
                        if t > last:
                            t = -1
                if t < 0:
                    if rsi:
                        rsi_hits[0] += 1
                        seen.add(cp | (rp << kshift) | (mask << mshift))
                        return False
                    continue
                cand.append((i, t))
                if force and t == last:
                    fi = i
                    break
            if not force or fi < 0:
                break
            # commit the forced job (unique feasible start)
            i = fi
            t = d[i] - p[i]
            cp -= rep[p[i]] << (cw * t)
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
                rsi_hits[0] += 1
                seen.add(cp | (rp << kshift) | (mask << mshift))
                return False
            sched[i] = t
            forced_n[0] += 1
            mask ^= 1 << i
            rp, pc, rdy = nrp, npc, nrdy
        # ---- branching ---------------------------------------------------
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
        stats['forced'] = forced_n[0]
        stats['comp'] = comp_hits[0]
    return ok, dict(sched)
