import pickle, sys, json
sys.path[:0] = ['exp/v13', 'exp/v28']
import sgs
C = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
rows = []
for idx in [5, 21, 32, 42, 47]:
    inst, opt = C[idx]; h = opt - 1
    st = {}
    v, _ = sgs.sgs_solve(inst, h, nodecap=300000, stats=st)
    W = st['nodes']; sizes = st['root_sizes']; D = max(sizes)
    bound = 4 / (1 + 4 * D / W)
    rows.append(dict(idx=idx, W=W, children=sizes, D=D, ratio=round(D / W, 3),
                     bound4=round(bound, 2)))
    print(json.dumps(rows[-1]))
json.dump(rows, open('exp/v28/res_par.json', 'w'), indent=1)
