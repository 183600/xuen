"""LLS-M: level-wise label setting with max-plus start-matrix dominance.

The essential state is the max-plus start matrix
    M[i,k] = max(A_k, est_i)   (i in R, k in E_i),
because only M enters the start-time constraints.  Dominance is M'<=M,
strictly coarser than (est'<=est and A'<=A): est_i is irrelevant when it
lies below every A_k.  Dropping an M-dominated live label is sound.

The only compression is dominance: dropping a *non-dominated* live label
would lose feasible schedules.  Hence no K cap is used on live fronts.
"""
import sys
sys.path.insert(0, 'exp/v14')
import sp


def _dom(m2, m):
    for x, y in zip(m2, m):
        if x > y: return False
    return True


def decide_lls(inst, h, policy=None, stats=None, labelcap=5_000_000,
               use_deadfront=False, phi='lin'):
    pol = dict(sp.DEFAULT_POLICY); pol.update(policy or {})
    n, m, p = inst['n'], inst['m'], inst['p']
    full = inst['full']
    st = {'labels': 0, 'expanded': 0, 'pruned': 0, 'dead': 0, 'packs': 0,
          'pack_hits': 0, 'greedy': 0, 'dff': 0, 'exact': 0,
          'dfront_hits': 0, 'front_max': 0, 'front_total': [],
          'dead_max': 0, 'timeout': False, 'levels': []}
    est0, _ = sp.heads_tails(inst, 0, [0] * n)
    def build_M(rem, est, A):
        vals = []
        for i in sp.bitsof(rem):
            e = est[i]
            for k in inst['elig'][i]:
                a = A[k]
                vals.append(a if a > e else e)
        return tuple(vals)

    # label = (sM, M, estt, A_c, est_full)
    M0 = build_M(full, est0, [0] * m)
    front = {full: [(sum(M0), M0, tuple(est0), (0,) * m, tuple(est0))]}
    deadf = {}
    by_size = {n: [full]}
    twin_cache = {}; q_cache = {}; ready_cache = {}; pack_memo = {}

    def qof(rem):
        q = q_cache.get(rem)
        if q is None:
            q = sp.tails(inst, rem); q_cache[rem] = q
        return q

    def readyof(rem):
        r = ready_cache.get(rem)
        if r is None:
            r = [i for i in sp.bititer(rem) if not (inst['pmask'][i] & rem)]
            ready_cache[rem] = r
        return r

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
        ok, used_exact = sp.pack_check(inst, rem, A_c, est, q, h)
        if used_exact:
            st['exact'] += 1
            if not ok:
                pass
        else:
            if ok: st['greedy'] += 1
            else: st['dff'] += 1
        pack_memo[key] = ok
        return ok

    def add_dead(rem, M, estt, A_c):
        fr = deadf.setdefault(rem, [])
        for (m2, e2, a2) in fr:
            if _dom(m2, M):
                return False
        keep = []
        for (m2, e2, a2) in fr:
            if _dom(M, m2):
                continue
            keep.append((m2, e2, a2))
        keep.append((M, estt, A_c))
        fr[:] = keep
        if len(fr) > st['dead_max']: st['dead_max'] = len(fr)
        return True

    def add_live(store, rem, sM, M, estt, A_c, est):
        fr = store.setdefault(rem, [])
        dom = False
        keep = []
        for lab in fr:
            sm2 = lab[0]
            if sm2 <= sM and _dom(lab[1], M):
                dom = True; break
            if sM <= sm2 and _dom(M, lab[1]):
                continue
            keep.append(lab)
        if dom:
            return False
        keep.append((sM, M, estt, A_c, est))
        fr[:] = keep
        return True

    for d in range(n, 0, -1):
        work = []
        for rem in by_size.get(d, []):
            for lab in front.get(rem, []):
                k1 = lab[0]
                work.append((k1, 0, 0, rem, lab))
        work.sort(key=lambda z: (z[0], z[1], z[2]))
        nxt = {}
        for (_, _, _, rem, lab) in work:
            sM, M, estt, A_c, est = lab
            st['labels'] += 1
            if st['labels'] > labelcap:
                st['timeout'] = True; return (None, None), st
            if use_deadfront:
                hit = False
                for (m2, e2, a2) in deadf.get(rem, []):
                    if _dom(m2, M):
                        hit = True; break
                if hit:
                    st['dfront_hits'] += 1; continue
            q = qof(rem)
            dead = False
            for i in sp.bitsof(rem):
                if est[i] + p[i] + q[i] > h:
                    dead = True; break
            if dead or not cap(rem, A_c, est, q):
                st['dead'] += 1
                if use_deadfront:
                    add_dead(rem, M, estt, A_c)
                continue
            st['expanded'] += 1
            for i in readyof(rem):
                for k in inst['elig'][i]:
                    t = max(A_c[k], est[i])
                    if t + p[i] + q[i] > h:
                        continue
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
                            if nest[j] <= fl:
                                nest[j] = 0
                    estt2 = tuple(nest[j] for j in sp.bititer(r2))
                    M2 = build_M(r2, tuple(nest), nA)
                    if not add_live(nxt, r2, sum(M2), M2, estt2,
                                    nA, tuple(nest)):
                        st['pruned'] += 1
        tot = sum(len(v) for v in nxt.values())
        fm = max((len(v) for v in nxt.values()), default=0)
        st['front_total'].append(tot)
        st['front_max'] = max(st['front_max'], fm)
        st['levels'].append((d, len(nxt), tot, fm))
        if 0 in nxt:
            return (True, None), st
        front = nxt
        by_size[d - 1] = list(nxt.keys())
        if not nxt:
            return (False, None), st
    return (False, None), st
