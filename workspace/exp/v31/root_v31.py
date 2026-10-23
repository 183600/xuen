"""v3.1 cascade: HEC -> ICC -> WOS(full) / E-WOS(het) -> PACE."""
import sys, time
sys.path[:0] = ['exp/v31', 'exp/v30', 'exp/v29', 'exp/v13', 'exp/v20', 'exp/v25']
import po, icc, hec
import wos as os_pack
import ewos

PACE_CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
                packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000,
                dhd=True, dcd=True, hpack_on=True, odom=False,
                map_on=True, map_tau=4, map_ncap=16,
                cps_on=True, cps_tau=4, cps_depth=0, cps_ncap=16,
                cps_nodecap=300000, cps_gate_fan=0)


def bb_solve(inst, h, os_ncap=10000, het_ncap=20000, icc_on=True, pmax=16,
             tau=4, use_hec=True, use_het=True, stats=None, pace_cfg=None):
    if stats is None:
        stats = {}
    n, m = inst['n'], inst['m']
    full = all(len(set(inst['elig'][i])) == m for i in range(n))
    est, q = po.heads_tails(inst, 0, [0] * n)
    cp = max(est[i] + inst['p'][i] + q[i] for i in range(n))
    S = h - cp
    stats.update(S=S, full=full, gate=(full and n <= pmax and 0 <= S <= tau))
    t0 = time.time()
    if use_hec and not hec.check(inst, h, est, q, stats):
        stats['verdict'] = 'HEC'
        stats['t'] = time.time() - t0
        return False, stats
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
                                  est=est, q=q, nodecap=os_ncap, rsi=True,
                                  order='lpt', stats=so)
        stats['os_nodes'] = so.get('nodes', 0)
        stats['os_memo'] = so.get('memo', 0)
        if vo is not None:
            stats['verdict'] = 'OS'
            stats['t'] = time.time() - t0
            return vo, stats
    elif use_het and not full and False:
        pass
    import pace_v25 as P
    cfg = dict(pace_cfg or PACE_CFG)
    cfg['omd'] = full
    if use_het and not full:
        cfg['map_on'] = False
    st2 = {}
    (ok, _), st2 = P.decide(inst, h, stats=st2, **cfg)
    stats['pace_nodes'] = st2.get('nodes')
    stats['verdict'] = 'PACE'
    stats['t'] = time.time() - t0
    return ok, stats
