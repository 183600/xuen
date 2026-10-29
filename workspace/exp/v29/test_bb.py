"""v2.5 correctness: brute force, differential, YES schedules, ICC witnesses."""
import sys, json, pickle, random, time
sys.path[:0] = ['exp/v29', 'exp/v13', 'exp/v15', 'exp/v16', 'exp/v20',
                'exp/v24', 'exp/v25', 'exp/v28']
import po, icc, os_pack, os_bit, sgs, root_bb


def brute(inst, h):
    n, p = inst['n'], inst['p']
    pred, succ = inst['pred'], inst['succ']
    indeg = [0] * n
    for i in range(n):
        for j in succ[i]:
            indeg[j] += 1
    q = [i for i in range(n) if indeg[i] == 0]
    topo = []
    while q:
        u = q.pop(); topo.append(u)
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
            return max(cnt) <= inst['m']
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
    rng = random.Random(2029)
    # 1. differential vs brute, several horizons per instance
    mis_pack = mis_bit = mis_rsi = trials = feas = 0
    for _ in range(120):
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
            s = {}
            v, _ = os_pack.sgs_solve(inst, h, rem=inst['full'], A=(0,) * m,
                                     est=est, q=q, nodecap=300000, stats=s)
            s2 = {}
            v2, _ = os_pack.sgs_solve(inst, h, rem=inst['full'], A=(0,) * m,
                                      est=est, q=q, nodecap=300000, rsi=False, stats=s2)
            s3 = {}
            v3, _ = os_bit.sgs_solve(inst, h, rem=inst['full'], A=(0,) * m,
                                     est=est, q=q, nodecap=300000, rsi=True, bit=True, stats=s3)
            trials += 1; feas += 1 if b else 0
            if v is not None and bool(v) != bool(b):
                mis_pack += 1; print('PACK MISMATCH', n, m, h, p, pred, b, v)
            if v2 is not None and bool(v2) != bool(b):
                mis_rsi += 1; print('RSI MISMATCH', n, m, h, p, pred, b, v2)
            if v3 is not None and bool(v3) != bool(b):
                mis_bit += 1; print('BIT MISMATCH', n, m, h, p, pred, b, v3)
    out['brute'] = dict(trials=trials, feasible=feas, mis_pack=mis_pack,
                        mis_bit=mis_bit, mis_rsi=mis_rsi)
    print('brute', out['brute'], flush=True)

    # 2. feasible side: h=OPT, validate schedules from the new kernel
    okc = bad = 0; nodes = 0
    for f in ['exp/v13/hard3.pkl', 'exp/v18/deep.pkl', 'exp/v20/holdout_cases50.pkl']:
        for inst, opt in load(f):
            n = inst['n']
            est, q = po.heads_tails(inst, 0, [0] * n)
            st = {}
            v, sch = os_pack.sgs_solve(inst, opt, rem=inst['full'],
                                       A=(0,) * inst['m'], est=est, q=q,
                                       nodecap=300000, stats=st)
            nodes += st['nodes']
            if v is True and sgs.validate(inst, opt, sch)[0]:
                okc += 1
            else:
                bad += 1
    out['yes70'] = dict(valid=okc, bad=bad, nodes=nodes)
    print('yes70', out['yes70'], flush=True)

    # 2b. feasible synth45 (includes 8 m=4 instances)
    syn0 = pickle.load(open('exp/v28/synth2_45.pkl', 'rb'))
    okc2 = bad2 = m4 = m4ok = 0
    for inst, opt, seed in syn0:
        est, q = po.heads_tails(inst, 0, [0] * inst['n'])
        v, sch = os_pack.sgs_solve(inst, opt, rem=inst['full'],
                                   A=(0,) * inst['m'], est=est, q=q,
                                   nodecap=200000)
        good = v is True and sgs.validate(inst, opt, sch)[0]
        okc2 += good; bad2 += (not good)
        if inst['m'] == 4:
            m4 += 1; m4ok += good
    out['synth_yes'] = dict(valid=okc2, bad=bad2, m4=m4, m4_valid=m4ok)
    print('synth_yes', out['synth_yes'], flush=True)

    # 3. ICC witnesses (hard3 + synth45)
    checked = badw = 0
    syn = pickle.load(open('exp/v28/synth2_45.pkl', 'rb'))
    for f in ['exp/v13/hard3.pkl']:
        for inst, opt in load(f):
            est, q = po.heads_tails(inst, 0, [0] * inst['n'])
            ok, w = icc.icc(inst, inst['full'], (0,) * inst['m'], est, q, opt - 1)
            if not ok:
                checked += 1
                if not icc.check(inst, inst['full'], (0,) * inst['m'],
                                 est, q, opt - 1, w):
                    badw += 1
    for x in syn:
        inst, opt = x[0], x[1]
        est, q = po.heads_tails(inst, 0, [0] * inst['n'])
        ok, w = icc.icc(inst, inst['full'], (0,) * inst['m'], est, q, opt - 1)
        if not ok:
            checked += 1
            if not icc.check(inst, inst['full'], (0,) * inst['m'],
                             est, q, opt - 1, w):
                badw += 1
    out['icc_witness'] = dict(checked=checked, bad=badw)
    print('icc_witness', out['icc_witness'], flush=True)

    # 4. v2.5 vs v2.4 verdicts on all stored rows
    d24 = json.load(open('exp/v28/res_pc.json'))
    d25 = json.load(open('exp/v29/res_bb.json'))
    diff = same = 0
    for name in ['holdout50', 'hard3', 'deep8', 'large_a', 'large_b',
                 'large_het', 'synth45', 'residual5']:
        for r24, r25 in zip(d24['rows'][name], d25['rows'][name]):
            same += 1
            if bool(r24['ok']) != bool(r25['ok']):
                diff += 1
                print('VERDICT DIFF', name, r24['idx'], r24['ok'], r25['ok'])
    out['vs_v24'] = dict(same=same, diff=diff)
    print('vs_v24', out['vs_v24'], flush=True)

    json.dump(out, open('exp/v29/res_bb_valid.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
