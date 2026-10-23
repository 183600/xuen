"""v4.0 benchmark: WOS (DFS) vs LFP, forward/backward, 4-way interleaved."""
import sys, time, json, statistics, pickle
sys.path[:0] = ['exp/v34', 'exp/v30', 'exp/v13']
import po, wos, lfp
from bench_wos import load


def cases():
    return load('exp/v20/holdout_cases50.pkl')


def main():
    cs = cases()
    ests = [po.heads_tails(inst, 0, [0] * inst['n']) for inst, _ in cs]
    res = {k: [] for k in ['df', 'db', 'lf', 'lb']}
    exp = {}
    for rep in range(4):
        t = time.time()
        for (inst, opt), (est, q) in zip(cs, ests):
            wos.sgs_solve(inst, opt - 1, est=est, q=q, force=True, nodecap=300000)
        res['df'].append(time.time() - t)
        t = time.time()
        for (inst, opt), (est, q) in zip(cs, ests):
            wos.sgs_solve(rev(inst), opt - 1, est=q, q=est, force=True, nodecap=300000)
        res['db'].append(time.time() - t)
        t = time.time()
        for inst, opt in cs:
            lfp.solve(inst, opt - 1, dir='forward')
        res['lf'].append(time.time() - t)
        t = time.time()
        for inst, opt in cs:
            lfp.solve(inst, opt - 1, dir='backward')
        res['lb'].append(time.time() - t)
    # deterministic expansion counts
    for tag, d in [('lf', 'forward'), ('lb', 'backward')]:
        e = 0
        for inst, opt in cs:
            s = {}; lfp.solve(inst, opt - 1, dir=d, stats=s); e += s['expanded']
        exp[tag] = e
    for tag, d in [('df', 'forward'), ('db', 'backward')]:
        e = 0
        for (inst, opt), (est, q) in zip(cs, ests):
            s = {}
            ii = inst if d == 'forward' else rev(inst)
            wos.sgs_solve(ii, opt - 1, est=est if d == 'forward' else q,
                          q=q if d == 'forward' else est, force=True,
                          nodecap=300000, stats=s)
            e += s['nodes']
        exp[tag] = e
    out = dict(times={k: statistics.median(v) for k, v in res.items()},
               raw=res, expansions=exp)
    print(json.dumps(out, indent=1))
    json.dump(out, open('exp/v34/res_lfp.json', 'w'), indent=1)


def rev(inst):
    n = inst['n']; z = dict(inst)
    z['pred'] = [list(inst['succ'][i]) for i in range(n)]
    z['succ'] = [list(inst['pred'][i]) for i in range(n)]
    return z


if __name__ == '__main__':
    main()
