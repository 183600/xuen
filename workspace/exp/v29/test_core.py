"""Minimal-infeasible-core probe: is every task necessary for the NO proof?"""
import sys, pickle, time, json
sys.path[:0] = ['exp/v29', 'exp/v13', 'exp/v20', 'exp/v25']
import po, os_pack


def subinst(inst, S):
    S = sorted(S); idx = {v: k for k, v in enumerate(S)}; n = len(S)
    z = dict(inst); z['n'] = n
    z['p'] = [inst['p'][i] for i in S]
    z['pred'] = [[idx[j] for j in inst['pred'][i] if j in idx] for i in S]
    z['succ'] = [[idx[j] for j in inst['succ'][i] if j in idx] for i in S]
    z['elig'] = [list(inst['elig'][i]) for i in S]
    z['full'] = (1 << n) - 1
    z['pmask'] = z['full']
    return z


def feas(inst, S, h, ncap=100000):
    z = subinst(inst, S)
    est, q = po.heads_tails(z, 0, [0] * z['n'])
    v, _ = os_pack.sgs_solve(z, h, rem=z['full'], A=(0,) * z['m'],
                             est=est, q=q, nodecap=ncap, rsi=True)
    return v


def main():
    d = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    out = []
    t0 = time.time()
    for idx, (inst, opt) in enumerate(d):
        h = opt - 1
        n = inst['n']
        irreducible = True
        tested = 0
        for i in range(n):
            S = set(range(n)); S.discard(i)
            v = feas(inst, S, h)
            tested += 1
            if v is False:
                irreducible = False
                break
        out.append(dict(idx=idx, n=n, irreducible=irreducible, tested=tested))
        print(idx, n, irreducible, flush=True)
    agg = dict(n=len(out), irreducible=sum(1 for r in out if r['irreducible']),
               t=round(time.time() - t0, 3))
    print(agg)
    json.dump(dict(agg=agg, rows=out), open('exp/v29/res_core.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
