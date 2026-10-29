import pickle, sys, time, json
sys.path[:0] = ['exp/v13', 'exp/v28']
import sgs

def load(f):
    d = pickle.load(open(f, 'rb'))
    out = []
    for x in d:
        if isinstance(x, tuple):
            out.append((x[0], x[1]))
        else:
            out.append((x['inst'], x['opt']))
    return out

SETS = {
 'hard3': 'exp/v13/hard3.pkl',
 'large_a': 'exp/v14/large_a.pkl',
 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl',
 'deep': 'exp/v18/deep.pkl',
 'holdout': 'exp/v20/holdout_cases50.pkl',
}

res = {}
for name, f in SETS.items():
    cases = load(f)
    rows = []
    t_all = time.time()
    for idx, (inst, opt) in enumerate(cases):
        full_e = all(len(set(inst['elig'][i])) == inst['m'] for i in range(inst['n']))
        row = dict(idx=idx, n=inst['n'], m=inst['m'], full=full_e)
        for tag, h in [('hM1', opt - 1), ('h0', opt)]:
            st = {}
            t0 = time.time()
            v, sch = sgs.sgs_solve(inst, h, nodecap=200000, dom=False, stats=st)
            dt = time.time() - t0
            okv = None
            if v is True:
                okv = sgs.validate(inst, h, sch)[0]
            row[tag] = dict(v=v, nodes=st.get('nodes'), t=round(dt, 4), valid=okv)
        rows.append(row)
    tot = dict(n=sum(r['hM1']['nodes'] for r in rows),
               t=round(time.time() - t_all, 3),
               no=sum(1 for r in rows if r['hM1']['v'] is False),
               unk=sum(1 for r in rows if r['hM1']['v'] is None),
               yes=sum(1 for r in rows if r['hM1']['v'] is True))
    res[name] = dict(rows=rows, total=tot)
    print(name, json.dumps(tot))
json.dump(res, open('exp/v28/res_all.json', 'w'), indent=1)
