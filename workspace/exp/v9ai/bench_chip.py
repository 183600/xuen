"""Large-gap stress test: start ICF-AID from chip bounds (no LP pin).

The 252 corpus with the full pipeline has initial gaps 0/1/5.  Dropping
the LP pin exposes 91 instances with gap >= 2, so the outer probe policy
is actually exercised.  Three policies are compared on the same inner
AIDA oracle.
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9ai', 'exp/v9a', 'exp/v8j', 'exp/v8u', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from icf import corpora
from icfaid import run_icf_aid


POLICIES = ('lower-first', 'binary', 'pact')


def run(policy):
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = run_icf_aid(inst, known, name, idx, policy=policy,
                        inner='aida', init_engine='chip')
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('exp/v9ai/bench_chip_%s.json' % policy, 'w') as f:
        json.dump(rows, f, indent=1)
    print('\n==', policy, '== wall', wall)
    print('ok', sum(r.get('ok', False) for r in rows),
          'cert', sum(r.get('certified', False) for r in rows),
          'q', sum(r.get('queries', 0) for r in rows),
          'lp', sum(r.get('inner_lp', 0) for r in rows),
          'certlp', sum(r.get('inner_cert_lp', 0) for r in rows),
          'pfail', sum(r.get('partial_fail', 0) for r in rows),
          'unk', sum(r.get('unknown', 0) for r in rows),
          't', round(sum(r.get('t', 0) for r in rows), 2))
    hist = collections.Counter((r.get('ub0', 0) - r.get('lb0', 0),
                                r.get('queries', 0)) for r in rows)
    print('gap,q hist', dict(sorted(hist.items())))
    return rows


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which == 'all':
        out = {}
        for p in POLICIES:
            out[p] = run(p)
        print('\n== deltas vs lower-first ==')
        base = {(r['corpus'], r['name'], r['idx']): r
                for r in out['lower-first']}
        for p in ('binary', 'pact'):
            dl = dq = 0
            for r in out[p]:
                b = base[(r['corpus'], r['name'], r['idx'])]
                dl += r.get('inner_lp', 0) - b.get('inner_lp', 0)
                dq += r.get('queries', 0) - b.get('queries', 0)
            print(p, 'dq', dq, 'dlp', dl)
    elif which in POLICIES:
        run(which)
    else:
        raise SystemExit('unknown: %s' % which)
