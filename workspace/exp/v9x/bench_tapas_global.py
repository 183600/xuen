"""TAPAS-G: one global branching policy learned on 8 hard YES probes.

The 24 hard YES probes from bench_tapas_local are split 8/16.  A single
weight vector is annealed on the first 8 (with a tabu list on rounded
weights) and then frozen; it is applied unchanged to the held-out 16 and
to all 252 YES/NO probes.  This tests whether policy annealing transfers
without per-instance tuning.
"""
import sys
import json
import time
import random
import math

sys.path[:0] = ['exp/v9x', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from pact import pact_decide
from sdecc import SDLP
from po import heads_tails
from sage import _elig_aware
from tapas import proof_rank, _audit_ok, FEATURES


def corpus_rows():
    rid = 0
    rows = []
    for tag, rr in (('base', base_corpus()), ('pert', pert_corpus()),
                    ('stress', stress_corpus())):
        for row in rr:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            rows.append(dict(rid=rid, tag=tag, name=name, idx=idx,
                             inst=inst, known=known))
            rid += 1
    return rows


def prep(inst, h):
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    res = lp.solve([(0, 1)] * lp.N)
    return lp, res


def main():
    t0 = time.time()
    rows = {z['rid']: z for z in corpus_rows()}
    local = json.load(open('exp/v9x/bench_tapas_local.json'))
    hard = [r for r in local if r['label'] == 'YES']
    train = hard[:8]
    held = hard[8:]
    cache = {}
    for z in train:
        cache[z['rid']] = prep(rows[z['rid']]['inst'], z['h'])
    capmap = {z['rid']: max(16, 2 * z['base_nodes']) for z in train}

    def run(z, w, s, cap):
        lp, res = cache[z['rid']]
        return pact_decide(rows[z['rid']]['inst'], z['h'],
                           depthcap=None, nodecap=cap,
                           policy={'weights': w, 'split': s},
                           root_lp=lp, root_res=res)

    def score(w, s):
        tot = 0.0
        for z in train:
            r = run(z, w, s, capmap[z['rid']])
            k = proof_rank(r)
            if r['verdict'] is None or k is None:
                return 10 ** 12
            tot += r['nodes'] + 2.0 * k
        return tot

    rng = random.Random(5)
    best = None
    portfolio = []
    for it in range(12):
        w = {f: rng.uniform(-1.0, 1.0) for f in FEATURES}
        s = rng.choice([0.3, 0.5, 0.7])
        sc = score(w, s)
        portfolio.append(dict(E=sc, policy={'weights': w, 'split': s}))
        if best is None or sc < best[0]:
            best = (sc, w, s)
    w, s = best[1], best[2]
    cur, bestE = best[0], best[0]
    bestw, bests = dict(w), s
    tabu = []
    T = 2.0
    trace = []
    for it in range(20):
        nw = dict(w)
        for f in FEATURES:
            if rng.random() < 0.40:
                nw[f] += rng.gauss(0.0, 0.9)
        ns = min(0.8, max(0.2, s + rng.gauss(0.0, 0.08)))
        sc = score(nw, ns)
        key = tuple(round(nw[f], 1) for f in FEATURES)
        if key in tabu and sc >= bestE:
            T *= 0.85
            continue
        if sc <= cur or rng.random() < math.exp(-(sc - cur) / max(T, 1e-9)):
            w, s, cur = nw, ns, sc
            tabu.append(key)
            tabu = tabu[-7:]
        if sc < bestE:
            bestE, bestw, bests = sc, dict(nw), ns
            trace.append(dict(it=it, E=sc))
        T *= 0.85
    policy = {'weights': bestw, 'split': bests}

    def eval_rows(zs, label):
        recs = []
        for z in zs:
            inst = rows[z['rid']]['inst']
            h = z['h']
            r = pact_decide(inst, h, depthcap=None, nodecap=None,
                            policy=policy)
            k = proof_rank(r)
            recs.append(dict(rid=z['rid'], corpus=z['corpus'],
                             name=z['name'], idx=z['idx'],
                             label=label, h=h,
                             base_nodes=z['base_nodes'],
                             base_rank=z['base_rank'],
                             nodes=r['nodes'], rank=k,
                             verdict=r['verdict'],
                             audit_ok=_audit_ok(inst, h, r),
                             t=r['t']))
        return recs

    test_train = eval_rows(train, 'train')
    test_held = eval_rows(held, 'held')
    # all 252 YES and NO (fresh baseline keys)
    all_yes, all_no = [], []
    for z in rows.values():
        inst, known = z['inst'], z['known']
        for label, h in (('YES', known), ('NO', known - 1)):
            r = pact_decide(inst, h, depthcap=None, nodecap=None)
            b = dict(nodes=r['nodes'], rank=proof_rank(r))
            r2 = pact_decide(inst, h, depthcap=None, nodecap=None,
                             policy=policy)
            k2 = proof_rank(r2)
            rec = dict(rid=z['rid'], corpus=z.get('corpus', z.get('tag')), name=z['name'],
                       idx=z['idx'], label=label, h=h,
                       base_nodes=b['nodes'], base_rank=b['rank'],
                       nodes=r2['nodes'], rank=k2,
                       verdict=r2['verdict'],
                       audit_ok=_audit_ok(inst, h, r2), t=r2['t'])
            (all_yes if label == 'YES' else all_no).append(rec)

    out = dict(policy=policy, portfolio=portfolio, trace=trace,
               train=test_train, held=test_held,
               all_yes=all_yes, all_no=all_no,
               tune_wall=round(time.time() - t0, 2))
    with open('exp/v9x/bench_tapas_global.json', 'w') as f:
        json.dump(out, f, indent=1)

    def summarize(name, rs):
        print('%-8s n %2d  nodes %4d -> %4d  rank %3d -> %3d  '
              'audit %2d  improved %2d' % (
                  name, len(rs), sum(r['base_nodes'] for r in rs),
                  sum(r['nodes'] for r in rs),
                  sum(r['base_rank'] for r in rs),
                  sum(r['rank'] for r in rs),
                  sum(r['audit_ok'] for r in rs),
                  sum((r['nodes'], r['rank']) <
                      (r['base_nodes'], r['base_rank']) for r in rs)))

    summarize('train', test_train)
    summarize('held', test_held)
    summarize('allYES', all_yes)
    summarize('allNO', all_no)
    print('global policy', {k: round(v, 3) for k, v in bestw.items()},
          'split', round(bests, 3))
    print('wall', round(time.time() - t0, 2))


if __name__ == '__main__':
    main()
