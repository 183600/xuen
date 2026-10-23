"""v3.1: ICC -> WOS probe -> exact LP/Farkas certificate -> WOS -> PACE."""
import sys, time
sys.path[:0] = ['exp/v37', 'exp/v35', 'exp/v30', 'exp/v29', 'exp/v13',
                'exp/v20', 'exp/v25']
import po, icc, wos as os_pack, dual_cert3

PACE_CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
                packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000,
                dhd=True, dcd=True, hpack_on=True, odom=False,
                map_on=True, map_tau=4, map_ncap=16,
                cps_on=True, cps_tau=4, cps_depth=0, cps_ncap=16,
                cps_nodecap=300000, cps_gate_fan=0)


def bb_solve(inst, h, probe=1500, os_ncap=10000, icc_on=True, pmax=16, tau=4,
             stats=None, pace_cfg=None, rsi=True, order='lpt', lp_on=True):
    if stats is None:
        stats = {}
    n, m = inst['n'], inst['m']
    full = all(len(set(inst['elig'][i])) == m for i in range(n))
    est, q = po.heads_tails(inst, 0, [0] * n)
    cp = max(est[i] + inst['p'][i] + q[i] for i in range(n))
    S = h - cp
    stats.update(S=S, full=full,
                 gate=(full and n <= pmax and 0 <= S <= tau))
    t0 = time.time()
    if icc_on and full:
        ok, w = icc.icc(inst, inst['full'], tuple([0] * m), est, q, h, stats=stats)
        if not ok:
            stats['verdict'] = 'ICC'
            stats['cert'] = w
            stats['t'] = time.time() - t0
            return False, stats
    if full and n <= pmax and 0 <= S <= tau:
        so = {}
        vo, _ = os_pack.sgs_solve(inst, h, rem=inst['full'], A=tuple([0] * m),
                                  est=est, q=q, nodecap=probe, rsi=rsi,
                                  order=order, stats=so)
        stats['probe_nodes'] = so.get('nodes', 0)
        if vo is not None:
            stats['os_nodes'] = so.get('nodes', 0)
            stats['verdict'] = 'WOS-probe'
            stats['t'] = time.time() - t0
            return vo, stats
        if lp_on:
            vl, info = dual_cert3.solve(inst, h)
            stats['lp_info'] = info
            if vl is False:
                stats['verdict'] = 'LP-CERT'
                stats['t'] = time.time() - t0
                return False, stats
        so2 = {}
        vo, _ = os_pack.sgs_solve(inst, h, rem=inst['full'], A=tuple([0] * m),
                                  est=est, q=q, nodecap=os_ncap, rsi=rsi,
                                  order=order, stats=so2)
        stats['os_nodes'] = (stats.get('probe_nodes') or 0) + so2.get('nodes', 0)
        stats['os_memo'] = so2.get('memo', 0)
        if vo is not None:
            stats['verdict'] = 'WOS'
            stats['t'] = time.time() - t0
            return vo, stats
    import pace_v25 as P
    cfg = dict(pace_cfg or PACE_CFG)
    cfg['omd'] = full
    st2 = {}
    (ok, _), st2 = P.decide(inst, h, stats=st2, **cfg)
    stats['pace_nodes'] = st2.get('nodes')
    stats['pace_tables'] = st2.get('tables')
    stats['verdict'] = 'PACE'
    stats['t'] = time.time() - t0
    return ok, stats
