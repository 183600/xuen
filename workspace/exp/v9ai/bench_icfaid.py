"""Benchmark ICF-AID / ICF-AIDF on the 252-instance corpus.

Modes:
  full       ICF-AID with AIDA's memoized box DAG
  nomemo     same, AIDA memo disabled
  nosub      same, subsumption disabled
  single     one AIDA policy instead of the portfolio
  frontier   ICF-AIDF: explicit live DFS frontier
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

from icfaid import run_icf_aid, corpora
from aida import DEFAULT_POLICIES


CONFIGS = {
    'full': dict(inner='aida', aida_kwargs={}),
    'nomemo': dict(inner='aida',
                   aida_kwargs=dict(use_memo=False)),
    'nosub': dict(inner='aida',
                  aida_kwargs=dict(use_sub=False)),
    'single': dict(inner='aida',
                   aida_kwargs=dict(policies=[DEFAULT_POLICIES[0]])),
    'frontier': dict(inner='aidf', budget=10000),
}


def run_config(tag, cfg):
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = run_icf_aid(inst, known, name, idx, **cfg)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('exp/v9ai/bench_icfaid_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    print('\n==', tag, '== wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r.get('ok', False)
                                         for r in rs),
              'cert', sum(r.get('certified', False) for r in rs),
              'q', sum(r.get('queries', 0) for r in rs),
              'lp', sum(r.get('inner_lp', 0) for r in rs),
              'certlp', sum(r.get('inner_cert_lp', 0) for r in rs),
              'pfail', sum(r.get('partial_fail', 0) for r in rs),
              'unk', sum(r.get('unknown', 0) for r in rs),
              't', round(sum(r.get('t', 0) for r in rs), 2))
    print('all ok', sum(r.get('ok', False) for r in rows),
          'cert', sum(r.get('certified', False) for r in rows),
          'q', sum(r.get('queries', 0) for r in rows),
          'lp', sum(r.get('inner_lp', 0) for r in rows),
          'certlp', sum(r.get('inner_cert_lp', 0) for r in rows),
          'audits', sum(r.get('partial_ok', 0) for r in rows),
          'pfail', sum(r.get('partial_fail', 0) for r in rows),
          't', round(sum(r.get('t', 0) for r in rows), 2))
    print('kinds', dict(collections.Counter(
        r.get('proof_kind') for r in rows)))
    return rows


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'full'
    if which == 'all':
        for tag, cfg in CONFIGS.items():
            run_config(tag, cfg)
    elif which in CONFIGS:
        run_config(which, CONFIGS[which])
    else:
        raise SystemExit('unknown: %s' % which)
