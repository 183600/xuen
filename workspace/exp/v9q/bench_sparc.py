"""Benchmark v9.5 SPARC on the 252-instance corpus."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9q', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from pact import PACT
from sparc import make_sparc

SPARC = make_sparc(PACT)


def corpora():
    for tag, rows in (('base', base_corpus()),
                      ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known


def run_all(tag, **kw):
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        t1 = time.time()
        co = SPARC(inst, **kw)
        r = co.optimize()
        r.update(corpus=corpus, name=name, idx=idx, known=known,
                 t=round(time.time() - t1, 4))
        r['ok'] = bool(r.get('certified') and r.get('opt') == known
                       and r.get('audit') and r.get('proof')
                       and r.get('total_audit')
                       and r.get('cert_h') == known - 1)
        r['total_kind'] = getattr(getattr(co, 'total_cert', None),
                                  'kind', None)
        r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                                  'kind', None)
        r['pin_lp'] = getattr(co, 'pin_lp', 0)
        r['bb_lp'] = getattr(co, 'bb_lp', 0)
        r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
        r['probe_lp'] = getattr(co, 'probe_lp', 0)
        r['probe_calls'] = getattr(co, 'probe_calls', 0)
        r['probe_removed'] = getattr(co, 'probe_removed', 0)
        r['probe_steps'] = getattr(co, 'probe_steps', 0)
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('/tmp/sparc_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    with open('exp/v9q/bench_sparc_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    print('\n==', tag, '== wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'pin', sum(r['pin_lp'] for r in rs),
              'probe_lp', sum(r['probe_lp'] for r in rs),
              'probe_rm', sum(r['probe_removed'] for r in rs),
              'search', sum(r['pact_lp'] for r in rs),
              'cert_lp', sum(r['pact_cert_lp'] for r in rs),
              'total', sum(r['total_audit'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          'probe_lp', sum(r['probe_lp'] for r in rows),
          'probe_rm', sum(r['probe_removed'] for r in rows),
          'search', sum(r['pact_lp'] for r in rows),
          'cert_lp', sum(r['pact_cert_lp'] for r in rows),
          'total', sum(r['total_audit'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', dict(collections.Counter(r['proof_kind'] for r in rows)))
    print('probe steps', sum(r['probe_steps'] for r in rows))
    return rows


if __name__ == '__main__':
    for tag, kw in (('b0', dict(probe_budget=0)),
                    ('b4', dict(probe_budget=4)),
                    ('b8', dict(probe_budget=8)),
                    ('b16', dict(probe_budget=16)),
                    ('b32', dict(probe_budget=32))):
        run_all(tag, **kw)
