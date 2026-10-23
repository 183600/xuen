import sys, pickle, time, json
sys.path[:0] = ['exp/v60', 'exp/v13']
import lazy

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


def main():
    out = {}
    tot = dict(n=0, root_no=0, branch_cases=0, branch_nodes=0, nodes=0,
               cuts=0, t=0.0, no=0, unknown=0)
    t00 = time.time()
    for name, f in FILES.items():
        cs = load(f)
        rows = []
        t0 = time.time()
        for idx, (inst, opt) in enumerate(cs):
            h = opt - 1
            t1 = time.time()
            v, st = lazy.lazy_no(inst, h)
            rows.append(dict(idx=idx, v=v, root=st['root'], nodes=st['nodes'],
                             cuts=st['cuts_added'], rounds=st['rounds'],
                             branches=st['branches'], t=time.time() - t1))
        root_no = sum(1 for r in rows if r['root'] == 'infeasible')
        nodes = sum(r['nodes'] for r in rows)
        bnodes = sum(r['nodes'] - 1 for r in rows if r['nodes'] > 1)
        bc = sum(1 for r in rows if r['nodes'] > 1)
        cuts = sum(r['cuts'] for r in rows)
        no = sum(1 for r in rows if r['v'] is False)
        unk = sum(1 for r in rows if r['v'] is None)
        out[name] = dict(n=len(cs), root_no=root_no, branch_cases=bc,
                         branch_nodes=bnodes, nodes=nodes, cuts=cuts,
                         no=no, unknown=unk, t=time.time() - t0, rows=rows)
        for k in ('n', 'root_no', 'branch_cases', 'branch_nodes', 'nodes',
                  'cuts', 'no', 'unknown'):
            tot[k] += out[name][k]
        tot['t'] += out[name]['t']
        print(name, 'root', root_no, '/', len(cs), 'branch', bc,
              'bnodes', bnodes, 'nodes', nodes, 'cuts', cuts,
              't', round(out[name]['t'], 3), flush=True)
    out['_total'] = tot
    out['_wall'] = time.time() - t00
    json.dump(out, open('exp/v60/lazy_bench.json', 'w'), indent=1)
    print('TOTAL', {k: (round(v, 3) if isinstance(v, float) else v)
                    for k, v in tot.items()}, 'wall', round(out['_wall'], 3))


if __name__ == '__main__':
    main()
