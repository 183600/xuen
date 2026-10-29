"""v3.5 root cascade: ICC -> WOS probe -> PCLP (LP certificate) -> WOS -> PACE.

PCLP is the new root engine: a start-time LP relaxation with
  * per-time machine-subset capacity rows (generalises EPC/HEC to all times),
  * cumulative precedence cuts added by cutting-plane refinement.
LP infeasibility at h is a valid NO certificate; feasibility is inconclusive.
"""
import sys, time
sys.path[:0] = ['exp/v35', 'exp/v30', 'exp/v29', 'exp/v13', 'exp/v20', 'exp/v25']
import po, icc, wos as os_pack
import refine

PACE_CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
                packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000,
                dhd=True, dcd=True, hpack_on=True, odom=False,
                map_on=True, map_tau=4, map_ncap=16,
                cps_on=True, cps_tau=4, cps_depth=0, cps_ncap=16,
                cps_nodecap=300000, cps_gate_fan=0)

LP_NMAX = 24
LP_HMAX = 128


def lp_gate(inst, h):
    return (inst['n'] <= LP_NMAX and h <= LP_HMAX
            and 1 <= inst['m'] <= 4)


def bb_solve(inst, h, probe=2000, os_ncap=10000, icc_on=True, pmax=16, tau=4,
             stats=None, pace_cfg=None, rsi=True, order='lpt',
             lp_on=True, lp_cuts=True):
    if stats is None:
        stats = {}
    n, m = inst['n'], inst['m']
    full = all(len(set(inst['elig'][i])) == m for i in range(n))
    est, q = po.heads_tails(inst, 0, [0] * n)
    cp = max(est[i] + inst['p'][i] + q[i] for i in range(n))
    S = h - cp
    stats.update(S=S, full=full)
    t0 = time.time()
    if icc_on and full:
        ok, w = icc.icc(inst, inst['full'], tuple([0] * m), est, q, h, stats=stats)
        if not ok:
            stats['verdict'] = 'ICC'
            stats['t'] = time.time() - t0
            return False, stats
    os_gate = full and n <= pmax and 0 <= S <= tau
    probe_hit = False
    if os_gate and probe > 0:
        sp = {}
        vo, _ = os_pack.sgs_solve(inst, h, rem=inst['full'], A=tuple([0] * m),
                                  est=est, q=q, nodecap=probe, rsi=rsi,
                                  order=order, stats=sp)
        stats['probe_nodes'] = sp.get('nodes', 0)
        if vo is not None:
            stats['verdict'] = 'WOS-probe'
            stats['os_nodes'] = sp.get('nodes', 0)
            stats['t'] = time.time() - t0
            return vo, stats
        probe_hit = True
    if lp_on and lp_gate(inst, h) and ((not full) or probe_hit):
        v, info = refine.solve_cp(inst, h, max_cuts=200 if lp_cuts else 0)
        stats['lp'] = v
        stats['lp_cuts'] = info.get('cuts')
        stats['lp_rounds'] = info.get('rounds')
        if v == 'NO':
            stats['verdict'] = 'PCLP'
            stats['t'] = time.time() - t0
            return False, stats
    if os_gate:
        so = {}
        vo, _ = os_pack.sgs_solve(inst, h, rem=inst['full'], A=tuple([0] * m),
                                  est=est, q=q, nodecap=os_ncap, rsi=rsi,
                                  order=order, stats=so)
        stats['os_nodes'] = (stats.get('probe_nodes') or 0) + so.get('nodes', 0)
        stats['os_memo'] = so.get('memo', 0)
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
