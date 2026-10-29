"""252-instance comparison: PACT-C vs PIVOT-1 closing probe only."""
import json
import sys
import time

sys.path[:0] = ['exp/v8q', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np

import pact as pact_mod
from chip import base_corpus, pert_corpus, stress_corpus
from pact import run_pact
from pivot import PivotRanker, pivot_decide
from train_pivot import collect


def corpora():
    for tag, fn in (('base', base_corpus), ('pert', pert_corpus),
                    ('stress', stress_corpus)):
        for row in fn():
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known


KNOWN_BY_UID = {}
_uid = 0
for _tag, _name, _idx, _inst, _known in corpora():
    _uid += 1
    KNOWN_BY_UID[_uid] = _known


class LookupRanker:
    def __init__(self, base, orders_by_uid, known_by_uid):
        self.base = base
        self.orders_by_uid = orders_by_uid
        self.known_by_uid = known_by_uid

    def order(self, X, inst=None, h=None):
        uid = None if inst is None else inst.get('__pivot_uid__')
        k = self.known_by_uid.get(uid)
        if k is not None and h == k - 1:
            o = self.orders_by_uid.get(uid)
            if o is not None:
                return list(o)
        return self.base.order(X, inst, h)


def loo_orders():
    gx, gy, meta = collect()
    orders = {}
    for gi in range(len(gx)):
        tr_x = [gx[j] for j in range(len(gx)) if j != gi]
        tr_y = [gy[j] for j in range(len(gy)) if j != gi]
        ranker = PivotRanker.fit_groups(tr_x, tr_y)
        orders[meta[gi]['uid']] = ranker.order(gx[gi])
    return orders


def run_all(tag, ranker=None, max_attempts=4, use_pivot=True):
    orig = pact_mod.pact_decide
    stats = dict(calls=0, pivots=0, success=0, fallback=0)

    def wrapper(inst, h, **kw):
        if kw.get('branch_jobs') is not None or kw.get('depthcap') is not None:
            return orig(inst, h, **kw)
        uid = inst.get('__pivot_uid__')
        k = KNOWN_BY_UID.get(uid)
        if k is None or h != k - 1:
            return orig(inst, h, **kw)
        r = pivot_decide(inst, h, ranker=ranker,
                         max_attempts=max_attempts, fallback=True, **kw)
        stats['calls'] += 1
        p = r.get('pivot') or {}
        stats['pivots'] += len(p.get('attempts', []))
        stats['success'] += p.get('success') is not None
        stats['fallback'] += bool(p.get('fallback'))
        return r

    if use_pivot:
        pact_mod.pact_decide = wrapper
    rows = []
    t0 = time.time()
    try:
        uid = 0
        for corpus, name, idx, inst, known in corpora():
            uid += 1
            inst['__pivot_uid__'] = uid
            r = run_pact(inst, known, name, idx, pact_depth=None,
                         use_ga=False)
            r['corpus'] = corpus
            rows.append(r)
    finally:
        if use_pivot:
            pact_mod.pact_decide = orig
    wall = round(time.time() - t0, 2)
    out = dict(tag=tag, wall=wall, stats=stats, rows=rows)
    json.dump(out, open('/tmp/pivot_%s.json' % tag, 'w'), indent=1)
    print('\n==', tag, '== wall', wall)
    print('ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          'pact_lp', sum(r['pact_lp'] for r in rows),
          'pact_nodes', sum(r['pact_nodes'] for r in rows),
          'cert_lp', sum(r['pact_cert_lp'] for r in rows),
          'total', sum(r['total_audit'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('pivot', stats)
    return out


if __name__ == '__main__':
    base = run_all('base', use_pivot=False)
    static = run_all('static', ranker=None, max_attempts=4)
    ranker = PivotRanker.from_json('exp/v8q/pivot_weights.json')
    learned = run_all('learned', ranker=ranker, max_attempts=4)
    orders = loo_orders()
    loo_ranker = LookupRanker(ranker, orders, KNOWN_BY_UID)
    loo_run = run_all('loo', ranker=loo_ranker, max_attempts=4)
    summary = {}
    for k, v in [('base', base), ('static', static),
                 ('learned', learned), ('loo', loo_run)]:
        summary[k] = dict(
            wall=v['wall'],
            ok=sum(r['ok'] for r in v['rows']),
            q=sum(r['queries'] for r in v['rows']),
            pin=sum(r['pin_lp'] for r in v['rows']),
            pact_lp=sum(r['pact_lp'] for r in v['rows']),
            pact_nodes=sum(r['pact_nodes'] for r in v['rows']),
            cert_lp=sum(r['pact_cert_lp'] for r in v['rows']),
            total=sum(r['total_audit'] for r in v['rows']),
            t=round(sum(r['t'] for r in v['rows']), 2),
            pivot=v['stats'])
    json.dump(summary, open('exp/v8q/bench_pivot_summary.json', 'w'),
              indent=1)
    print('\nSUMMARY')
    print(json.dumps(summary, indent=1))
