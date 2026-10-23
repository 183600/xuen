"""v2.5 ablation / hyperparameter landscape on held-out 50."""
import sys, time, json, pickle
sys.path[:0] = ['exp/v28', 'exp/v29', 'exp/v13']
import po, sgs, os_pack, os_bit, os_prop


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']) for x in d]


def rev(inst):
    n = inst['n']; z = dict(inst)
    z['pred'] = [list(inst['succ'][i]) for i in range(n)]
    z['succ'] = [list(inst['pred'][i]) for i in range(n)]
    return z


CASES = load('exp/v20/holdout_cases50.pkl')


def run(fn, revdir=False, **kw):
    nodes = 0; t0 = time.time(); bad = 0
    for inst, opt in CASES:
        h = opt - 1
        est, q = po.heads_tails(inst, 0, [0] * inst['n'])
        st = {}
        if revdir:
            r = rev(inst)
            fn(r, h, rem=r['full'], A=(0,) * r['m'], est=q, q=est,
               nodecap=300000, stats=st, **kw)
        else:
            v, _ = fn(inst, h, rem=inst['full'], A=(0,) * inst['m'], est=est,
                      q=q, nodecap=300000, stats=st, **kw)
            bad += (v is not False)
        nodes += st.get('nodes', 0)
    return dict(nodes=nodes, t=round(time.time() - t0, 3), bad=bad)


def main():
    out = {}
    out['v2.4 OS (tuple memo)'] = run(sgs.sgs_solve, dom=False, order='lpt')
    out['v2.4 OS dom=True'] = run(sgs.sgs_solve, dom=True, order='lpt')
    out['os_pack rsi=False'] = run(os_pack.sgs_solve, rsi=False)
    out['os_pack rsi=True'] = run(os_pack.sgs_solve, rsi=True)
    out['os_pack order=edd'] = run(os_pack.sgs_solve, rsi=True, order='edd')
    out['os_pack order=spt'] = run(os_pack.sgs_solve, rsi=True, order='spt')
    out['os_bit rsi=True'] = run(os_bit.sgs_solve, rsi=True, bit=True)
    out['os_bit + atpf'] = run(os_bit.sgs_solve, rsi=True, bit=True, atpf=True)
    out['os_bit + EDF(d<=10)'] = run(os_bit.sgs_solve, rsi=True, bit=True, edf_depth=10)
    out['os_bit + RICC(ready<=4)'] = run(os_bit.sgs_solve, rsi=True, bit=True, ricc=4)
    out['os_prop + forcing'] = run(os_prop.sgs_solve, force=True)
    out['os_pack backward'] = run(os_pack.sgs_solve, revdir=True, rsi=True)
    print(json.dumps(out, indent=1))
    json.dump(out, open('exp/v29/res_ablate.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
