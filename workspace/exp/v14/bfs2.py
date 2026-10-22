"""Level-wise label setting (LLS) for DEC: exact forward frontier DP.

front[R] is the exact antichain of live labels (est,A) that are reachable and
not dominated.  A label is expanded once, at its level; children are merged
into the next level.  Unlike a DFS failure memo, live labels may NOT be
dropped by a cap without losing completeness: dominance is the only legal
compression.
"""
import sys, time
sys.path.insert(0, 'exp/v14')
import sp


def decide_lls(inst, h, policy=None, stats=None, labelcap=5_000_000,
               frontcap=0):
    pol = dict(sp.DEFAULT_POLICY); pol.update(policy or {})
    n, m, p = inst['n'], inst['m'], inst['p']
    full = inst['full']
    st = {'labels': 0, 'expanded': 0, 'pruned': 0, 'dead': 0, 'packs': 0,
          'pack_hits': 0, 'greedy': 0, 'dff': 0, 'front_total': [],
          'front_max': 0, 'timeout': False, 'levels': []}
    est0, _ = sp.heads_tails(inst, 0, [0] * n)
    front = {full: [(tuple(est0), (0,) * m, tuple(est0))]}
    by_size = {n: [full]}
    twin_cache = {}
    q_cache = {}
    F_pack = {}
    pack_memo = {}

    def qof(rem):
        q = q_cache.get(rem)
        if q is None:
            q = sp.tails(inst, rem); q_cache[rem] = q
        return q

    def canonA(rem, A):
        r = twin_cache.get(rem)
        if r is None:
            groups = {}
            for k in range(m):
                col = tuple(sorted(i for i in sp.bititer(rem) if k in inst['elig'][i]))
                groups.setdefault(col, []).append(k)
            r = [g for g in groups.values() if len(g) > 1]
            twin_cache[rem] = r
        if not r:
            return A
        out = list(A)
        for g in r:
            vals = sorted((out[k] for k in g), reverse=True)
            for k, v in zip(g, vals): out[k] = v
        return tuple(out)

    def cap(rem, A_c, est, q):
        key = (rem, A_c)
        v = pack_memo.get(key)
        if v is not None:
            return v
        st['packs'] += 1
        fr = F_pack.setdefault((rem, h), [])
        if sp.front_query(fr, A_c):
            st['pack_hits'] += 1
            pack_memo[key] = False
            return False
        if sp.pack_greedy(inst, rem, A_c, est, q, h):
            st['greedy'] += 1
            pack_memo[key] = True
            return True
        if sp.pack_dff(inst, rem, A_c, est, q, h):
            st['dff'] += 1
            sp.front_insert(fr, A_c, 0)
            pack_memo[key] = False
            return False
        ok = sp.pack_exact(inst, rem, A_c, est, q, h)
        if not ok:
            sp.front_insert(fr, A_c, 0)
        pack_memo[key] = ok
        return ok

    for d in range(n, 0, -1):
        rems = by_size.get(d, [])
        nxt = {}
        for rem in rems:
            fr = front.get(rem, [])
            q = qof(rem)
            ready = [i for i in sp.bititer(rem) if not (inst['pmask'][i] & rem)]
            for (estt, A_c, est) in fr:
                st['labels'] += 1
                if st['labels'] > labelcap:
                    st['timeout'] = True; return (None, None), st
                dead = False
                for i in sp.bititer(rem):
                    if est[i] + p[i] + q[i] > h:
                        dead = True; break
                if dead:
                    st['dead'] += 1; continue
                if not cap(rem, A_c, est, q):
                    st['dead'] += 1; continue
                st['expanded'] += 1
                for i in ready:
                    for k in inst['elig'][i]:
                        t = max(A_c[k], est[i])
                        if t + p[i] + q[i] > h: continue
                        nA = list(A_c); nA[k] = t + p[i]; nA = tuple(nA)
                        r2 = rem & ~(1 << i)
                        nA = canonA(r2, nA)
                        nest = list(est)
                        for j in inst['succ'][i]:
                            if (rem >> j) & 1 and t + p[i] > nest[j]:
                                nest[j] = t + p[i]
                        if pol['est_zero']:
                            for j in sp.bititer(r2):
                                fl = min(nA[kk] for kk in inst['elig'][j])
                                if nest[j] <= fl: nest[j] = 0
                        estt2 = tuple(nest[j] for j in sp.bititer(r2))
                        tf = nxt.setdefault(r2, [])
                        dom = False
                        for (e2, a2, _) in tf:
                            if sp.dominates(a2, nA) and all(e2[t] <= estt2[t] for t in range(len(estt2))):
                                dom = True; break
                        if dom:
                            st['pruned'] += 1; continue
                        keep = []
                        for (e2, a2, efull) in tf:
                            if sp.dominates(nA, a2) and all(estt2[t] <= e2[t] for t in range(len(estt2))):
                                continue
                            keep.append((e2, a2, efull))
                        keep.append((estt2, nA, tuple(nest)))
                        if frontcap and len(keep) > frontcap:
                            # sound only if we never drop a live label: disabled by default
                            keep.sort(key=lambda z: (sum(z[0]), sum(z[1])))
                            keep = keep[:frontcap]
                        tf[:] = keep
        tot = sum(len(v) for v in nxt.values())
        fm = max((len(v) for v in nxt.values()), default=0)
        st['front_total'].append(tot); st['front_max'] = max(st['front_max'], fm)
        st['levels'].append((d, len(nxt), tot, fm))
        if 0 in nxt:
            return (True, None), st
        front = nxt
        by_size[d - 1] = list(nxt.keys())
        if not nxt:
            return (False, None), st
    return (False, None), st
