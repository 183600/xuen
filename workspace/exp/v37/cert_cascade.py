"""CERT-CASCADE: exact YES/NO certificates before residual PACE/WOS."""
import sys, time
sys.path[:0] = ['exp/v37', 'exp/v35', 'exp/v30', 'exp/v29', 'exp/v13',
                'exp/v16', 'exp/v20', 'exp/v25']
import po, icc, greedy, dual_cert3

PACE_CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
                packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000,
                dhd=True, dcd=True, hpack_on=True, odom=False,
                map_on=True, map_tau=4, map_ncap=16,
                cps_on=True, cps_tau=4, cps_depth=0, cps_ncap=16,
                cps_nodecap=300000, cps_gate_fan=0)


def decide(inst, h, stats=None, greedy_tries=20, lp_on=True, icc_on=True):
    if stats is None:
        stats = {}
    n, m, p = inst['n'], inst['m'], inst['p']
    full = all(len(set(inst['elig'][i])) == m for i in range(n))
    est, q = po.heads_tails(inst, 0, [0] * n)
    t0 = time.time()
    # sound single-job bound
    if any(est[i] + p[i] + q[i] > h for i in range(n)):
        stats['verdict'] = 'SINGLE'
        stats['t'] = time.time() - t0
        return False, stats
    if icc_on and full:
        ok, w = icc.icc(inst, inst['full'], tuple([0] * m), est, q, h, stats=stats)
        if not ok:
            stats['verdict'] = 'ICC'
            stats['t'] = time.time() - t0
            return False, stats
    if lp_on and n <= 24 and h <= 128 and 1 <= m <= 4:
        vl, info = dual_cert3.solve(inst, h)
        stats['lp_info'] = info
        if vl is False:
            stats['verdict'] = 'LP-CERT'
            stats['t'] = time.time() - t0
            return False, stats
    s = greedy.solve(inst, h, tries=greedy_tries)
    if s is not None and greedy.verify(inst, h, s):
        stats['verdict'] = 'GREEDY'
        stats['t'] = time.time() - t0
        return True, stats
    import pace_v25 as P
    (ok, _), st2 = P.decide(inst, h, stats={}, **PACE_CFG)
    stats['pace_nodes'] = st2.get('nodes')
    stats['verdict'] = 'PACE'
    stats['t'] = time.time() - t0
    return ok, stats
