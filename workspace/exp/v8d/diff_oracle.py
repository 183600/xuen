"""Direct oracle differential test: HSC vs brute force at h=OPT and OPT-1."""
import sys
import random
import time

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

import po
from chip import base_bounds
from hsc import HSC
from diff_small import gen, brute


def main():
    rng = random.Random(77)
    bad = 0
    unk = 0
    ncase = 0
    t0 = time.time()
    for it in range(80):
        n = rng.randint(5, 9)
        m = rng.choice([2, 3])
        inst = gen(rng, n, m, ep=rng.choice([0.15, 0.3, 0.5]),
                   elig_p=rng.choice([1.0, 0.7, 0.5]))
        lb, ub, _, _, est, q = base_bounds(inst)
        opt = None
        for h in range(lb, lb + 12):
            if brute(inst, h):
                opt = h
                break
        if opt is None:
            continue
        for h in [opt, opt - 1]:
            want = (h >= opt)
            rdf = HSC(inst, h, yes_scan=True, cheap_disc=2, hull_disc=4,
                      hull_on=True, random_fallback=False)
            v, st = rdf.decide(budget=80, nodecap=5000)
            ncase += 1
            if v is None:
                unk += 1
                continue
            if bool(v) != want:
                bad += 1
                print('ORACLE MISMATCH', it, n, m, h, 'want', want,
                      'got', v, 'phase', st.get('phase'), flush=True)
                if bad > 3:
                    break
        if bad > 3:
            break
    print('oracle cases', ncase, 'mismatch', bad, 'unknown', unk,
          'time', round(time.time() - t0, 1))


if __name__ == '__main__':
    main()
