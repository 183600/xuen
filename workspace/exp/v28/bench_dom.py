import pickle, sys, time, json
sys.path[:0] = ['exp/v13', 'exp/v28']
import sgs

CASES = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
out = {}
for dom in [False, True]:
    tot = 0; t0 = time.time(); rows = []
    for idx in [5, 21, 32, 42, 47]:
        inst, opt = CASES[idx]; h = opt - 1
        st = {}
        v, sch = sgs.sgs_solve(inst, h, nodecap=300000, dom=dom, stats=st)
        rows.append(dict(idx=idx, v=v, n=st['nodes'], t=None))
        tot += st['nodes']
    out['dom' if dom else 'exact'] = dict(total=tot, t=round(time.time()-t0, 3), rows=rows)
    print(dom, tot, round(time.time()-t0, 3), [(r['idx'], r['n']) for r in rows])
json.dump(out, open('exp/v28/res_dom.json', 'w'), indent=1)
