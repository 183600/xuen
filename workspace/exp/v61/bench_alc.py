"""Benchmark ALC on all 141 NO instances at h=OPT-1."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v61', 'exp/v60', 'exp/v13']
from alc import ALC
import cert as v60cert

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
    t00 = time.time()
    for name, f in FILES.items():
        rows = []
        tset = time.time()
        for idx, (inst, opt) in enumerate(load(f)):
            h = opt - 1
            t0 = time.time()
            a = ALC(inst, h)
            v, st = a.decide()
            dt = time.time() - t0
            c = st['cert']
            # first infeasible LP event (root-level NO moment)
            first_inf = None
            for e in st['events']:
                if e['kind'] == 'lp' and e['status'] == 'infeasible':
                    first_inf = e['lp']
                    break
            rows.append(dict(idx=idx, v=v, lp=st['lp_solves'],
                             nodes=st['nodes'], cuts=st['cuts'],
                             cert_kind=(c['kind'] if c else None),
                             cert_beta=(len(c['beta']) if c else None),
                             cert_dom=(len(c['dom']) if c else None),
                             cert_scale=(c.get('scale') if c else None),
                             cert_ok=st['cert_ok'],
                             cert_t=st['cert_t'], cert_calls=st['cert_calls'],
                             first_inf=first_inf, t=dt,
                             events=st['events']))
        out[name] = dict(
            n=len(rows),
            no=sum(1 for r in rows if r['v'] is False),
            unknown=sum(1 for r in rows if r['v'] is None),
            cert_ok=sum(1 for r in rows if r['cert_ok']),
            lp=sum(r['lp'] for r in rows),
            nodes=sum(r['nodes'] for r in rows),
            cuts=sum(r['cuts'] for r in rows),
            first_inf_1=sum(1 for r in rows if r['first_inf'] == 1),
            t=time.time() - tset,
            cert_t=sum(r['cert_t'] for r in rows),
            rows=rows)
        print(name, {k: v for k, v in out[name].items() if k != 'rows'},
              flush=True)
    # totals
    keys = ['n', 'no', 'unknown', 'cert_ok', 'lp', 'nodes', 'cuts',
            'first_inf_1']
    tot = {k: sum(out[n][k] for n in FILES) for k in keys}
    tot['t'] = sum(out[n]['t'] for n in FILES)
    out['_total'] = tot
    # certificate sizes
    allrows = [r for n in FILES for r in out[n]['rows']]
    ck = [r for r in allrows if r['cert_kind'] == 'packing']
    out['_cert_stats'] = dict(
        packings=len(ck),
        beta_median=sorted(r['cert_beta'] for r in ck)[len(ck)//2] if ck else None,
        beta_max=max((r['cert_beta'] for r in ck), default=None),
        dom_median=sorted(r['cert_dom'] for r in ck)[len(ck)//2] if ck else None,
        dom_max=max((r['cert_dom'] for r in ck), default=None),
        scale_median=sorted(r['cert_scale'] for r in ck)[len(ck)//2] if ck else None,
        cuts_median=sorted(r['cuts'] for r in allrows)[len(allrows)//2],
        cuts_max=max(r['cuts'] for r in allrows),
    )
    out['_wall'] = time.time() - t00
    json.dump(out, open('exp/v61/alc_stats.json', 'w'), indent=1)
    print('TOTAL', tot)
    print('CERT', out['_cert_stats'])
    print('wall', round(out['_wall'], 2))


if __name__ == '__main__':
    main()
