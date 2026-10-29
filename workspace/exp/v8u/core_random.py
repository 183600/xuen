import sys, json, time, collections
sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13', 'exp/v8j']
from search_hard import make_inst
from core_icf import solve_root, decide_core
from pact import PACT, pact_decide


def opt_of(inst):
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, s, m = co.initial_bounds()
    if ub is None:
        return None
    L, U = int(lb), int(ub)
    while L < U:
        mid = (L + U) // 2
        r = pact_decide(inst, mid, depthcap=None, nodecap=None)
        if r['verdict'] is True:
            c = max(r['schedule'][i] + inst['p'][i]
                    for i in range(inst['n']))
            U = min(U, c)
        elif r['verdict'] is False:
            L = mid + 1
        else:
            return None
    return L


def main(out='exp/v8u/core_random75.json'):
    rows = []
    t0 = time.time()
    for edgep, seeds in ((0.03, 15), (0.05, 15), (0.08, 15), (0.12, 30)):
        for seed in range(seeds):
            inst = make_inst(18, 3, seed, edgep=edgep, hetero=0.0)
            opt = opt_of(inst)
            if opt is None:
                rows.append(dict(edgep=edgep, seed=seed, opt=None,
                                 status='unknown-opt'))
                continue
            t = time.time()
            status, lp, res, K = solve_root(inst, opt - 1)
            dt = time.time() - t
            r = dict(edgep=edgep, seed=seed, opt=opt, h=opt - 1,
                     T=int(max(inst['p'])), status=status,
                     K=sorted(K), k=len(K), lp_time=round(dt, 4),
                     total_t=round(time.time() - t0, 2))
            if status == 'fractional':
                rr, root, fb = decide_core(inst, opt - 1)
                r.update(verdict=rr['verdict'], fallback=bool(fb),
                         search_lp=rr.get('lp_solves', 0),
                         nodes=rr.get('nodes', 0))
            rows.append(r)
        print('edgep', edgep, 'done', len(rows), flush=True)
    json.dump(rows, open(out, 'w'))
    print('wrote', out, 'n', len(rows))
    print('status', collections.Counter(r['status'] for r in rows))
    print('k', collections.Counter(r['k'] for r in rows))
    print('fallback', collections.Counter(r.get('fallback') for r in rows))
    print('wall', round(time.time() - t0, 2))
    return rows


if __name__ == '__main__':
    main()
