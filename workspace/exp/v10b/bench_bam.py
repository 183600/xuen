"""Benchmark BAM-PACT on the 252-instance corpus and the gap-stress set."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from bam import run_bam
from icf import corpora, run_icf


def bench(rows, tag, **kw):
    out = []
    t0 = time.time()
    for corpus, name, idx, inst, known in rows:
        r = run_bam(inst, known, name, idx, **kw)
        r['corpus'] = corpus
        out.append(r)
    wall = round(time.time() - t0, 2)
    path = 'exp/v10b/bench_bam_%s.json' % tag
    with open(path, 'w') as f:
        json.dump(out, f, indent=1)
    print('\n==', tag, '== wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in out if r.get('corpus') == c]
        if rs:
            print(c, 'n', len(rs), 'cert', sum(r['certified'] for r in rs),
                  'audit', sum(r['audit'] for r in rs),
                  'probes', sum(r['probes'] for r in rs),
                  'lp', sum(r['lp'] for r in rs),
                  'certlp', sum(r['cert_lp'] for r in rs),
                  'splits', sum(r['splits'] for r in rs),
                  'peak', max(r['peak_leaves'] for r in rs),
                  't', round(sum(r['t'] for r in rs), 2))
    print('all cert', sum(r['certified'] for r in out),
          'audit', sum(r['audit'] for r in out),
          'probes', sum(r['probes'] for r in out),
          'lp', sum(r['lp'] for r in out),
          'certlp', sum(r['cert_lp'] for r in out),
          'total', sum(r['lp'] + r['cert_lp'] for r in out),
          'splits', sum(r['splits'] for r in out),
          'peak', max(r['peak_leaves'] for r in out),
          't', round(sum(r['t'] for r in out), 2))
    print('aco best', sum(1 for r in out if r['aco_best'] is not None),
          'aco impr', sum(r['aco_impr'] for r in out))
    print('(gap0,probes)', dict(sorted(collections.Counter(
        (r['init_U'] - r['init_L'], r['probes']) for r in out).items())))
    return out


if __name__ == '__main__':
    rows = list(corpora())
    for tag, kw in [
        ('W32_lower_naco', dict(W=32, use_aco=False, memory_mode='stop',
                                policy='lower')),
        ('W32_lower_aco', dict(W=32, use_aco=True, memory_mode='stop',
                               policy='lower')),
        ('W8_lower_naco', dict(W=8, use_aco=False, memory_mode='stop',
                               policy='lower')),
        ('W16_lower_naco', dict(W=16, use_aco=False, memory_mode='stop',
                                policy='lower')),
    ]:
        bench(rows, tag, **kw)
