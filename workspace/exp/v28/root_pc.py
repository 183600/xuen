"""v2.4 root certificate cascade: ICC -> CPS(64) -> OS(10k) -> PACE."""
import sys, time
sys.path[:0] = ['exp/v28', 'exp/v13', 'exp/v20', 'exp/v25']
import po, hybrid, sgs, icc

PACE_CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
                packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000,
                dhd=True, dcd=True, hpack_on=True, odom=False,
                map_on=True, map_tau=4, map_ncap=16,
                cps_on=True, cps_tau=4, cps_depth=0, cps_ncap=16,
                cps_nodecap=300000, cps_gate_fan=0)


def pc_solve(inst, h, probe=0, os_ncap=10000, icc_on=True, pmax=16, tau=4,
             stats=None, pace_cfg=None):
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
    # stage 1: short dual cut (only for full eligibility)
    if icc_on and full:
        ok, w = icc.icc(inst, inst['full'], tuple([0] * m), est, q, h, stats=stats)
        if not ok:
            stats['verdict'] = 'ICC'
            stats['cert'] = w
            stats['t'] = time.time() - t0
            return False, stats
    # stage 2/3: cheap chain probe, then order space
    if full and n <= pmax and 0 <= S <= tau:
        if probe > 0:
            st = {}
            v = hybrid.cps_probe(inst, inst['full'], tuple([0] * m), est, q, h,
                                 budget=probe, stats=st)
            stats['probe_nodes'] = st.get('probe_nodes', 0)
            stats['probe_res'] = v
            if v is not None:
                stats['verdict'] = 'CPS'
                stats['t'] = time.time() - t0
                return v, stats
        so = {}
        vo, _ = sgs.sgs_solve(inst, h, rem=inst['full'], A=tuple([0] * m),
                              est=est, q=q, nodecap=os_ncap, dom=False,
                              stats=so)
        stats['os_nodes'] = so.get('nodes', 0)
        if vo is not None:
            stats['verdict'] = 'OS'
            stats['t'] = time.time() - t0
            return vo, stats
    # stage 4: full machine-time search
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
