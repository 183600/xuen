"""SUBCERT/2: budgeted window-subproblem search, windows ordered by energy slack."""
import sys, time
sys.path[:0] = ['exp/v37', 'exp/v30', 'exp/v13']
import po, wos


def cand_windows(inst, h, est, q):
    n, m, p = inst['n'], inst['m'], inst['p']
    r = [est[i] for i in range(n)]
    d = [h - q[i] for i in range(n)]
    rs = sorted(set(r)); ds = sorted(set(d))
    out = []
    for a in rs:
        for b in ds:
            if b <= a:
                continue
            S = [i for i in range(n) if r[i] >= a and d[i] <= b]
            if len(S) < 2:
                continue
            L = b - a
            tot = sum(p[i] for i in S)
            cap = m * L
            if tot > cap:
                out.append((0, -len(S), a, b, S, L, tot, cap))
            else:
                out.append((cap - tot, -len(S), a, b, S, L, tot, cap))
    out.sort()
    return out


def check(inst, h, est, q, nodecap=500, totalcap=20000, stats=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    t0 = time.time(); tested = 0; nodes = 0
    for slack, negk, a, b, S, L, tot, cap in cand_windows(inst, h, est, q):
        if nodes > totalcap:
            break
        if tot > cap:
            if stats is not None:
                stats['sub2'] = ('energy', a, b, S, tot, cap)
            return False
        k = len(S)
        pp = [p[i] for i in S]
        ee = [est[i] - a for i in S]
        qq = [b - (h - q[i]) for i in S]
        fake = po.make_inst(pp, m, [[] for _ in range(k)])
        st = {}
        v, _ = wos.sgs_solve(fake, L, rem=fake['full'], A=tuple([0] * m),
                             est=ee, q=qq, nodecap=nodecap, rsi=True,
                             force=True, order='lpt', stats=st)
        nodes += st.get('nodes', 0); tested += 1
        if v is False:
            if stats is not None:
                stats['sub2'] = ('search', a, b, S, slack, tested, nodes)
                stats['sub2_us'] = (time.time() - t0) * 1e6
            return False
    if stats is not None:
        stats['sub2_tested'] = tested
        stats['sub2_nodes'] = nodes
        stats['sub2_us'] = (time.time() - t0) * 1e6
    return True
