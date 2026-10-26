"""Benchmark the live MTF-PACT frontier and the single-leaf cap-1 baseline."""
import json
import sys
import time

sys.path[:0] = ['exp/v9m', 'exp/v8u', 'exp/v8j', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13',
                'exp/v09']

import icf
from frontier import certify_frontier
from icf import corpora, run_icf
from pact import pact_decide


def frontier_caps(rows):
    res = {}
    for cap in (1, 2, 4, 8):
        t0 = time.time()
        ok = aud = lp = leaves = splits = sub = 0
        multi = maxleaves = 0
        for corpus, name, idx, inst, known in rows:
            r = certify_frontier(inst, known - 1, cap=cap, max_leaves=4000)
            ok += int(r['verdict'] is False)
            aud += int(bool(r.get('audit')))
            lp += r['lp']
            leaves += r['leaves']
            splits += r['splits']
            sub += r['sub_hits']
            multi += int(r['leaves'] > 1)
            maxleaves = max(maxleaves, r['leaves'])
        res[str(cap)] = dict(ok=ok, audit=aud, lp=lp, leaves=leaves,
                             splits=splits, sub=sub, maxleaves=maxleaves,
                             multi=multi, t=round(time.time() - t0, 3))
        print('frontier cap', cap, res[str(cap)], flush=True)
    json.dump(res, open('exp/v9m/frontier_caps.json', 'w'), indent=1)


def single_cap1(rows):
    base = json.load(open('exp/v8u/bench_icf_lower-first.json'))
    gap = {(x['name'], x['idx']): x['opt'] - x['lb0'] for x in base}
    orig = icf.pact_decide

    def dec(inst, h, **kw):
        kw = dict(kw)
        kw.pop('nodecap', None)
        kw.pop('depthcap', None)
        return pact_decide(inst, h, depthcap=None, nodecap=1, **kw)

    icf.pact_decide = dec
    out = []
    for corpus, name, idx, inst, known in rows:
        r = run_icf(inst, known, name, idx, policy='lower-first')
        out.append(dict(name=name, idx=idx, corpus=corpus,
                        gap=gap[(name, idx)], certified=r['certified'],
                        audit=r['audit'], probes=r['probes'],
                        lp=r['pact_lp'], unknown=r['unknown'],
                        partial_fail=r['partial_fail']))
    icf.pact_decide = orig
    summ = dict(
        certified=sum(x['certified'] for x in out),
        audit=sum(x['audit'] for x in out),
        probes=sum(x['probes'] for x in out),
        lp=sum(x['lp'] for x in out),
        unknown=sum(x['unknown'] for x in out),
        partial_fail=sum(x['partial_fail'] for x in out),
        by_gap={str(g): [sum(1 for x in out
                              if x['gap'] == g and x['certified']),
                         sum(1 for x in out if x['gap'] == g)]
                for g in sorted(set(x['gap'] for x in out))})
    print('single cap1', summ)
    json.dump(dict(rows=out, summary=summ),
              open('exp/v9m/single_cap1.json', 'w'), indent=1)


if __name__ == '__main__':
    rows = list(corpora())
    frontier_caps(rows)
    single_cap1(rows)
