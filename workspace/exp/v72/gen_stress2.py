"""Second stress generator: recompute OPT after a p-mutation, then keep
instances whose h=OPT-1 needs branching under QNC.

Only used to build an offline evaluation set; UCP itself is deterministic.
"""
import sys, pickle, random, json, time
sys.setrecursionlimit(20000)
sys.path[:0] = ['exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC
from po import heads_tails


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def opt_of(inst, lo, hi):
    for h in range(lo, hi + 1):
        q = QNC(inst, h)
        try:
            v, st = q.decide(nodecap=300, budget=4000)
        except (RecursionError, MemoryError):
            return None
        if v is True:
            return h, q
    return None


def main():
    bases = []
    for f in ('exp/v20/holdout_cases50.pkl', 'exp/v28/synth2_45.pkl'):
        for idx, (inst, opt) in enumerate(load(f)):
            bases.append((f.split('/')[-1][:-4], idx, inst, opt))
    rng = random.Random(1)
    kept, trials, t0 = [], 0, time.time()
    for trial in range(260):
        name, idx, inst, opt = bases[rng.randrange(len(bases))]
        job = rng.randrange(inst['n'])
        delta = rng.choice([-2, -1, 1, 2])
        p = list(inst['p'])
        if p[job] + delta < 1:
            continue
        p[job] += delta
        inst2 = dict(inst)
        inst2['p'] = p
        est, qq = heads_tails(inst2, 0, [0] * inst2['n'])
        lb = max(est[i] + p[i] + qq[i] for i in range(inst2['n']))
        got = opt_of(inst2, lb, opt + 2)
        trials += 1
        if got is None:
            continue
        newopt, qyes = got
        if newopt <= lb:
            continue
        q = QNC(inst2, newopt - 1)
        try:
            v, st = q.decide(nodecap=500, budget=6000)
        except (RecursionError, MemoryError):
            continue
        if v is False and st['nodes'] > 1 and q.audit():
            kept.append(dict(src=name, idx=idx, job=job, p_new=p[job],
                             opt=newopt, h=newopt - 1,
                             lp=st['lp_solves'], nodes=st['nodes'],
                             n=inst2['n'], m=inst2['m'], inst=inst2))
        if trials % 20 == 0:
            print('trials', trials, 'kept', len(kept),
                  'time', round(time.time() - t0, 1), flush=True)
    pickle.dump(kept, open('exp/v72/stress2.pkl', 'wb'))
    meta = [{k: v for k, v in r.items() if k != 'inst'} for r in kept]
    json.dump(meta, open('exp/v72/stress2_meta.json', 'w'), indent=1)
    print('DONE trials', trials, 'kept', len(kept),
          'time', round(time.time() - t0, 2))


if __name__ == '__main__':
    main()
