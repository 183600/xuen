import sys, pickle, time, json
sys.path[:0] = ['exp/v60', 'exp/v13', 'exp/v50']
import sdecc
try:
    import ecc
except Exception:
    ecc = None

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
    out = []
    for x in d:
        if isinstance(x, tuple):
            out.append((x[0], x[1]))
        else:
            out.append((x['inst'], x['opt']))
    return out

def run(no_branch=True):
    out = {}
    for name, f in FILES.items():
        cs = load(f)
        rows = []
        t0 = time.time()
        for idx, (inst, opt) in enumerate(cs):
            h = opt - 1
            t1 = time.time()
            v, st = sdecc.sdecc_no(inst, h, nodecap=(5000 if no_branch else 5000))
            dt = time.time() - t1
            rows.append(dict(idx=idx, n=inst['n'], m=inst['m'], v=v,
                             root=st['root'], nodes=st['nodes'], t=dt))
        out[name] = dict(rows=rows, t=time.time() - t0,
                         root_no=sum(1 for r in rows if r['root'] == 'infeasible'),
                         nodes=sum(r['nodes'] for r in rows),
                         no=sum(1 for r in rows if r['v'] is False),
                         unknown=sum(1 for r in rows if r['v'] is None),
                         yes=sum(1 for r in rows if r['v'] is True))
        print(name, out[name]['root_no'], '/', len(cs), 'NO', out[name]['no'],
              'nodes', out[name]['nodes'], 't', round(out[name]['t'], 3), flush=True)
    return out

if __name__ == '__main__':
    o = run()
    json.dump(o, open('exp/v60/bench_no.json', 'w'), indent=1)
