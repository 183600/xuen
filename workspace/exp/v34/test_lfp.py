"""v4.0 correctness: LFP vs brute force and vs WOS, both directions."""
import sys, json, random
sys.path[:0] = ['exp/v34', 'exp/v30', 'exp/v13']
import po, wos, lfp
from bench_wos import load


def brute(inst, h):
    n, p = inst['n'], inst['p']
    indeg = [0] * n
    for i in range(n):
        for j in inst['succ'][i]:
            indeg[j] += 1
    q = [i for i in range(n) if indeg[i] == 0]
    topo = []
    while q:
        u = q.pop(); topo.append(u)
        for v in inst['succ'][u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    st = [0] * n

    def rec(k):
        if k == n:
            cnt = [0] * h
            for i in range(n):
                for t in range(st[i], st[i] + p[i]):
                    cnt[t] += 1
            return max(cnt) <= inst['m']
        i = topo[k]
        lo = max([st[j] + p[j] for j in inst['pred'][i]] + [0])
        for t in range(lo, h - p[i] + 1):
            st[i] = t
            if rec(k + 1):
                return True
        return False
    return rec(0)


def main():
    rng = random.Random(4004)
    trials = feas = mis = 0
    for _ in range(140):
        n = rng.randint(3, 7); m = rng.randint(1, 4)
        p = [rng.randint(1, 4) for _ in range(n)]
        pred = [[] for _ in range(n)]
        for j in range(1, n):
            for i in range(j):
                if rng.random() < 0.22:
                    pred[j].append(i)
        inst = po.make_inst(p, m, pred)
        for h in range(3, 12):
            b = brute(inst, h)
            trials += 1; feas += 1 if b else 0
            v, _ = lfp.solve(inst, h, dir='forward')
            v2, _ = lfp.solve(inst, h, dir='backward')
            if bool(v) != b or bool(v2) != b:
                mis += 1
                print('MISMATCH', n, m, h, p, pred, b, v, v2)
    out = dict(brute=dict(trials=trials, feasible=feas, mismatch=mis), bench={})
    cases = load('exp/v20/holdout_cases50.pkl')
    bad = cnt = 0
    for hm in (-1, 0):
        for idx, (inst, opt) in enumerate(cases):
            h = opt + hm; n = inst['n']
            est, q = po.heads_tails(inst, 0, [0] * n)
            w, _ = wos.sgs_solve(inst, h, est=est, q=q, force=True, nodecap=300000)
            v, _ = lfp.solve(inst, h, dir='forward')
            v2, _ = lfp.solve(inst, h, dir='backward')
            cnt += 1
            if bool(v) != bool(w) or bool(v2) != bool(w):
                bad += 1
                print('VERDICT MISMATCH', hm, idx, w, v, v2)
    out['bench'] = dict(cases=cnt, mismatch=bad)
    print(json.dumps(out, indent=1))
    json.dump(out, open('exp/v34/res_test.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
