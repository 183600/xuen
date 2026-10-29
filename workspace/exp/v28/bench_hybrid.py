import pickle, sys, time, json
sys.path[:0] = ['exp/v13', 'exp/v20', 'exp/v28']
import sgs, hybrid

CASES = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
rows = []
for idx in [5, 21, 32, 42, 47]:
    inst, opt = CASES[idx]; h = opt - 1
    st = {}
    t0 = time.time()
    import po
    est, q = po.heads_tails(inst, 0, [0]*inst['n'])
    v = hybrid.hybrid_certify(inst, inst['full'], tuple([0]*inst['m']),
                              est, q, h, stats=st)
    rows.append(dict(idx=idx, v=v, t=round(time.time()-t0, 4),
                     probe=st.get('probe_nodes'), probe_res=st.get('probe_res'),
                     os=st.get('os_nodes')))
    print(json.dumps(rows[-1]))
print('totals', dict(t=round(sum(r['t'] for r in rows), 4),
                     probe=sum(r['probe'] or 0 for r in rows),
                     os=sum(r['os'] or 0 for r in rows)))
json.dump(rows, open('exp/v28/res_hybrid5.json', 'w'), indent=1)
