import sys, pickle, time, json
sys.path[:0] = ['exp/v60', 'exp/v13']
import cert

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
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']) for x in d]

def main():
    out = {}
    for name, f in FILES.items():
        rows = []
        t0 = time.time()
        for idx, (inst, opt) in enumerate(load(f)):
            h = opt - 1
            c = cert.integer_certificate(inst, h)
            if c is None:
                rows.append(dict(idx=idx, ok=False, reason='none'))
                continue
            rows.append(dict(idx=idx, ok=True, scale=c['scale'],
                             beta=len(c['beta']), dom=len(c['dom']),
                             exp=len(c['exp']), obj=c['obj']))
        ok = [r for r in rows if r['ok']]
        out[name] = dict(rows=rows, t=time.time() - t0,
                         n=len(rows), ok=len(ok),
                         max_scale=max([r['scale'] for r in ok], default=0),
                         max_cuts=max([r['beta'] + r['dom'] for r in ok], default=0),
                         max_dom=max([r['dom'] for r in ok], default=0),
                         max_beta=max([r['beta'] for r in ok], default=0))
        print(name, out[name]['ok'], '/', out[name]['n'],
              'maxD', out[name]['max_scale'], 'maxcuts', out[name]['max_cuts'],
              't', round(out[name]['t'], 3), flush=True)
    json.dump(out, open('exp/v60/bench_cert.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
