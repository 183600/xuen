"""v2.3 prototype: CPS with sequence (SGS) residual + Pareto dominance memo.

Reproduces the 5 held-out root residuals of v2.2 and compares
  baseline : exact start-time DFS (cps_lib._residual_feasible)
  sgs      : serial SGS over order atoms (earliest placement, all orders)
  sgs_dom  : sgs + Pareto dominance memo on (mask, cap, rel)
"""
import pickle, sys, time, json
sys.path[:0] = ['exp/v13', 'exp/v20', 'exp/v25']
import po, cps_lib

CASES = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
IDX = [5, 21, 32, 42, 47]


def placements(inst, rem, est, q, h, chain):
    S = h - (est[chain[0]] + sum(inst['p'][i] for i in chain) + q[chain[-1]])
    out = []
    if S < 0:
        return out
    for g in cps_lib._compositions(S, len(chain) + 1):
        s, t, ok = [], est[chain[0]] + g[0], True
        for a, i in enumerate(chain):
            if a > 0:
                t = s[-1] + inst['p'][chain[a - 1]] + g[a]
            if t < est[i] or t + inst['p'][i] > h - q[i]:
                ok = False
                break
            s.append(t)
        if ok:
            out.append(tuple(s))
    return out


def make_residual(inst, rem, A, est, q, h, chain, s):
    w = cps_lib._windows(inst, rem, A, est, q, h, chain, s)
    if w is None:
        return None
    r, d = w
    p, m = inst['p'], inst['m']
    P = set(chain)
    cap = [sum(1 for k in range(m) if A[k] <= t) for t in range(h)]
    for a, i in enumerate(chain):
        for t in range(s[a], min(h, s[a] + p[i])):
            cap[t] -= 1
    if any(c < 0 for c in cap):
        return None
    res = [i for i in range(inst['n']) if ((rem >> i) & 1) and i not in P]
    rmask = 0
    for i in res:
        rmask |= 1 << i
    predm = {i: sum(1 << j for j in inst['pred'][i] if (rmask >> j) & 1) for i in res}
    succm = {i: [j for j in inst['succ'][i] if (rmask >> j) & 1] for i in res}
    return dict(res=res, rmask=rmask, predm=predm, succm=succm,
                r=list(r), d=d, p=p, cap=cap, h=h)


def earliest(cap, t0, pi, hi):
    """earliest t >= t0 with hi >= t+pi and cap[t..t+pi) >= 1."""
    t = t0
    while t + pi <= hi:
        if all(cap[u] > 0 for u in range(t, t + pi)):
            return t
        t += 1
    return None


