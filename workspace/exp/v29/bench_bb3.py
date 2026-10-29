"""v2.5 benchmark: ICC -> OS-BBX -> PACE on all v2.4 families."""
import sys, time, json, pickle
sys.path[:0] = ['exp/v29', 'exp/v13', 'exp/v15', 'exp/v16', 'exp/v20',
                'exp/v24', 'exp/v25']
import root_bb3 as root_bb


def load(f):
    d = pickle.load(open(f, 'rb'))
    out = []
    for x in d:
        out.append((x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']))
    return out


def run(setname, cases, hmod=-1, **kw):
    rows = []
    t0 = time.time()
    for idx, (inst, opt) in enumerate(cases):
        h = opt + hmod
        st = {}
        ok, st = root_bb.bb_solve(inst, h, stats=st, **kw)
        rows.append(dict(set=setname, idx=idx, n=inst['n'], m=inst['m'],
                         S=st.get('S'), full=st.get('full'), gate=st.get('gate'),
                         verdict=st.get('verdict'), ok=ok,
                         t=round(st.get('t', 0.0), 6),
                         icc_kind=(st.get('cert')[0] if st.get('cert') else None),
                         os=st.get('os_nodes'), os_memo=st.get('os_memo'),
                         pace=st.get('pace_nodes'), tables=st.get('pace_tables')))
    agg = dict(set=setname, hmod=hmod, n=len(rows), t=round(time.time() - t0, 4),
               nodes_os=sum(r['os'] or 0 for r in rows),
               nodes_pace=sum(r['pace'] or 0 for r in rows),
               icc=sum(1 for r in rows if r['verdict'] == 'ICC'),
               cps=sum(1 for r in rows if r['verdict'] == 'CPS'),
               os=sum(1 for r in rows if r['verdict'] == 'OS'),
               pace_n=sum(1 for r in rows if r['verdict'] == 'PACE'),
               yes=sum(1 for r in rows if r['ok']),
               verdicts={v: sum(1 for r in rows if r['verdict'] == v)
                         for v in sorted(set(r['verdict'] for r in rows))})
    return rows, agg


def main():
    cases = {
        'holdout50': load('exp/v20/holdout_cases50.pkl'),
        'hard3': load('exp/v13/hard3.pkl'),
        'deep8': load('exp/v18/deep.pkl'),
        'large_a': load('exp/v14/large_a.pkl'),
        'large_b': load('exp/v14/large_b.pkl'),
        'large_het': load('exp/v14/large_het.pkl'),
        'synth45': load('exp/v28/synth2_45.pkl'),
    }
    cases['residual5'] = [cases['holdout50'][i] for i in [5, 21, 32, 42, 47]]
    cases['core38'] = cases['hard3'] + cases['large_a'] + cases['large_b'] + cases['large_het']
    allrows, aggs = {}, {}
    for name, cs in cases.items():
        rows, agg = run(name, cs, hmod=-1)
        allrows[name], aggs[name] = rows, agg
        print(name, json.dumps(agg, ensure_ascii=False), flush=True)
    # feasible side: h = OPT, verify YES
    yesrows, yesaggs = {}, {}
    for name in ['holdout50', 'hard3', 'deep8', 'residual5', 'synth45']:
        rows, agg = run(name + '_YES', cases[name], hmod=0)
        yesrows[name], yesaggs[name] = rows, agg
        print(name + '_YES', json.dumps(agg, ensure_ascii=False), flush=True)
    json.dump(dict(aggs=aggs, rows=allrows, yesaggs=yesaggs, yesrows=yesrows),
              open('exp/v29/res_bb3.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
