"""Anytime lower-bound profile: EPC -> root start-time LP -> full ECC."""
import sys, time, json, pickle
sys.path[:0] = ['exp/v13', 'exp/v50', 'exp/v60']
import numpy as np
from po import heads_tails
from ecc import StartLP, ecc_no


def epc_feasible(inst, h, est, q):
    n, m, p = inst['n'], inst['m'], inst['p']
    d = [h - q[i] for i in range(n)]
    for a in range(h):
        for b in range(a + 1, h + 1):
            need = 0
            for i in range(n):
                ov = min(p[i], b - a, est[i] + p[i] - a, b - d[i] + p[i])
                if ov > 0:
                    need += ov
            if need > m * (b - a):
                return False
    return True


def epc_lb(inst, hi):
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    lo = max(max(est[i] + inst['p'][i] + q[i] for i in range(inst['n'])),
             (sum(inst['p']) + inst['m'] - 1) // inst['m'])
    # epc is monotone: find smallest feasible h
    if epc_feasible(inst, lo, est, q):
        return lo, 0
    a, b = lo, hi
    while a < b:
        mid = (a + b) // 2
        if epc_feasible(inst, mid, est, q):
            b = mid
        else:
            a = mid + 1
    return a, 0


def root_lp_lb(inst, hi, lo=None):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    if lo is None:
        lo = max(max(est[i] + inst['p'][i] + q[i] for i in range(n)),
                 (sum(inst['p']) + inst['m'] - 1) // inst['m'])
    solves = [0]
    def feasible(h):
        lp = StartLP(inst, h, est, q)
        solves[0] += 1
        return lp.solve().status == 0
    if feasible(lo):
        return lo, solves[0]
    a, b = lo, hi
    assert feasible(b), (lo, hi)
    while a < b:
        mid = (a + b) // 2
        if feasible(mid):
            b = mid
        else:
            a = mid + 1
    return a, solves[0]


def full_no_lb(inst, hi, nodecap=20000):
    """Largest h in [lo, hi] with an ECC NO certificate, plus 1.

    NO is downward closed in h, so binary search is valid.  We never call
    the branch search on a feasible h (the v5.0 YES side can recurse without
    making progress -- see notes).  ``hi`` is the known/assumed OPT.
    """
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    lo = max(max(est[i] + inst['p'][i] + q[i] for i in range(n)),
             (sum(inst['p']) + inst['m'] - 1) // inst['m'])
    lp_nodes = [0]
    def is_no(h):
        v, st = ecc_no(inst, h, nodecap=nodecap)
        lp_nodes[0] += st.get('lp_nodes', 0)
        return v
    a, b = lo, hi - 1
    if b < a:
        return a, 0, 'trivial'
    va = is_no(a)
    if va is None:
        return None, lp_nodes[0], 'unknown'
    if va is not False:
        return a, lp_nodes[0], 'root-feasible'
    if a == b:
        return a + 1, lp_nodes[0], 'yes'
    # find last NO in [a, b]; is_no is False for NO, True for YES, None unknown
    last_no = a
    while a <= b:
        mid = (a + b) // 2
        v = is_no(mid)
        if v is None:
            return None, lp_nodes[0], 'unknown'
        if v is False:
            last_no = mid
            a = mid + 1
        else:
            b = mid - 1
    return last_no + 1, lp_nodes[0], 'yes'


def load_all():
    out = []
    sets = [
        ('holdout50', 'exp/v20/holdout_cases50.pkl', 'tuple'),
        ('synth2_45', 'exp/v28/synth2_45.pkl', 'tuple'),
        ('large_a', 'exp/v14/large_a.pkl', 'dict'),
        ('large_b', 'exp/v14/large_b.pkl', 'dict'),
        ('large_het', 'exp/v14/large_het.pkl', 'dict'),
        ('hard3', 'exp/v13/hard3.pkl', 'tuple'),
        ('deep', 'exp/v18/deep.pkl', 'tuple'),
    ]
    for name, path, kind in sets:
        d = pickle.load(open(path, 'rb'))
        for idx, x in enumerate(d):
            if kind == 'tuple':
                inst, opt = x[0], x[1]
            else:
                inst, opt = x['inst'], x['opt']
            out.append((name, idx, inst, opt))
    return out


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'holdout50'
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else 10**9
    data = load_all()
    rows = []
    t0 = time.time()
    for k, (name, idx, inst, opt) in enumerate(data):
        if name != which or len(rows) >= lim:
            continue
        e_lb, _ = epc_lb(inst, opt)
        r_lb, r_solves = root_lp_lb(inst, opt, max(e_lb, 0))
        f_lb, fnodes, fstatus = full_no_lb(inst, opt)
        rows.append(dict(set=name, idx=idx, opt=opt, epc_lb=e_lb, root_lb=r_lb,
                         root_solves=r_solves, full_lb=f_lb, full_nodes=fnodes,
                         full_status=fstatus))
        print(f"{name}#{idx} opt={opt} epc={e_lb} root={r_lb} ({r_solves} LP) "
              f"full={f_lb} ({fnodes} nodes, {fstatus})", flush=True)
    json.dump(rows, open(f'exp/v60/lb_{which}.json', 'w'), indent=1)
    print('time', round(time.time() - t0, 2), 'rows', len(rows))
