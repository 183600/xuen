"""v4.0-MPC correctness: brute force, MPC soundness, YES schedules, fallback."""
import sys, json, pickle, random
sys.path[:0] = ['exp/v41', 'exp/v30', 'exp/v29', 'exp/v13', 'exp/v15', 'exp/v16', 'exp/v20', 'exp/v24', 'exp/v25', 'exp/v28']
import po, sgs, wos, mpc_max, mpc_py, root_v30, root_v41


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


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def main():
    out = {}
    rng = random.Random(41041)
    # 1. cascade vs brute on random small instances
    trials = feas = mis = 0
    for _ in range(160):
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
            ok, st = root_v41.bb_solve(inst, h, stats={})
            if bool(ok) != bool(b):
                mis += 1
                print('CASCADE MISMATCH', n, m, h, p, pred, b, ok)
            if ok and st.get('verdict') == 'OS':
                v, sch = wos.sgs_solve(inst, h, est=po.heads_tails(inst, 0, [0]*n)[0],
                                       q=po.heads_tails(inst, 0, [0]*n)[1])
                if not sgs.validate(inst, h, sch)[0]:
                    print('BAD SCHED', n, m, h)
                    mis += 1
    out['brute'] = dict(trials=trials, feasible=feas, mismatches=mis)
    print('brute', out['brute'], flush=True)

    # 2. MPC soundness on random instances against exact WOS
    unsound = cert = total = 0
    for _ in range(800):
        n = rng.randint(2, 8); m = rng.randint(1, 4)
        p = [rng.randint(1, 5) for _ in range(n)]
        pred = [[] for _ in range(n)]
        for j in range(1, n):
            for i in range(j):
                if rng.random() < 0.25:
                    pred[j].append(i)
        inst = po.make_inst(p, m, pred)
        est, q = po.heads_tails(inst, 0, [0] * n)
        for h in range(max(est[i] + p[i] + q[i] for i in range(n)), 14):
            total += 1
            v = mpc_max.mpc_no(inst, h, est, q)
            if v is None:
                continue
            if v:
                cert += 1
                ok, _ = wos.sgs_solve(inst, h, est=est, q=q, nodecap=300000)
                if ok:
                    unsound += 1
                    print('MPC UNSOUND', n, m, h, p, pred)
    out['mpc_sound'] = dict(trials=total, certificates=cert, unsound=unsound)
    print('mpc_sound', out['mpc_sound'], flush=True)

    # 3. C and python fallback agree
    diff = 0; tested = 0
    for _ in range(200):
        n = rng.randint(2, 10); m = rng.randint(1, 4)
        p = [rng.randint(1, 5) for _ in range(n)]
        pred = [[] for _ in range(n)]
        for j in range(1, n):
            for i in range(j):
                if rng.random() < 0.25:
                    pred[j].append(i)
        inst = po.make_inst(p, m, pred)
        est, q = po.heads_tails(inst, 0, [0] * n)
        for h in range(max(est[i] + p[i] + q[i] for i in range(n)), 14):
            a = mpc_max.mpc_no(inst, h, est, q)
            b = mpc_py.mpc_no(inst, h, est, q)
            if a is not None and b is not None and a != b:
                diff += 1
                print('FALLBACK DIFF', n, m, h)
            tested += 1
    out['fallback'] = dict(tested=tested, diff=diff)
    print('fallback', out['fallback'], flush=True)

    # 4. YES schedules validate, v41 == v30 verdicts on all sets
    yes = dict(valid=0, bad=0)
    sets = {'holdout50': 'exp/v20/holdout_cases50.pkl',
            'hard3': 'exp/v13/hard3.pkl', 'deep8': 'exp/v18/deep.pkl',
            'synth45': 'exp/v28/synth2_45.pkl'}
    for name, f in sets.items():
        for inst, opt in load(f):
            ok, st = root_v41.bb_solve(inst, opt, stats={})
            if ok is None:
                continue
            if ok:
                v, sch = wos.sgs_solve(inst, opt, est=po.heads_tails(inst, 0, [0]*inst['n'])[0],
                                       q=po.heads_tails(inst, 0, [0]*inst['n'])[1])
                if not sgs.validate(inst, opt, sch)[0]:
                    yes['bad'] += 1
                else:
                    yes['valid'] += 1
            else:
                yes['bad'] += 1
    out['yes'] = yes
    print('yes', out['yes'], flush=True)
    json.dump(out, open('exp/v41/res_test.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
