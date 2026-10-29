"""v2.4 correctness: brute force, YES schedules, ICC witnesses."""
import sys, json, pickle, random, time
sys.path[:0] = ['exp/v13', 'exp/v15', 'exp/v16', 'exp/v20', 'exp/v24',
                'exp/v25', 'exp/v28']
import po, icc, root_pc, sgs


def brute(inst, h):
    n, m, p = inst['n'], inst['m'], inst['p']
    pred, succ = inst['pred'], inst['succ']
    indeg = [0] * n
    for i in range(n):
        for j in succ[i]:
            indeg[j] += 1
    q = [i for i in range(n) if indeg[i] == 0]
    topo = []
    while q:
        u = q.pop()
        topo.append(u)
        for v in succ[u]:
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
            return max(cnt) <= m
        i = topo[k]
        lo = max([st[j] + p[j] for j in pred[i]] + [0])
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
    # 1. 400 random small instances vs brute
    rng = random.Random(2027)
    mis_icc = mis_pipe = 0
    feas = icc_hits = ncase = 0
    for _ in range(400):
        n = rng.randint(3, 7)
        m = rng.randint(1, 3)
        h = rng.randint(4, 10)
        p = [rng.randint(1, 4) for _ in range(n)]
        pred = [[] for _ in range(n)]
        for j in range(1, n):
            for i in range(j):
                if rng.random() < 0.22:
                    pred[j].append(i)
        inst = po.make_inst(p, m, pred)
        est, q = po.heads_tails(inst, 0, [0] * n)
        b = brute(inst, h)
        ok, w = icc.icc(inst, inst['full'], tuple([0] * m), est, q, h)
        if not ok:
            icc_hits += 1
            if b or not icc.check(inst, inst['full'], tuple([0] * m), est, q, h, w):
                mis_icc += 1
                break
        v, st = root_pc.pc_solve(inst, h)
        if v is None or bool(v) != bool(b):
            mis_pipe += 1
            print('PIPE MISMATCH', n, m, h, p, pred, b, v, st)
            break
        ncase += 1
        feas += 1 if b else 0
    out['brute'] = dict(n=ncase, feasible=feas, icc_hits=icc_hits,
                        mis_icc=mis_icc, mis_pipe=mis_pipe)
    print('brute', out['brute'], flush=True)

    # 2. YES schedules at h=OPT, independent validation
    okc = bad = 0
    nodes = 0
    for f in ['exp/v13/hard3.pkl', 'exp/v18/deep.pkl', 'exp/v20/holdout_cases50.pkl']:
        for inst, opt in load(f):
            n = inst['n']
            est, q = po.heads_tails(inst, 0, [0] * n)
            st = {}
            v, sch = sgs.sgs_solve(inst, opt, est=est, q=q, nodecap=200000, stats=st)
            nodes += st.get('nodes', 0)
            if v is True and sgs.validate(inst, opt, sch)[0]:
                okc += 1
            else:
                bad += 1
    out['yes70'] = dict(valid=okc, bad=bad, nodes=nodes)
    print('yes70', out['yes70'], flush=True)

    # 3. ICC witnesses on hard3 + synth45
    checked = badw = 0
    for f in ['exp/v13/hard3.pkl']:
        for inst, opt in load(f):
            n = inst['n']
            est, q = po.heads_tails(inst, 0, [0] * n)
            ok, w = icc.icc(inst, inst['full'], tuple([0] * inst['m']), est, q, opt - 1)
            if not ok:
                checked += 1
                if not icc.check(inst, inst['full'], tuple([0] * inst['m']),
                                 est, q, opt - 1, w):
                    badw += 1
    syn = pickle.load(open('exp/v28/synth2_45.pkl', 'rb'))
    for inst, opt, seed in syn:
        n = inst['n']
        est, q = po.heads_tails(inst, 0, [0] * n)
        ok, w = icc.icc(inst, inst['full'], tuple([0] * inst['m']), est, q, opt - 1)
        if not ok:
            checked += 1
            if not icc.check(inst, inst['full'], tuple([0] * inst['m']),
                             est, q, opt - 1, w):
                badw += 1
    out['icc_witness'] = dict(checked=checked, bad=badw)
    print('icc_witness', out['icc_witness'], flush=True)

    json.dump(out, open('exp/v28/res_pc_valid.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
