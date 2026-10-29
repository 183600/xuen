"""Generate a branching stress set for v7.2 UCP.

We mutate processing times of the 95 holdout+synth NO instances and keep
the mutations that are still NO at the *original* h = OPT-1 but require
branching under QNC (nodes > 1).  The label is sound either way: QNC's NO
comes with a Farkas certificate, and its YES comes from an integral LP.

No RNG is used by UCP itself; the seed here only fixes the offline corpus.
"""
import sys, pickle, random, json, time
sys.setrecursionlimit(20000)
sys.path[:0] = ['exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def main():
    bases = []
    for f in ('exp/v20/holdout_cases50.pkl', 'exp/v28/synth2_45.pkl'):
        for idx, (inst, opt) in enumerate(load(f)):
            bases.append((f.split('/')[-1][:-4], idx, inst, opt))
    rng = random.Random(0)
    kept, seen = [], set()
    t0 = time.time()
    for trial in range(700):
        name, idx, inst, opt = bases[rng.randrange(len(bases))]
        job = rng.randrange(inst['n'])
        delta = rng.choice([-2, -1, 1, 2])
        p = list(inst['p'])
        if p[job] + delta < 1:
            continue
        p[job] += delta
        key = (name, idx, job, p[job])
        if key in seen:
            continue
        seen.add(key)
        inst2 = dict(inst)
        inst2['p'] = p
        h = opt - 1
        q = QNC(inst2, h)
        try:
            v, st = q.decide(nodecap=400)
        except (RecursionError, MemoryError):
            continue
        if v is False and st['nodes'] > 1:
            kept.append(dict(src=name, idx=idx, job=job, p_new=p[job],
                             h=h, lp=st['lp_solves'], nodes=st['nodes'],
                             n=inst['n'], m=inst['m'], inst=inst2,
                             audit=q.audit()))
    pickle.dump(kept, open('exp/v72/stress.pkl', 'wb'))
    meta = [{k: v for k, v in r.items() if k != 'inst'} for r in kept]
    json.dump(meta, open('exp/v72/stress_meta.json', 'w'), indent=1)
    print('candidates', len(seen), 'kept', len(kept),
          'time', round(time.time() - t0, 2))
    from collections import Counter
    print(Counter((r['src'], r['idx']) for r in kept).most_common(20))


if __name__ == '__main__':
    main()
