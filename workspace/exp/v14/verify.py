import sys, random, time
sys.path.insert(0, 'exp/v14')
import sp

def brute(inst, h, cap=2_000_000):
    n, m, p = inst['n'], inst['m'], inst['p']
    full = inst['full']
    cnt = [0]
    def rec(rem, A, est):
        cnt[0] += 1
        if cnt[0] > cap: raise TimeoutError
        if rem == 0: return True
        q = sp.tails(inst, rem)
        ready = [i for i in sp.bititer(rem) if not (inst['pmask'][i] & rem)]
        for i in ready:
            if est[i] + p[i] + q[i] > h: continue
            for k in inst['elig'][i]:
                t = max(A[k], est[i])
                if t + p[i] + q[i] > h: continue
                nA = list(A); nA[k] = t + p[i]
                nest = list(est)
                for j in inst['succ'][i]:
                    if (rem >> j) & 1 and t + p[i] > nest[j]: nest[j] = t + p[i]
                if rec(rem & ~(1 << i), tuple(nA), tuple(nest)): return True
        return False
    est0, _ = sp.heads_tails(inst, 0, [0] * n)
    return rec(full, (0,) * m, tuple(est0))

def rand_inst(rng, n, m):
    p = [rng.randint(1, 7) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random() < 0.22: pred[j].append(i)
    elig = []
    for i in range(n):
        e = [k for k in range(m) if rng.random() < 0.8]
        if not e: e = [rng.randrange(m)]
        elig.append(e)
    return sp.make_inst(p, m, pred, elig)

def verify_witness(inst, h, sched):
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = sp.heads_tails(inst, 0, [0] * n)
    A = [0] * m; done = [False] * n
    for (i, k, t) in sched:
        if k not in inst['elig'][i]: return 'elig'
        if t < max(A[k], est[i]): return 'machine/est'
        if t + p[i] + q[i] > h: return 'deadline'
        A[k] = t + p[i]; done[i] = True
        for j in inst['succ'][i]:
            if not done[j]: est[j] = max(est[j], t + p[i])
    return None if all(done) else 'missing'

if __name__ == '__main__':
    rng = random.Random(2024)
    configs = [
        ('plain', dict()),
        ('plain', dict(est_zero=True)),
        ('plain', dict(etail=True)),
        ('sub', dict()),
        ('sub', dict(est_zero=True)),
        ('sub', dict(etail=True)),
        ('sub', dict(est_zero=True, etail=True)),
    ]
    bad = 0; tot = 0; wit_bad = 0; t0 = time.time()
    for trial in range(320):
        n = rng.randint(4, 7); m = rng.choice([2, 3])
        inst = rand_inst(rng, n, m)
        est, q = sp.heads_tails(inst, 0, [0] * n)
        lb = max(max(est[i] + inst['p'][i] + q[i] for i in range(n)), max(inst['p']))
        h = rng.randint(lb, lb + 5)
        b = brute(inst, h)
        for mode, pol in configs:
            (ok, sched), st = sp.decide(inst, h, mode=mode, nodecap=500000,
                                        policy=pol)
            tot += 1
            if ok != b:
                bad += 1
                print('MISMATCH', mode, pol, n, m, h, ok, b, inst['p'], inst['pred'], inst['elig'])
                if bad > 5: sys.exit(1)
            if ok and sched is not None:
                e = verify_witness(inst, h, sched)
                if e:
                    wit_bad += 1; print('WIT', mode, pol, e)
    print('checks', tot, 'mismatch', bad, 'witness_bad', wit_bad,
          'time', round(time.time() - t0, 2))
