"""v3.5 benchmark: v3.0 (WOS) vs v3.5 (WOS+PCLP), interleaved, h=OPT-1 and h=OPT."""
import sys, time, json, pickle, statistics
sys.path[:0] = ['exp/v35', 'exp/v30', 'exp/v29', 'exp/v13', 'exp/v20',
                'exp/v25']
import root_v30, root_v35


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


CASES = [('holdout50', 'exp/v20/holdout_cases50.pkl'),
         ('hard3', 'exp/v13/hard3.pkl'),
         ('deep8', 'exp/v18/deep.pkl'),
         ('large_a', 'exp/v14/large_a.pkl'),
         ('large_b', 'exp/v14/large_b.pkl'),
         ('large_het', 'exp/v14/large_het.pkl'),
         ('synth45', 'exp/v28/synth2_45.pkl')]


def run(mod, cases, hmod, reps=3, **kw):
    times = []
    rows = []
    for rep in range(reps):
        t0 = time.time()
        rr = []
        for inst, opt in cases:
            st = {}
            ok, st = mod.bb_solve(inst, opt + hmod, stats=st, **kw)
            rr.append(dict(n=inst['n'], m=inst['m'], ok=ok,
                           verdict=st.get('verdict'), os=st.get('os_nodes'),
                           lp=st.get('lp'), lp_cuts=st.get('lp_cuts'),
                           t=st.get('t', 0.0)))
        dt = time.time() - t0
        times.append(dt)
        if rep == reps - 1:
            rows = rr
    return rows, dict(t=round(statistics.median(times), 4),
                      yes=sum(1 for r in rows if r['ok']),
                      os=sum(r['os'] or 0 for r in rows),
                      verdicts={v: sum(1 for r in rows if r['verdict'] == v)
                                for v in sorted(set(r['verdict'] for r in rows))})


def main():
    out = {}
    for tag, hmod in [('NO', -1), ('YES', 0)]:
        out[tag] = {}
        for name, f in CASES:
            cases = load(f)
            r3, a3 = run(root_v30, cases, hmod)
            r5, a5 = run(root_v35, cases, hmod)
            same = sum(1 for x, y in zip(r3, r5) if bool(x['ok']) == bool(y['ok']))
            out[tag][name] = dict(n=len(cases), v30=a3, v35=a5, same=same,
                                  rows30=r3, rows35=r5)
            print(tag, name, 'v30', a3['t'], a3['verdicts'], '| v35',
                  a5['t'], a5['verdicts'], '| same', same, flush=True)
        tot3 = sum(v['v30']['t'] for v in out[tag].values())
        tot5 = sum(v['v35']['t'] for v in out[tag].values())
        out[tag]['_total'] = dict(v30=round(tot3, 4), v35=round(tot5, 4),
                                  speed=round(tot3 / tot5, 3) if tot5 else None)
        print(tag, '_total', out[tag]['_total'], flush=True)
    json.dump(out, open('exp/v35/res_e2e.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
