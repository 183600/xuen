import sys, time
sys.path.insert(0, '..'); sys.path.insert(0, '.'); sys.path.insert(0, '../v07')
import exp_da as E, ip, cbj


def solve(inst, use_ip=True, use_pack=True, use_cbj=False, nodecap=3_000_000):
    n = inst['n']; S = 0; A = (0,) * inst['m']; c = (-1,) * n
    U = min(E.greedy(inst, S, A, c, r) for r in ('CP', 'LPT', 'MWKR'))
    L0 = E.lower_L0(inst, S, A, c)
    LD = ip.dff_lb(inst, S, A, c) if use_ip else L0
    LP = ip.pack_lb(inst, S, A, c, L0, U - 1) if use_ip else L0
    L = max(L0, LD, LP)
    memo = {'bad': {}}
    nodes = 0; calls = 0; rounds = 0; t0 = time.time()
    while L < U and rounds < 32:
        rounds += 1
        st, sc, s = cbj.decide(inst, S, A, c, U - 1, nodecap=nodecap,
                               use_pack=use_pack, use_cbj=use_cbj, memo=memo)
        nodes += s.get('nodes', 0); calls += 1
        if st is False:
            L = U; break
        if st is True:
            mk = max([max(A)] + [t + inst['p'][i] for (i, k, t) in sc])
            if mk < U:
                U = mk
            else:
                break
        else:
            break
        # after a better U, recompute the IP bound
        L0n = E.lower_L0(inst, S, A, c)
        if use_ip:
            L = max(L0n, ip.dff_lb(inst, S, A, c), ip.pack_lb(inst, S, A, c, L0n, U - 1))
        else:
            L = L0n
    return dict(U=U, L=L, rounds=rounds, calls=calls, nodes=nodes,
                t=round(time.time() - t0, 4), proved=(L >= U))


if __name__ == '__main__':
    import json
    R = json.load(open('results.json'))
    import pickle
    pool = pickle.load(open('../pool30.pkl', 'rb'))
    out = {}
    for fam in ('dense', 'part2', 'part3'):
        rows = R[fam]; res = []
        for r in rows:
            if fam == 'dense':
                inst = pool[r['k']][0]
            else:
                # rebuild from p
                p = r['p']; m = r['m']; n = len(p)
                pred = [[] for _ in range(n)]; succ = [[] for _ in range(n)]
                inst = {'n': n, 'm': m, 'p': p, 'pred': pred, 'succ': succ,
                        'ep': 0.0, 'pmax': max(p)}
                E.compute_desc(inst); inst['pmask'] = [0] * n
            b = solve(inst, use_ip=False, use_pack=False)
            a = solve(inst, use_ip=True, use_pack=True, use_cbj=True)
            res.append(dict(k=r['k'], base=b, ip=a, OPT=r['OPT']))
            print(fam, r['k'], 'OPT', r['OPT'], 'base', b, 'ip', a, flush=True)
        out[fam] = res
    json.dump(out, open('solve.json', 'w'), indent=1)
    for fam in out:
        print('==', fam)
        for key in ('base', 'ip'):
            print(key, 'nodes', sum(x[key]['nodes'] for x in out[fam]),
                  'rounds', sum(x[key]['rounds'] for x in out[fam]),
                  't', round(sum(x[key]['t'] for x in out[fam]), 3),
                  'wrong', sum(1 for x in out[fam] if x[key]['U'] != x['OPT']))
