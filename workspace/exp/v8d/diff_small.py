"""Differential test: HSCPool vs exhaustive search on random n<=9 instances."""
import sys
import random
import time

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

import po
from chip import base_bounds
from hsc_pool import HSCPool


def gen(rng, n, m, pmax=8, ep=0.3, elig_p=1.0):
    p = [rng.randint(1, pmax) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random() < ep:
                pred[j].append(i)
        if j > 0 and not pred[j] and rng.random() < 0.7:
            pred[j].append(rng.randrange(j))
    if elig_p >= 1.0:
        elig = [list(range(m)) for _ in range(n)]
    else:
        elig = []
        for i in range(n):
            e = [k for k in range(m) if rng.random() < elig_p]
            if not e:
                e = [rng.randrange(m)]
            elig.append(e)
    return po.make_inst(p, m, pred, elig)


def brute(inst, h, cap=400000):
    n, m, p = inst['n'], inst['m'], inst['p']
    full = inst['full']
    seen = [0]

    def rec(rem, A, est):
        seen[0] += 1
        if seen[0] > cap:
            raise TimeoutError
        if rem == 0:
            return True
        q = po.tails(inst, rem)
        ready = [i for i in po.bititer(rem)
                 if not (inst['pmask'][i] & rem)]
        for i in ready:
            if est[i] + p[i] + q[i] > h:
                continue
            for k in inst['elig'][i]:
                t = max(A[k], est[i])
                if t + p[i] + q[i] > h:
                    continue
                nA = list(A)
                nA[k] = t + p[i]
                nest = list(est)
                for j in inst['succ'][i]:
                    if (rem >> j) & 1 and t + p[i] > nest[j]:
                        nest[j] = t + p[i]
                if rec(rem & ~(1 << i), tuple(nA), tuple(nest)):
                    return True
        return False

    est0, _ = po.heads_tails(inst, 0, [0] * n)
    return rec(full, (0,) * m, tuple(est0))


def main():
    rng = random.Random(20261024)
    bad = 0
    ncase = 0
    t0 = time.time()
    for it in range(60):
        n = rng.randint(5, 9)
        m = rng.choice([2, 3])
        ep = rng.choice([0.15, 0.3, 0.5])
        elig_p = rng.choice([1.0, 0.7, 0.5])
        inst = gen(rng, n, m, ep=ep, elig_p=elig_p)
        lb, ub, _, _, est, q = base_bounds(inst)
        opt = None
        for h in range(lb, lb + 12):
            if brute(inst, h):
                opt = h
                break
        if opt is None:
            print('no opt in window', it, n, m, lb)
            continue
        co = HSCPool(inst)
        r = co.optimize()
        ok = (r['certified'] and r['opt'] == opt and r['audit']
              and r['proof'] and r['cert_h'] == opt - 1)
        ncase += 1
        if not ok:
            bad += 1
            print('MISMATCH it', it, 'n', n, 'm', m, 'ep', ep,
                  'elig', elig_p, 'opt', opt, 'got', r['opt'],
                  'cert', r['certified'], 'audit', r['audit'],
                  'proof', r['proof'], 'cert_h', r['cert_h'],
                  flush=True)
            if bad > 3:
                break
    print('cases', ncase, 'mismatch', bad,
          'time', round(time.time() - t0, 1))


if __name__ == '__main__':
    main()
