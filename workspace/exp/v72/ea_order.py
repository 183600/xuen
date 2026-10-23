"""Offline evolutionary search for a unit-probe ordering policy.

The proof rule is exact; only the number of probes depends on the order in
which support literals are tested.  We cache forced/free labels for the
seven root-fractional cases and evolve a linear scoring policy.  The
result is a design aid, not part of the online proof.
"""
import sys, pickle, json, random, time
sys.path[:0] = ['exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
from lazy import LazySD
from qnc import farkas_int
from cert import verify
from quc import _support_mass, _del_bounds

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl',
 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl',
 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl',
 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl'}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def root_case(inst, h):
    lp = LazySD(inst, h, elig_aware=any(len(set(inst['elig'][i])) < inst['m']
                                        for i in range(inst['n'])))
    for rnd in range(60):
        res = lp.solve([(0, 1)] * lp.base.N)
        if res.status != 0:
            return None
        viol = lp.separate(res.x, topk=100)
        if not viol:
            break
        for _, i, j, t in viol:
            if (i, j, t) not in lp.cutset:
                lp.cutset.add((i, j, t))
                lp.cuts.append((i, j, t))
    S = _support_mass(lp, res.x)
    dom = {}
    for key in lp.cols:
        dom.setdefault(key[0], set()).add(key[-1])
    labels = {}
    for i in S:
        for t in S[i]:
            r = lp.solve(_del_bounds(lp, i, t))
            ok = False
            if r.status == 2:
                c, _ = farkas_int(lp, {(i, t)})
                ok = c is not None and verify(inst, h, c, forbid={(i, t)},
                                              elig_aware=lp.elig_aware)
            labels[(i, t)] = ok
    return dict(inst=inst, S=S, dom={i: (min(v), max(v)) for i, v in dom.items()},
                labels=labels)


def features(case):
    inst = case['inst']
    S = case['S']
    out = {}
    for i in S:
        lo, hi = case['dom'][i]
        ts = sorted(S[i])
        ms = [S[i][t] for t in ts]
        jf = [1.0 if (ts[0] == lo and ts[-1] == hi) else 0.0,
              float(len(ts)),
              float(max(ms)),
              float(min(ms)),
              float(hi - lo),
              i / max(1, inst['n'] - 1),
              float(len(inst['succ'][i])),
              float(len(inst['pred'][i]))]
        tf = {}
        for t in ts:
            tf[t] = [float(S[i][t]),
                     1.0 if t == ts[0] else 0.0,
                     1.0 if t == ts[-1] else 0.0,
                     abs(t - (ts[0] + ts[-1]) / 2.0) / max(1.0, hi - lo),
                     t / max(1.0, inst['h'] if 'h' in inst else 100.0)]
        out[i] = (jf, tf, ts)
    return out


def simulate(case, feats, w, budget=6):
    inst = case['inst']
    S = case['S']
    labels = case['labels']
    jobs = list(feats)
    wj = np.array(w[:8]); wt = np.array(w[8:])
    jobs.sort(key=lambda i: -float(np.dot(wj, feats[i][0])))
    probes = 0
    forced = {}
    for i in jobs:
        if probes >= budget:
            return budget + 5
        jf, tf, ts = feats[i]
        times = sorted(ts, key=lambda t: -float(np.dot(wt, tf[t])))
        for t in times:
            if probes >= budget:
                return budget + 5
            probes += 1
            if not labels[(i, t)]:
                continue
            if i in forced and forced[i] != t:
                return probes
            forced[i] = t
    return budget + 5


def score(policy, cases, feats):
    return sum(simulate(c, f, policy) for c, f in zip(cases, feats))


def main():
    cases = []
    for nm, idx in [('holdout50', 5), ('holdout50', 47)]:
        inst, opt = load(FILES[nm])[idx]
        cases.append(root_case(inst, opt - 1))
    pert = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    for (nm, k, inst, opt, an, al) in pert:
        if an > 1:
            cases.append(root_case(inst, opt - 1))
    feats = [features(c) for c in cases]
    for c in cases:
        c['inst']['h'] = 0
    # rebuild features with h
    for c in cases:
        c['inst']['h'] = c['inst'].get('h', 0)
    # hand policy: span, then support size, then mass; endpoints first
    hand = [10.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            1.0, 10.0, 10.0, -1.0, 0.0]
    print('hand', score(hand, cases, feats),
          [simulate(c, f, hand) for c, f in zip(cases, feats)])
    random.seed(0)
    np.random.seed(0)
    pop = [np.random.randn(13) for _ in range(30)]
    pop[0] = np.array(hand, dtype=float)
    best = None
    for gen in range(40):
        ranked = sorted(pop, key=lambda p: score(p, cases, feats))
        if best is None or score(ranked[0], cases, feats) < best[0]:
            best = (score(ranked[0], cases, feats), ranked[0].copy())
        elite = ranked[:4]
        new = [p.copy() for p in elite]
        while len(new) < 30:
            a = min(random.sample(ranked[:12], 2), key=lambda p: score(p, cases, feats))
            b = min(random.sample(ranked[:12], 2), key=lambda p: score(p, cases, feats))
            child = np.where(np.random.rand(13) < 0.5, a, b)
            child = child + np.random.randn(13) * 0.4
            new.append(child)
        pop = new
    ranked = sorted(pop, key=lambda p: score(p, cases, feats))
    best = (score(ranked[0], cases, feats), ranked[0])
    print('best', best[0], [simulate(c, f, best[1]) for c, f in zip(cases, feats)])
    print('weights', [round(float(x), 3) for x in best[1]])
    json.dump(dict(hand=score(hand, cases, feats),
                   best=best[0],
                   weights=[float(x) for x in best[1]],
                   per_case=[simulate(c, f, best[1]) for c, f in zip(cases, feats)]),
              open('exp/v72/ea_order.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
