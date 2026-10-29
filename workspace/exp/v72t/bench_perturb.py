import sys, os, json, time, pickle, collections
sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v72t', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from tca import TCA, check_proof
D = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
out = {}
for side in ['YES', 'NO']:
    rows = []
    for name, k, inst, opt, an, al in D:
        h = opt if side == 'YES' else opt - 1
        t0 = time.perf_counter()
        try:
            tc = TCA(inst, h, primal_tries=100, dec_cap=200000,
                     dual_first_budget=3, dual_budget=100000,
                     dual_nodecap=5000)
            v, st = tc.decide()
            row = dict(case=name, k=k, n=inst['n'], h=h, verdict=v,
                       engine=st.get('engine'), t=time.perf_counter() - t0,
                       lp=st.get('lp'), nodes=st.get('nodes'),
                       proof_ok=None)
            if v is False:
                pv, why, pst = check_proof(inst, h, st['proof'])
                row['proof_ok'] = (pv == 'NO')
                row['proof_why'] = why
                row['proof_stats'] = pst
            rows.append(row)
        except Exception as e:
            rows.append(dict(case=name, k=k, n=inst['n'], h=h,
                             verdict='ERR', engine=None,
                             t=time.perf_counter() - t0,
                             lp=None, nodes=None, err=repr(e)))
        print(side, name, k, rows[-1]['verdict'], rows[-1]['engine'],
              round(rows[-1]['t'], 3), flush=True)
    out[side] = rows
    print(side, 'SUMMARY', collections.Counter(r['verdict'] for r in rows),
          collections.Counter(r.get('engine') for r in rows),
          't', round(sum(r['t'] for r in rows), 3),
          'proof_ok', sum(r.get('proof_ok') is True for r in rows))
json.dump(out, open('exp/v72t/tca_perturb.json', 'w'), indent=0)
