"""v2.3 tier 0.15: two-engine certificate portfolio with a node probe.

probe: enumerate chain placements (CPS), run exact residual DFS with a *global*
       residual-node budget `probe` (default 300).
       - NO  -> NO (cheap chain certificate)
       - YES -> YES (full eligibility)
       - budget hit -> fall through
fallback: OS-SGS order-space search with budget `os_ncap` (default 10000).
"""
import sys, time
sys.path[:0] = ['exp/v28', 'exp/v13', 'exp/v25']
import cps_lib, sgs


def _placements(inst, rem, est, q, h, chain):
    S = h - (est[chain[0]] + sum(inst['p'][i] for i in chain) + q[chain[-1]])
    if S < 0:
        return []
    out = []
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


def cps_probe(inst, rem, A, est, q, h, budget=300, stats=None):
    """CPS with a global residual-node budget.  False=NO, True=YES, None=budget."""
    n = inst['n']
    chain, cp = cps_lib.critical_path(inst, rem, tuple(est), q)
    spent = [0]
    unknown = False
    for s in _placements(inst, rem, est, q, h, chain):
        left = budget - spent[0]
        if left <= 0:
            return None
        st = {}
        rr = cps_lib._residual_feasible(inst, rem, A, est, q, h, chain, list(s),
                                        nodecap=left, stats=st)
        spent[0] += st.get('cps_res_nodes', 0)
        if rr is True:
            return True
        if rr is None:
            unknown = True
            if stats is not None:
                stats['probe_nodes'] = spent[0]
            return None
    if stats is not None:
        stats['probe_nodes'] = spent[0]
    return None if unknown else False


def hybrid_certify(inst, rem, A, est, q, h, tau=4, nodecap=300000,
                   probe=300, os_ncap=10000, stats=None):
    if stats is None:
        stats = {}
    nrem = bin(rem).count('1')
    if nrem == 0:
        return True
    if nrem > 22:
        return None
    cp = max(est[i] + inst['p'][i] + q[i] for i in range(inst['n']) if (rem >> i) & 1)
    S = h - cp
    stats['cps_S'] = S
    if S < 0:
        return False
    if S > tau:
        return None
    full = all(len(set(inst['elig'][i])) == inst['m']
               for i in range(inst['n']) if (rem >> i) & 1)
    if not full:
        return None
    v = cps_probe(inst, rem, A, est, q, h, budget=probe, stats=stats)
    stats['probe_res'] = v
    if v is not None:
        return v
    st = {}
    vo, sch = sgs.sgs_solve(inst, h, rem=rem, A=A, est=est, q=q,
                            nodecap=os_ncap, dom=False, stats=st)
    stats['os_nodes'] = stats.get('os_nodes', 0) + st.get('nodes', 0)
    stats['cps_res_nodes'] = stats.get('cps_res_nodes', 0) + st.get('nodes', 0)
    return vo
