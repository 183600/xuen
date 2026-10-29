"""Forward label-setting (level BFS) for the DEC state graph."""
import sys, time
sys.path.insert(0, 'exp/v14')
import sp


def decide_bfs(inst, h, K=48, nodecap=3_000_000, policy=None, stats=None):
    pol = dict(sp.DEFAULT_POLICY); pol.update(policy or {})
    n, m, p = inst['n'], inst['m'], inst['p']
    full = inst['full']
    if stats is None: stats = {}
    st = {'labels': 0, 'expanded': 0, 'pruned': 0, 'dead': 0, 'packs': 0,
          'front_sizes': [], 'levels': [], 'timeout': False}
    est0, _ = sp.heads_tails(inst, 0, [0] * n)
    # front[rem] = list of (estt, A_c, est_full)
    front = {full: [(tuple(est0), (0,) * m, tuple(est0))]}
    by_size = {n: [full]}
    twin_cache = {}
    q_cache = {}

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

    for d in range(n, 0, -1):
        rems = by_size.get(d, [])
        nxt = {}
        lvl_labels = 0
        for rem in rems:
            fr = front.get(rem, [])
            lvl_labels += len(fr)
            q = qof(rem)
            ready = [i for i in sp.bititer(rem) if not (inst['pmask'][i] & rem)]
            for (estt, A_c, est) in fr:
                st['labels'] += 1
                if st['labels'] > nodecap:
                    st['timeout'] = True; return (None, None), st
                # DEAD
                dead = False
                for i in sp.bititer(rem):
                    if est[i] + p[i] + q[i] > h:
                        dead = True; break
                if dead:
                    st['dead'] += 1; continue
                st['packs'] += 1
                if not sp.pack_exact(inst, rem, A_c, est, q, h):
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
                        # dominage against live front
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
                        if K and len(keep) > K:
                            keep.sort(key=lambda z: (sum(z[0]), sum(z[1])))
                            keep = keep[:K]
                        tf[:] = keep
                    # next bounds
        # count
        st['front_sizes'].append(sum(len(v) for v in nxt.values()))
        st['levels'].append((d, len(nxt), sum(len(v) for v in nxt.values())))
        if 0 in nxt:
            return (True, None), st
        front = nxt
        by_size[d - 1] = list(nxt.keys())
        if not nxt:
            return (False, None), st
    return (False, None), st


if __name__ == '__main__':
    import pickle
    d = pickle.load(open('exp/v13/hard3.pkl', 'rb'))
    for idx in [int(x) for x in sys.argv[1:]] or [10]:
        inst, opt, n0 = d[idx]
        print('=== inst', idx, 'n', inst['n'], 'opt', opt, flush=True)
        t = time.time()
        (ok, _), st = decide_bfs(inst, opt - 1, nodecap=3_000_000)
        print('bfs', ok, 't', round(time.time() - t, 3), st, flush=True)
