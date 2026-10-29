"""Drop-in replacement for cps_lib.cps_certify: order-space SGS certificate."""
import sys
sys.path[:0] = ['exp/v28', 'exp/v13']
import sgs


def sgs_certify(inst, rem, A, est, q, h, tau=4, depth_cap=10 ** 9,
                nodecap=300000, stats=None, residual='exact'):
    if stats is None:
        stats = {}
    nrem = bin(rem).count('1')
    if nrem == 0:
        return True
    if nrem > 22:
        return None
    # tightness gate (same as CPS: critical-path slack)
    cp = max(est[i] + inst['p'][i] + q[i] for i in range(inst['n']) if (rem >> i) & 1)
    S = h - cp
    stats['cps_cp'] = cp
    stats['cps_S'] = S
    if S < 0:
        return False
    if S > tau:
        return None
    full = all(len(set(inst['elig'][i])) == inst['m']
               for i in range(inst['n']) if (rem >> i) & 1)
    if not full:
        return None
    st = {}
    v, sch = sgs.sgs_solve(inst, h, rem=rem, A=A, est=est, q=q,
                           nodecap=nodecap, dom=False, stats=st)
    stats['cps_res_nodes'] = stats.get('cps_res_nodes', 0) + st.get('nodes', 0)
    stats['sgs_nodes'] = stats.get('sgs_nodes', 0) + st.get('nodes', 0)
    stats['cps_placements'] = 1
    if v is None:
        stats['cps_result'] = 'UNK'
        return None
    stats['cps_result'] = 'YES' if v else 'NO'
    return v
