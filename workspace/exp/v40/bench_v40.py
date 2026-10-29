"""v4.0 benchmark: CP -> HEC -> ICC -> backward-LFP -> PACE."""
import sys, json, pickle
sys.path[:0] = ['exp/v40', 'exp/v30', 'exp/v31', 'exp/v29', 'exp/v13', 'exp/v20', 'exp/v15', 'exp/v16', 'exp/v24', 'exp/v25']
import root_v40, root_v30, root_v31

def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]

def run(fn, cases, hm, **kw):
    rows = []
    for idx, (inst, opt) in enumerate(cases):
        st = {}
        ok, st = fn(inst, opt + hm, stats=st, **kw)
        rows.append(dict(idx=idx, n=inst['n'], m=inst['m'], ok=ok,
                         verdict=st.get('verdict'), os=st.get('os_nodes'),
                         t=st.get('t', 0.0)))
    return rows

def main():
    sets = {
        'holdout50': 'exp/v20/holdout_cases50.pkl',
        'hard3': 'exp/v13/hard3.pkl',
        'deep8': 'exp/v18/deep.pkl',
        'large_a': 'exp/v14/large_a.pkl',
        'large_b': 'exp/v14/large_b.pkl',
        'large_het': 'exp/v14/large_het.pkl',
        'synth45': 'exp/v28/synth2_45.pkl',
    }
    out = {}
    for name, f in sets.items():
        cs = load(f)
        r30 = run(root_v30.bb_solve, cs, -1)
        r31 = run(root_v31.bb_solve, cs, -1)
        r40 = run(root_v40.bb_solve, cs, -1)
        out[name] = dict(
            v30=dict(t=sum(r['t'] for r in r30), os=sum(r['os'] or 0 for r in r30)),
            v31=dict(t=sum(r['t'] for r in r31), os=sum(r['os'] or 0 for r in r31)),
            v40=dict(t=sum(r['t'] for r in r40), os=sum(r['os'] or 0 for r in r40)),
            rows30=r30, rows40=r40,
            same=sum(1 for a, b in zip(r30, r40) if bool(a['ok']) == bool(b['ok'])))
        print('%-10s v30 %.4f v31 %.4f v40 %.4f nodes %d same %d' % (
            name, out[name]['v30']['t'], out[name]['v31']['t'],
            out[name]['v40']['t'], out[name]['v40']['os'], out[name]['same']),
            flush=True)
    out['_yes'] = {}
    for name in ['holdout50', 'hard3', 'deep8', 'synth45']:
        cs = load(sets[name])
        r30 = run(root_v30.bb_solve, cs, 0)
        r40 = run(root_v40.bb_solve, cs, 0)
        out['_yes'][name] = dict(
            v30=dict(t=sum(r['t'] for r in r30)),
            v40=dict(t=sum(r['t'] for r in r40)),
            rows30=r30, rows40=r40,
            same=sum(1 for a, b in zip(r30, r40) if bool(a['ok']) == bool(b['ok'])))
        print(name + '_YES v30 %.4f v40 %.4f same %d' % (
            out['_yes'][name]['v30']['t'], out['_yes'][name]['v40']['t'],
            out['_yes'][name]['same']), flush=True)
    out['_total'] = dict(
        v30=sum(v['v30']['t'] for k, v in out.items() if not k.startswith('_')),
        v31=sum(v['v31']['t'] for k, v in out.items() if not k.startswith('_')),
        v40=sum(v['v40']['t'] for k, v in out.items() if not k.startswith('_')))
    print('TOTAL', out['_total'])
    json.dump(out, open('exp/v40/res_v40.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
