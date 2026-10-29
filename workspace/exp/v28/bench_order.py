import pickle, sys, time, json, random, statistics
sys.path[:0] = ['exp/v13', 'exp/v28']
import sgs

CASES = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
NOIDX = [5, 21, 32, 42, 47]

# E4a: NO side -- exhaustive search, order should be invariant
res_no = {}
for idx in NOIDX:
    inst, opt = CASES[idx]; h = opt - 1
    row = {}
    for o in ['lpt', 'edd', 'spt']:
        st = {}; v, _ = sgs.sgs_solve(inst, h, nodecap=300000, order=o, stats=st)
        row[o] = st['nodes']
    seeds = []
    for sd in range(8):
        st = {}; v, _ = sgs.sgs_solve(inst, h, nodecap=300000,
                                      rng=random.Random(sd), stats=st)
        seeds.append(st['nodes'])
    row['random'] = sorted(set(seeds))
    res_no[idx] = row
    print('NO', idx, row)

# E4b: YES side -- nodes to the first feasible leaf
res_yes = {}
for o in ['lpt', 'edd', 'spt']:
    ns = []
    for idx, (inst, opt) in enumerate(CASES):
        st = {}; v, sch = sgs.sgs_solve(inst, opt, nodecap=300000, order=o, stats=st)
        assert v is True, (idx, o)
        ns.append(st['nodes'])
    res_yes[o] = dict(total=sum(ns), med=statistics.median(ns), mx=max(ns))
    print('YES', o, res_yes[o])
rnd = []
for sd in range(12):
    ns = []
    for idx, (inst, opt) in enumerate(CASES):
        st = {}; v, sch = sgs.sgs_solve(inst, opt, nodecap=300000,
                                        rng=random.Random(sd * 1000 + idx), stats=st)
        ns.append(st['nodes'])
    rnd.append(sum(ns))
res_yes['random_totals'] = sorted(rnd)
print('YES random totals', sorted(rnd))
json.dump(dict(no=res_no, yes=res_yes), open('exp/v28/res_order.json', 'w'), indent=1)
