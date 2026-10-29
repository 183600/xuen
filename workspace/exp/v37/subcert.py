"""SUBCERT: solve a window subproblem exactly; NO is a global NO certificate."""
import sys, time
sys.path[:0] = ['exp/v37', 'exp/v30', 'exp/v13']
import po, wos


def check(inst, h, est, q, nodecap=2000, stats=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    r = [est[i] for i in range(n)]
    d = [h - q[i] for i in range(n)]
    rs = sorted(set(r)); ds = sorted(set(d))
    t0 = time.time(); tested = 0; nodes = 0
    for a in rs:
        for b in ds:
            if b <= a:
                continue
            S = [i for i in range(n) if r[i] >= a and d[i] <= b]
            if len(S) < 2:
                continue
            L = b - a
            if sum(p[i] for i in S) > m * L:
                if stats is not None:
                    stats['sub'] = ('energy', a, b, S)
                return False
            # build fake instance, preserving no precedence
            k = len(S)
            pp = [p[i] for i in S]
            ee = [r[i] - a for i in S]
            qq = [b - d[i] for i in S]
            fake = po.make_inst(pp, m, [[] for _ in range(k)])
            st = {}
            v, _ = wos.sgs_solve(fake, L, rem=fake['full'], A=tuple([0] * m),
                                 est=ee, q=qq, nodecap=nodecap, rsi=True,
                                 force=True, order='lpt', stats=st)
            nodes += st.get('nodes', 0); tested += 1
            if v is False:
                if stats is not None:
                    stats['sub'] = ('search', a, b, S)
                    stats['sub_us'] = (time.time() - t0) * 1e6
                    stats['sub_nodes'] = nodes
                return False
            if v is None:
                # budget exhausted: inconclusive for this window
                continue
    if stats is not None:
        stats['sub_tested'] = tested
        stats['sub_nodes'] = nodes
        stats['sub_us'] = (time.time() - t0) * 1e6
    return True
