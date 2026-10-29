"""Full-instance serial SGS (no chain decomposition) as a root decision procedure."""
import pickle, sys, time, json
sys.path[:0] = ['exp/v13', 'exp/v20', 'exp/v25']
import po

CASES = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
IDX = [5, 21, 32, 42, 47]


def sgs_full(inst, h, nodecap=2_000_000, dom=True, stats=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    pred, succ, full = inst['pred'], inst['succ'], inst['full']
    est, q = po.heads_tails(inst, 0, [0] * n)
    r = list(est); d = [h - q[i] for i in range(n)]
    predm = {i: sum(1 << j for j in pred[i]) for i in range(n)}
    succm = {i: succ[i] for i in range(n)}
    nodes = [0]; fails = []
    seen = set()

    def earliest(cap, t0, pi, hi):
        t = max(t0, 0)
        while t + pi <= min(hi, h):
            if all(cap[u] > 0 for u in range(t, t + pi)):
                return t
            t += 1
        return None

    def dfs(mask, cap, rel):
        nodes[0] += 1
        if nodes[0] > nodecap: raise TimeoutError
        if mask == 0: return True
        if dom:
            for mk, c2, r2 in fails:
                if mk == mask and all(a >= b for a, b in zip(c2, cap)) and \
                   all(a <= b for a, b in zip(r2, rel)):
                    return False
        else:
            key = (mask, tuple(cap), tuple(rel[i] for i in range(n) if (mask >> i) & 1))
            if key in seen: return False
        ready = [i for i in range(n) if (mask >> i) & 1 and not (predm[i] & mask)]
        cand = []
        for i in ready:
            t = earliest(cap, rel[i], p[i], d[i])
            if t is not None: cand.append((i, t))
        if not cand:
            if dom: fails.append((mask, tuple(cap), tuple(rel)))
            else: seen.add((mask, tuple(cap), tuple(rel[i] for i in range(n) if (mask >> i) & 1)))
            return False
        # LPT-ish
        cand.sort(key=lambda it: (-p[it[0]], d[it[0]]))
        for i, t in cand:
            ncap = list(cap)
            for u in range(t, t + p[i]): ncap[u] -= 1
            nrel = list(rel)
            for j in succm[i]:
                if (mask >> j) & 1 and t + p[i] > nrel[j]: nrel[j] = t + p[i]
            if dfs(mask ^ (1 << i), ncap, nrel): return True
        if dom: fails.append((mask, tuple(cap), tuple(rel)))
        else: seen.add((mask, tuple(cap), tuple(rel[i] for i in range(n) if (mask >> i) & 1)))
        return False

    try: ok = dfs(full, [m] * h, r)
    except TimeoutError: ok = None
    if stats is not None: stats['nodes'] = nodes[0]; stats['front'] = len(fails)
    return ok


for idx in IDX:
    inst, opt = CASES[idx]
    row = dict(idx=idx, n=inst['n'], m=inst['m'], opt=opt)
    for h in [opt - 1, opt]:
        for dom in [False, True]:
            st = {}
            t0 = time.time()
            v = sgs_full(inst, h, nodecap=2_000_000, dom=dom, stats=st)
            row[('h%d' % h) + ('_dom' if dom else '_exact')] = dict(v=v, nodes=st.get('nodes'), t=round(time.time()-t0, 4))
    print(json.dumps(row))
