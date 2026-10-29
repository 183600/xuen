"""Benchmark DCS-ALC proof trees on the 141 NO instances."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v70', 'exp/v61', 'exp/v60', 'exp/v13']
from dcs import DCS, verify_tree

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl',
 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl',
 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl',
 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl',
}

def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]

def run(inst, opt, look):
    h = opt - 1
    a = DCS(inst, h)
    t0 = time.time()
    if look:
        root, _ = a.build_look(frozenset(), 500000, look_budget=8)
    else:
        root, _ = a.build(frozenset(), 500000)
    dt = time.time() - t0
    ok, why = verify_tree(inst, h, root, frozenset(), a.elig_aware)
    st = a.stats(root)
    st.update(t=dt, verify=ok, why=why, verdict=root.status)
    return st

def main():
    out = {}
    t00 = time.time()
    for name, f in FILES.items():
        rows = []
        tset = time.time()
        for idx, (inst, opt) in enumerate(load(f)):
            r0 = run(inst, opt, False)
            r1 = run(inst, opt, True)
            rows.append(dict(idx=idx, base=r0, look=r1))
        def agg(key):
            return dict(
                n=len(rows),
                no=sum(1 for r in rows if r[key]['verdict'] == 'no'),
                verify=sum(1 for r in rows if r[key]['verify']),
                lp=sum(r[key]['lp'] for r in rows),
                nodes=sum(r[key]['nodes'] for r in rows),
                leaves=sum(r[key]['leaves'] for r in rows),
                splits=sum(r[key]['splits'] for r in rows),
                certs=sum(r[key]['certs'] for r in rows),
                cert_ok=sum(r[key]['cert_ok'] for r in rows),
                depth=max(r[key]['depth'] for r in rows),
                t=sum(r[key]['t'] for r in rows),
                cert_t=sum(r[key]['cert_t'] for r in rows),
            )
        out[name] = dict(base=agg('base'), look=agg('look'), rows=rows)
        print(name, 'BASE', out[name]['base'], flush=True)
        print(name, 'LOOK', out[name]['look'], flush=True)
    keys = ['n', 'no', 'verify', 'lp', 'nodes', 'leaves', 'splits', 'certs',
            'cert_ok', 't', 'cert_t']
    tot = {}
    for mode in ['base', 'look']:
        tot[mode] = {k: sum(out[n][mode][k] for n in FILES) for k in keys}
        tot[mode]['depth'] = max(out[n][mode]['depth'] for n in FILES)
    out['_total'] = tot
    out['_wall'] = time.time() - t00
    json.dump(out, open('exp/v70/dcs_stats.json', 'w'), indent=1)
    print('TOTAL BASE', tot['base'])
    print('TOTAL LOOK', tot['look'])
    print('wall', round(out['_wall'], 2))

if __name__ == '__main__':
    main()
