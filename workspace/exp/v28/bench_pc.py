"""v2.4 benchmark: root certificate cascade on all held-out families."""
import sys, time, json, pickle
sys.path[:0] = ['exp/v13', 'exp/v15', 'exp/v16', 'exp/v20', 'exp/v24',
                'exp/v25', 'exp/v28']
import root_pc


def load(f):
    d = pickle.load(open(f, 'rb'))
    out = []
    for x in d:
        out.append((x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']))
    return out


def synth45():
    d = pickle.load(open('exp/v28/synth2_45.pkl', 'rb'))
    return [(x[0], x[1]) for x in d]


def run(setname, cases, **kw):
    rows = []
    t0 = time.time()
    for idx, (inst, opt) in enumerate(cases):
        st = {}
        ok, st = root_pc.pc_solve(inst, opt - 1, stats=st, **kw)
        rows.append(dict(set=setname, idx=idx, n=inst['n'], m=inst['m'],
                         S=st.get('S'), full=st.get('full'), gate=st.get('gate'),
                         verdict=st.get('verdict'), ok=ok,
                         t=round(st.get('t', 0.0), 6),
                         icc_kind=(st.get('cert')[0] if st.get('cert') else None),
                         icc_hits=st.get('icc_hits', 0),
                         probe=st.get('probe_nodes'), os=st.get('os_nodes'),
                         pace=st.get('pace_nodes'),
                         tables=st.get('pace_tables')))
    agg = dict(set=setname, n=len(rows), t=round(time.time() - t0, 4),
               nodes_probe=sum(r['probe'] or 0 for r in rows),
               nodes_os=sum(r['os'] or 0 for r in rows),
               nodes_pace=sum(r['pace'] or 0 for r in rows),
               icc=sum(1 for r in rows if r['verdict'] == 'ICC'),
               cps=sum(1 for r in rows if r['verdict'] == 'CPS'),
               os=sum(1 for r in rows if r['verdict'] == 'OS'),
               pace_n=sum(1 for r in rows if r['verdict'] == 'PACE'),
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
        'synth45': synth45(),
    }
    allrows = {}
    aggs = {}
    for name, cs in cases.items():
        rows, agg = run(name, cs)
        allrows[name] = rows
        aggs[name] = agg
        print(name, json.dumps(agg, ensure_ascii=False), flush=True)
    # residual 5
    rows, agg = run('residual5', [cases['holdout50'][i] for i in [5, 21, 32, 42, 47]])
    allrows['residual5'] = rows
    aggs['residual5'] = agg
    print('residual5', json.dumps(agg, ensure_ascii=False), flush=True)
    json.dump(dict(aggs=aggs, rows=allrows),
              open('exp/v28/res_pc.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
