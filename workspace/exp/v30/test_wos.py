"""v3.0 correctness: brute force, differential vs v2.5, YES schedules."""
import sys, json, pickle, random
sys.path[:0] = ['exp/v30', 'exp/v29', 'exp/v13', 'exp/v15', 'exp/v16',
                'exp/v20', 'exp/v24', 'exp/v25', 'exp/v28']
import po, sgs, wos, wos_no, os_pack


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
    rng = random.Random(30301)
    mis = {'force': 0, 'noforce': 0, 'diff': 0}
    trials = feas = 0
    for _ in range(140):
        n = rng.randint(3, 7); m = rng.randint(1, 4)
        p = [rng.randint(1, 4) for _ in range(n)]
        pred = [[] for _ in range(n)]
        for j in range(1, n):
            for i in range(j):
                if rng.random() < 0.22:
                    pred[j].append(i)
        inst = po.make_inst(p, m, pred)
        est, q = po.heads_tails(inst, 0, [0] * n)
        for h in range(3, 12):
            b = brute(inst, h)
            trials += 1; feas += 1 if b else 0
            v, sch = wos.sgs_solve(inst, h, A=(0,) * m, est=est, q=q,
                                   nodecap=300000)
            v2, _ = wos_no.sgs_solve(inst, h, A=(0,) * m, est=est, q=q,
                                     nodecap=300000)
            if bool(v) != bool(b):
                mis['force'] += 1
                print('FORCE MISMATCH', n, m, h, p, pred, b, v)
            if bool(v2) != bool(b):
                mis['noforce'] += 1
                print('NOFORCE MISMATCH', n, m, h, p, pred, b, v2)
            if v and not sgs.validate(inst, h, sch)[0]:
                print('BAD SCHEDULE', n, m, h, p, pred, sch)
                mis['force'] += 1
    out['brute'] = dict(trials=trials, feasible=feas, **mis)
    print('brute', out['brute'], flush=True)

    # differential vs v2.5 on random *states* (A != 0, subset rem)
    same = diff = 0
    for _ in range(400):
        n = rng.randint(3, 8); m = rng.randint(1, 4)
        p = [rng.randint(1, 5) for _ in range(n)]
        pred = [[] for _ in range(n)]
        for j in range(1, n):
            for i in range(j):
                if rng.random() < 0.2:
                    pred[j].append(i)
        inst = po.make_inst(p, m, pred)
        h = rng.randint(4, 14)
        est, q = po.heads_tails(inst, 0, [0] * n)
        A = tuple(rng.randint(0, 2) for _ in range(m))
        rem = inst['full']
        for i in range(n):
            if rng.random() < 0.3 and not (inst['pred'][i]):
                rem &= ~(1 << i)
        s1 = {}; s2 = {}
        v1, _ = wos.sgs_solve(inst, h, rem=rem, A=A, est=est, q=q,
                              nodecap=300000, stats=s1)
        v2, _ = os_pack.sgs_solve(inst, h, rem=rem, A=A, est=est, q=q,
                                  nodecap=300000, stats=s2, rsi=True)
        same += 1
        if bool(v1) != bool(v2):
            diff += 1
            print('STATE DIFF', n, m, h, A, rem, v1, v2)
    out['states'] = dict(same=same, diff=diff)
    print('states', out['states'], flush=True)

    # YES side: schedules from the new kernel must validate
    okc = bad = nodes = 0
    for f in ['exp/v13/hard3.pkl', 'exp/v18/deep.pkl',
              'exp/v20/holdout_cases50.pkl']:
        for inst, opt in load(f):
            est, q = po.heads_tails(inst, 0, [0] * inst['n'])
            st = {}
            v, sch = wos.sgs_solve(inst, opt, A=(0,) * inst['m'], est=est,
                                   q=q, nodecap=300000, stats=st)
            nodes += st['nodes']
            if v is True and sgs.validate(inst, opt, sch)[0]:
                okc += 1
            else:
                bad += 1
                print('YES BAD', inst['n'], inst['m'], v)
    out['yes70'] = dict(valid=okc, bad=bad, nodes=nodes)
    print('yes70', out['yes70'], flush=True)

    syn = pickle.load(open('exp/v28/synth2_45.pkl', 'rb'))
    okc = bad = m4 = m4ok = 0
    for inst, opt, seed in syn:
        est, q = po.heads_tails(inst, 0, [0] * inst['n'])
        v, sch = wos.sgs_solve(inst, opt, A=(0,) * inst['m'], est=est, q=q,
                               nodecap=200000)
        good = v is True and sgs.validate(inst, opt, sch)[0]
        okc += good; bad += (not good)
        if inst['m'] == 4:
            m4 += 1; m4ok += good
    out['synth_yes'] = dict(valid=okc, bad=bad, m4=m4, m4_valid=m4ok)
    print('synth_yes', out['synth_yes'], flush=True)
    json.dump(out, open('exp/v30/res_test.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
