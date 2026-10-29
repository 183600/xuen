"""Pareto label-setting (Dijkstra order by sum(A), sum(est)) for DEC.

Every state label is pushed once per generated edge.  A label is *finalised*
when popped; dominance is checked only against finalised labels at the same
R.  The key (sum A, sum est) is monotone: any dominator of L has
sum A' <= sum A, and on equality A'=A and sum est' <= sum est, so it is
popped no later than L.  Hence no future label can dominate a finalised one,
and the finalised antichain is exact.

Dead labels (capacity NO / DEAD) are kept in the antichain: they are valid
NO labels and prune any harder state at the same R.
"""
import sys, heapq, time
sys.path.insert(0, 'exp/v14')
import sp


def decide_dij(inst, h, policy=None, stats=None, labelcap=5_000_000):
    pol = dict(sp.DEFAULT_POLICY); pol.update(policy or {})
    n, m, p = inst['n'], inst['m'], inst['p']
    full = inst['full']
    st = {'pops': 0, 'pushes': 0, 'final': 0, 'dom_skip': 0, 'dead': 0,
          'packs': 0, 'pack_hits': 0, 'greedy': 0, 'dff': 0,
          'front_max': 0, 'front_total': 0, 'timeout': False, 'yes': False}
    est0, _ = sp.heads_tails(inst, 0, [0] * n)
    twin_cache = {}; q_cache = {}; F_pack = {}; pack_memo = {}
    fronts = {}                       # rem -> list of finalised (estt,A_c,est)
    heap = [(0, sum(est0), 0, full, tuple(est0), (0,) * m, tuple(est0))]
    cnt = 1

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
        if v is not None: return v
        st['packs'] += 1
        fr = F_pack.setdefault((rem, h), [])
        if sp.front_query(fr, A_c):
            st['pack_hits'] += 1; pack_memo[key] = False; return False
        if sp.pack_greedy(inst, rem, A_c, est, q, h):
            st['greedy'] += 1; pack_memo[key] = True; return True
        if sp.pack_dff(inst, rem, A_c, est, q, h):
            st['dff'] += 1; sp.front_insert(fr, A_c, 0); pack_memo[key] = False; return False
        ok = sp.pack_exact(inst, rem, A_c, est, q, h)
        if not ok: sp.front_insert(fr, A_c, 0)
        pack_memo[key] = ok
        return ok

    while heap:
        sA, sE, _, rem, estt, A_c, est = heapq.heappop(heap)
        st['pops'] += 1
        if st['pops'] > labelcap:
            st['timeout'] = True; return (None, None), st
        fr = fronts.setdefault(rem, [])
        dom = False
        for (e2, a2, _) in fr:
            if sp.dominates(a2, A_c) and all(e2[t] <= estt[t] for t in range(len(estt))):
                dom = True; break
        if dom:
            st['dom_skip'] += 1; continue
        fr.append((estt, A_c, est))
        st['final'] += 1
        st['front_total'] = max(st['front_total'], 0)
        if len(fr) > st['front_max']: st['front_max'] = len(fr)
        if rem == 0:
            st['yes'] = True; return (True, None), st
        q = qof(rem)
        dead = False
        for i in sp.bititer(rem):
            if est[i] + p[i] + q[i] > h:
                dead = True; break
        if not dead and not cap(rem, A_c, est, q):
            dead = True
        if dead:
            st['dead'] += 1; continue
        for i in sp.bititer(rem):
            if inst['pmask'][i] & rem: continue
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
                heapq.heappush(heap, (sum(nA), sum(estt2), cnt, r2, estt2, nA, tuple(nest)))
                cnt += 1; st['pushes'] += 1
    return (False, None), st
