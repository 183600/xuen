import pickle, sys, json
sys.path[:0] = ['exp/v13', 'exp/v28']
import sgs

def assign_exact(inst, h, sched):
    n, m, p = inst['n'], inst['m'], inst['p']
    elig = inst['elig']
    order = sorted(range(n), key=lambda i: (sched[i], -p[i]))
    free = [0] * m
    # backtracking, most-constrained-first among the prefix
    def rec(k):
        if k == n: return True
        i = order[k]
        cand = [c for c in elig[i] if free[c] <= sched[i]]
        cand.sort(key=lambda c: -free[c])
        for c in cand:
            old = free[c]; free[c] = sched[i] + p[i]
            if rec(k+1): return True
            free[c] = old
        return False
    return rec(0)

D = pickle.load(open('exp/v14/large_het.pkl', 'rb'))
rows = []
for idx, x in enumerate(D):
    inst, opt = x['inst'], x['opt']
    for tag, h in [('hM1', opt-1), ('h0', opt)]:
        st = {}
        v, sch = sgs.sgs_solve(inst, h, nodecap=200000, stats=st)
        row = dict(idx=idx, tag=tag, v=v, nodes=st.get('nodes'))
        if v is True:
            row['greedy'] = sgs.validate(inst, h, sch)[0]
            row['exact_assign'] = assign_exact(inst, h, sch)
        rows.append(row)
        print(json.dumps(row))
json.dump(rows, open('exp/v28/res_het2.json','w'), indent=1)