def sgs(R, nodecap=300000, order='minopts', dom=False, stats=None):
    res, rmask = R['res'], R['rmask']
    p, d, cap0 = R['p'], R['d'], R['cap']
    predm, succm = R['predm'], R['succm']
    nodes = [0]
    fails = []          # Pareto frontier of NO states: (mask, cap, rel)
    seen_exact = set()

    def dominated(mask, cap, rel):
        for mk, c2, r2 in fails:
            if mk != mask:
                continue
            if all(a >= b for a, b in zip(c2, cap)) and \
               all(a <= b for a, b in zip(r2, rel)):
                return True
        return False

    def dfs(mask, cap, rel):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if mask == 0:
            return True
        if dom and dominated(mask, cap, rel):
            return False
        if not dom:
            key = (mask, tuple(cap), tuple(rel[i] for i in res if (mask >> i) & 1))
            if key in seen_exact:
                return False
        if sum(p[i] for i in res if (mask >> i) & 1) > sum(cap):
            if dom:
                fails.append((mask, tuple(cap), tuple(rel)))
            else:
                seen_exact.add((mask, tuple(cap), tuple(rel[i] for i in res if (mask >> i) & 1)))
            return False
        ready = [i for i in res if (mask >> i) & 1 and not (predm[i] & mask)]
        # option counts for minopts over *ready* tasks
        cand = []
        for i in ready:
            t = earliest(cap, rel[i], p[i], d[i])
            if t is None:
                continue
            cand.append((i, t))
        if not cand:
            if dom:
                fails.append((mask, tuple(cap), tuple(rel)))
            else:
                seen_exact.add((mask, tuple(cap), tuple(rel[i] for i in res if (mask >> i) & 1)))
            return False
        if order == 'minopts':
            # fewest free start positions (a cheap MRV proxy over ready tasks)
            def nopts(it):
                i, t0 = it
                c = 0
                t = t0
                while t + p[i] <= d[i]:
                    if all(cap[u] > 0 for u in range(t, t + p[i])):
                        c += 1
                    t += 1
                return c
            cand.sort(key=lambda it: (nopts(it), d[it[0]], -p[it[0]]))
        elif order == 'edd':
            cand.sort(key=lambda it: (d[it[0]], -p[it[0]]))
        elif order == 'lpt':
            cand.sort(key=lambda it: (-p[it[0]], d[it[0]]))
        for i, t in cand:
            ncap = list(cap)
            for u in range(t, t + p[i]):
                ncap[u] -= 1
            nrel = list(rel)
            for j in succm[i]:
                if (mask >> j) & 1 and t + p[i] > nrel[j]:
                    nrel[j] = t + p[i]
            if dfs(mask ^ (1 << i), ncap, nrel):
                return True
            # deadline prune is implicit: earliest() returned None -> skipped
        if dom:
            fails.append((mask, tuple(cap), tuple(rel)))
        else:
            seen_exact.add((mask, tuple(cap), tuple(rel[i] for i in res if (mask >> i) & 1)))
        return False

    try:
        ok = dfs(rmask, list(cap0), list(R['r']))
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['nodes'] = nodes[0]
        stats['front'] = len(fails)
    return ok


def main():
    rows = []
    for idx in IDX:
        inst, opt = CASES[idx]
        h = opt - 1
        n = inst['n']
        est, q = po.heads_tails(inst, 0, [0] * n)
        A = tuple([0] * inst['m'])
        rem = inst['full']
        chain, cp = cps_lib.critical_path(inst, rem, tuple(est), q)
        ps = placements(inst, rem, est, q, h, chain)
        row = dict(idx=idx, n=n, m=inst['m'], h=h, S=h - cp, L=len(chain),
                   chain=chain, nplace=len(ps))
        base_nodes = sgs_nodes = 0
        t0 = time.time(); verdicts = set()
        for s in ps:
            st = {}
            rr = cps_lib._residual_feasible(inst, rem, A, tuple(est), q, h, chain, list(s),
                                            nodecap=300000, stats=st)
            base_nodes += st.get('cps_res_nodes', 0)
            verdicts.add(rr)
        row['base_nodes'] = base_nodes
        row['base_t'] = time.time() - t0
        row['base_v'] = str(verdicts)
        for mode, kw in [('minopts', dict(order='minopts')),
                         ('edd', dict(order='edd')),
                         ('lpt', dict(order='lpt'))]:
            tot = 0; t0 = time.time(); vs = set(); fr = 0; unk = False
            for s in ps:
                R = make_residual(inst, rem, A, tuple(est), q, h, chain, list(s))
                if R is None:
                    vs.add(False); continue
                st = {}
                rr = sgs(R, nodecap=300000, dom=False, stats=st, **kw)
                tot += st['nodes']; fr += st['front']
                if rr is None: unk = True
                vs.add(rr)
            row['sgs_' + mode] = dict(nodes=tot, t=time.time() - t0, v=str(vs))
        # dominance variant
        tot = 0; t0 = time.time(); vs = set(); fr = 0; unk = False
        for s in ps:
            R = make_residual(inst, rem, A, tuple(est), q, h, chain, list(s))
            if R is None:
                vs.add(False); continue
            st = {}
            rr = sgs(R, nodecap=300000, dom=True, stats=st)
            tot += st['nodes']; fr += st['front']
            if rr is None: unk = True
            vs.add(rr)
        row['sgs_dom'] = dict(nodes=tot, t=time.time() - t0, v=str(vs), front=fr)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
    json.dump(rows, open('exp/v28/res_sgs.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
