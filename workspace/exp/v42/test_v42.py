import sys, random, json
sys.path[:0] = ['exp/v42', 'exp/v41', 'exp/v31', 'exp/v30', 'exp/v29', 'exp/v13',
                'exp/v20', 'exp/v25', 'exp/v16', 'exp/v15', 'exp/v24']
import po, root_v42

TP = {'mint_on': False, 'hpack_on': False, 'cps_on': False}
SMALL = {'comps': ['HEC', 'ICC', 'MPC', 'WOS', 'PACE'], 'pace': TP}
LARGE = {'comps': ['HEC', 'PACE'], 'pace': TP}

def solve(inst, h):
    cfg = SMALL if inst['n'] <= 16 else LARGE
    return root_v42.bb_solve(inst, h, cfg=cfg, stats={})

def brute(inst, h):
    n, m, p = inst['n'], inst['m'], inst['p']
    indeg = [len(inst['pred'][i]) for i in range(n)]
    q = [i for i in range(n) if indeg[i] == 0]
    topo = []
    while q:
        u = q.pop(); topo.append(u)
        for v in inst['succ'][u]:
            indeg[v] -= 1
            if indeg[v] == 0: q.append(v)
    if len(topo) < n: return False
    fin = [0] * n
    busy = [0] * m
    def rec(k):
        if k == n: return True
        i = topo[k]; lo = 0
        for j in inst['pred'][i]:
            if fin[j] > lo: lo = fin[j]
        for t in range(lo, h - p[i] + 1):
            mask = ((1 << p[i]) - 1) << t
            for kk in inst['elig'][i]:
                if busy[kk] & mask: continue
                busy[kk] |= mask; fin[i] = t + p[i]
                if rec(k + 1): return True
                busy[kk] &= ~mask
        return False
    return rec(0)

def main():
    rng = random.Random(42042)
    trials = feas = mis = hec_bad = mpc_bad = 0
    for _ in range(300):
        n = rng.randint(3, 6); m = rng.randint(1, 3)
        p = [rng.randint(1, 4) for _ in range(n)]
        pred = [[] for _ in range(n)]
        for j in range(1, n):
            for i in range(j):
                if rng.random() < 0.25: pred[j].append(i)
        elig = []
        for i in range(n):
            k = rng.randint(1, m)
            elig.append(sorted(rng.sample(range(m), k)))
        inst = po.make_inst(p, m, pred, elig)
        est, q = po.heads_tails(inst, 0, [0] * n)
        for h in range(max(est[i] + p[i] + q[i] for i in range(n)), 12):
            b = brute(inst, h)
            ok, st = solve(inst, h)
            trials += 1; feas += 1 if b else 0
            if bool(ok) != bool(b):
                mis += 1
                print('MISMATCH', n, m, h, p, pred, elig, 'brute', b, 'solver', ok, st.get('verdict'))
            if st.get('verdict') == 'HEC' and b:
                hec_bad += 1; print('HEC UNSOUND', n, m, h)
            if st.get('verdict') == 'MPC' and b:
                mpc_bad += 1; print('MPC UNSOUND', n, m, h)
    out = dict(trials=trials, feasible=feas, mismatches=mis, hec_unsound=hec_bad,
               mpc_unsound=mpc_bad)
    print(json.dumps(out))
    json.dump(out, open('exp/v42/res_test.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
