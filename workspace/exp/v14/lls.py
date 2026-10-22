"""LLS: level-wise Pareto label setting for DEC.

State label: (R, est, A).  A label is live if it has not yet been proved NO.
front[R] is the exact antichain of live labels.  We process R by decreasing
|R|; all children of level d land in level d-1, so each R is merged once.
Dominance (est'<=est, A'<=A) is sound to drop a live label because the
dominating state is componentwise easier.

The only compression is dominance: dropping a *non-dominated* live label
would lose feasible schedules.  Hence no K cap is used on live fronts.
"""
import sys
sys.path.insert(0, 'exp/v14')
import sp


def _dom(a2, e2, nA, estt2):
    for x, y in zip(a2, nA):
        if x > y: return False
    for x, y in zip(e2, estt2):
        if x > y: return False
    return True


def decide_lls(inst, h, policy=None, stats=None, labelcap=5_000_000,
               use_deadfront=False, phi='lin', shuffle=0):
    pol = dict(sp.DEFAULT_POLICY); pol.update(policy or {})
    n, m, p = inst['n'], inst['m'], inst['p']
    full = inst['full']
    st = {'labels': 0, 'expanded': 0, 'pruned': 0, 'dead': 0, 'packs': 0,
          'pack_hits': 0, 'greedy': 0, 'dff': 0, 'exact': 0,
          'dfront_hits': 0, 'front_max': 0, 'front_total': [],
          'dead_max': 0, 'timeout': False, 'levels': []}
    est0, _ = sp.heads_tails(inst, 0, [0] * n)
    # label = (sE, sA, estt, A_c, est_full)
    front = {full: [(sum(est0), 0, tuple(est0), (0,) * m, tuple(est0))]}
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

    def add_dead(rem, estt, A_c):
        fr = deadf.setdefault(rem, [])
        for (e2, a2) in fr:
            if _dom(a2, e2, A_c, estt):
                return False
        keep = []
        for (e2, a2) in fr:
            if _dom(A_c, estt, a2, e2):
                continue
            keep.append((e2, a2))
        keep.append((estt, A_c))
        fr[:] = keep
        if len(fr) > st['dead_max']: st['dead_max'] = len(fr)
        return True

    def add_live(store, rem, sE, sA, estt, A_c, est):
        fr = store.setdefault(rem, [])
        dom = False
        keep = []
        for lab in fr:
            sa2 = lab[1]; se2 = lab[0]
            if sa2 <= sA and se2 <= sE:
                if _dom(lab[3], lab[2], A_c, estt):
                    dom = True; break
            if sA <= sa2 and sE <= se2:
                if _dom(A_c, estt, lab[3], lab[2]):
                    continue
            keep.append(lab)
        if dom:
            return False
        keep.append((sE, sA, estt, A_c, est))
        fr[:] = keep
        return True

    for d in range(n, 0, -1):
        work = []
        for rem in by_size.get(d, []):
            for lab in front.get(rem, []):
                A = lab[3]; e = lab[2]
                if phi == 'sq':
                    k1 = sum(x * x for x in A) + sum(x * x for x in e)
                elif phi == 'max':
                    k1 = max(A) + max(e)
                elif phi == 'est':
                    k1 = lab[0]
                elif phi == 'mix':
                    k1 = lab[1] + max(A)
                else:
                    k1 = lab[1]
                work.append((k1, lab[1], lab[0], rem, lab))
        work.sort(key=lambda z: (z[0], z[1], z[2]))
        if shuffle:
            import random as _r
            _r.Random(shuffle + d).shuffle(work)
        nxt = {}
        for (_, _, _, rem, lab) in work:
            sE, sA, estt, A_c, est = lab
            st['labels'] += 1
            if st['labels'] > labelcap:
                st['timeout'] = True; return (None, None), st
            if use_deadfront:
                hit = False
                for (e2, a2) in deadf.get(rem, []):
                    if _dom(a2, e2, A_c, estt):
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
                    add_dead(rem, estt, A_c)
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
                    if not add_live(nxt, r2, sum(estt2), sum(nA), estt2,
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
