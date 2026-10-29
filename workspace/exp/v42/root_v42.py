"""v4.2 configurable sound cascade: feature-conditioned portfolio.

Every component is sound.  The portfolio only changes cost, never verdicts.
Components:
  ICC  : interval-capacity certificate (full)
  HEC  : Hall energy certificate over eligible-machine subsets (het)
  MPC  : machine-partition certificate (drops cross-machine precedence + eligibility)
  WOS  : word-level exact DFS (full)
  EWOS : busy-mask exact DFS (het)
  PACE : complete fallback
"""
import sys, time, ctypes, os
sys.path[:0] = ['exp/v42', 'exp/v41', 'exp/v31', 'exp/v30', 'exp/v29',
                'exp/v13', 'exp/v20', 'exp/v25']
import po, icc, hec
import wos as os_pack
import ewos2 as ewos

_lib = ctypes.CDLL(os.path.join(os.path.dirname(__file__), 'libmpc_ord.so'))
_lib.mpc_no.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                        ctypes.c_longlong]
_lib.mpc_no.restype = ctypes.c_int
_lib.mpc_nodes.restype = ctypes.c_longlong
_lib.mpc_set_ord.argtypes = [ctypes.POINTER(ctypes.c_int)]

PACE_CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
                packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000,
                dhd=True, dcd=True, hpack_on=True, odom=False,
                map_on=True, map_tau=4, map_ncap=16,
                cps_on=True, cps_tau=4, cps_depth=0, cps_ncap=16,
                cps_nodecap=300000, cps_gate_fan=0)


def mpc_no(inst, h, est, q, order='lpt', w=None, budget=2_000_000, stats=None):
    n = inst['n']
    if n > 16 or h > 63:
        return None
    p = (ctypes.c_int * n)(*inst['p'])
    r = (ctypes.c_int * n)(*est)
    d = (ctypes.c_int * n)(*(h - q[i] for i in range(n)))
    pm = [0] * n
    for i in range(n):
        for j in inst['succ'][i]:
            pm[i] |= 1 << j
    pmv = (ctypes.c_int * n)(*pm)
    if order == 'lpt':
        o = sorted(range(n), key=lambda i: (-inst['p'][i], h - q[i]))
    elif order == 'estdesc':
        o = sorted(range(n), key=lambda i: (-est[i], -inst['p'][i]))
    elif order == 'slack':
        o = sorted(range(n), key=lambda i: (h - q[i] - inst['p'][i] - est[i], -inst['p'][i]))
    elif order == 'qdesc':
        o = sorted(range(n), key=lambda i: (-q[i], -inst['p'][i]))
    elif order == 'edd':
        o = sorted(range(n), key=lambda i: (h - q[i], -inst['p'][i]))
    elif order == 'learned' and w is not None:
        def key(i):
            dd = h - q[i]
            return (w[0] * (-inst['p'][i]) + w[1] * (-est[i]) + w[2] * dd
                    + w[3] * (-q[i]) + w[4] * (dd - inst['p'][i] - est[i])
                    + w[5] * inst['p'][i] / (q[i] + 1))
        o = sorted(range(n), key=key)
    else:
        o = list(range(n))
    ov = (ctypes.c_int * n)(*o)
    _lib.mpc_set_ord(ov)
    v = _lib.mpc_no(n, inst['m'], h, p, r, d, pmv, budget)
    _lib.mpc_clear_ord()
    if stats is not None:
        stats['mpc_nodes'] = _lib.mpc_nodes()
    return None if v < 0 else bool(v)


def bb_solve(inst, h, cfg=None, stats=None):
    if stats is None:
        stats = {}
    cfg = cfg or {}
    n, m = inst['n'], inst['m']
    full = all(len(set(inst['elig'][i])) == m for i in range(n))
    est, q = po.heads_tails(inst, 0, [0] * n)
    cp = max(est[i] + inst['p'][i] + q[i] for i in range(n))
    S = h - cp
    stats.update(S=S, full=full, gate=(full and n <= 16 and 0 <= S <= 4))
    t0 = time.time()
    comps = cfg.get('comps')
    if comps is None:
        comps = ['ICC', 'MPC', 'WOS', 'PACE'] if full else ['HEC', 'PACE']
    for comp in comps:
        if comp == 'ICC':
            if not full:
                continue
            ok, w = icc.icc(inst, inst['full'], tuple([0] * m), est, q, h, stats=stats)
            if not ok:
                stats['verdict'] = 'ICC'; stats['t'] = time.time() - t0
                return False, stats
        elif comp == 'HEC':
            if hec.check(inst, h, est, q, stats) is False:
                stats['verdict'] = 'HEC'; stats['t'] = time.time() - t0
                return False, stats
        elif comp == 'MPC':
            gate = cfg.get('mpc_gate', 'full16')
            okgate = (gate == 'all' or (gate == 'full16' and full and n <= 16)
                      or (gate == 'n16' and n <= 16))
            if not okgate:
                continue
            v = mpc_no(inst, h, est, q, order=cfg.get('mpc_order', 'lpt'),
                       w=cfg.get('mpc_w'), stats=stats)
            if v:
                stats['verdict'] = 'MPC'; stats['t'] = time.time() - t0
                return False, stats
        elif comp == 'WOS':
            if not (full and n <= 16 and 0 <= S <= cfg.get('tau', 4)):
                continue
            so = {}
            vo, _ = os_pack.sgs_solve(inst, h, rem=inst['full'], A=tuple([0] * m),
                                      est=est, q=q, nodecap=cfg.get('os_ncap', 10000),
                                      rsi=True, force=cfg.get('force', True),
                                      order=cfg.get('wos_order', 'lpt'), stats=so)
            stats['os_nodes'] = so.get('nodes', 0)
            stats['os_memo'] = so.get('memo', 0)
            if vo is not None:
                stats['verdict'] = 'OS'; stats['t'] = time.time() - t0
                return vo, stats
        elif comp == 'EWOS':
            if full or n > 16:
                continue
            so = {}
            vo, _ = ewos.solve(inst, h, est=est, q=q, nodecap=cfg.get('het_ncap', 20000),
                               rsi=True, force=cfg.get('force', True),
                               order=cfg.get('wos_order', 'lpt'), stats=so)
            stats['het_nodes'] = so.get('nodes', 0)
            if vo is not None:
                stats['verdict'] = 'EWOS'; stats['t'] = time.time() - t0
                return vo, stats
        elif comp == 'PACE':
            import pace_v25 as P
            pcfg = dict(PACE_CFG)
            pcfg.update(cfg.get('pace', {}))
            if not full:
                pcfg['omd'] = False
                if cfg.get('pace_het_map_off', True):
                    pcfg['map_on'] = False
            else:
                pcfg['omd'] = True
            st2 = {}
            (ok, _), st2 = P.decide(inst, h, stats=st2, **pcfg)
            stats['pace_nodes'] = st2.get('nodes')
            stats['verdict'] = 'PACE'; stats['t'] = time.time() - t0
            return ok, stats
    return None, stats
