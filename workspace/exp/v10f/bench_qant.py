"""Benchmark QANT against BAM on the 252 corpus and the 29 gap cases."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v10f', 'exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from bam import run_bam
from qant import run_qant
from icf import corpora


def summarize(rows, tag):
    print('\n==', tag, '==')
    for c in ('base', 'pert', 'stress', 'gap'):
        rs = [r for r in rows if r.get('corpus', 'gap' if 'corpus' not in r else None) == c]
        if not rs:
            continue
        print(c, 'n', len(rs),
              'cert', sum(r.get('certified', False) for r in rs),
              'audit', sum(r.get('audit', False) for r in rs),
              'probes', sum(r.get('probes', 0) for r in rs),
              'lp', sum(r.get('lp', 0) for r in rs),
              'certlp', sum(r.get('cert_lp', 0) for r in rs),
              'total', sum(r.get('total_lp', 0) for r in rs),
              'spl', sum(r.get('splits', 0) for r in rs),
              'peak', max([r.get('peak_leaves', 0) for r in rs] or [0]),
              't', round(sum(r.get('t', 0) for r in rs), 2),
              'acoimp', sum(r.get('aco_impr', 0) for r in rs))
    print('ALL n', len(rows), 'cert', sum(r.get('certified', False) for r in rows),
          'audit', sum(r.get('audit', False) for r in rows),
          'probes', sum(r.get('probes', 0) for r in rows),
          'lp', sum(r.get('lp', 0) for r in rows),
          'certlp', sum(r.get('cert_lp', 0) for r in rows),
          'total', sum(r.get('total_lp', 0) for r in rows),
          'spl', sum(r.get('splits', 0) for r in rows),
          'peak', max([r.get('peak_leaves', 0) for r in rows] or [0]),
          't', round(sum(r.get('t', 0) for r in rows), 2),
          'acoimp', sum(r.get('aco_impr', 0) for r in rows))


def main():
    corpus = list(corpora())
    cases = json.load(open('exp/v10c/gap_cases.json'))
    variants = [
        ('bam_astar_naco', run_bam, dict(W=32, use_aco=False)),
        ('bam_astar_aco', run_bam, dict(W=32, use_aco=True)),
        ('qant_b05', run_qant, dict(W=32, amp_beta=0.5, aco_gate='gap1')),
        ('qant_b10', run_qant, dict(W=32, amp_beta=1.0, aco_gate='gap1')),
        ('qant_b20', run_qant, dict(W=32, amp_beta=2.0, aco_gate='gap1')),
        ('qant_b40', run_qant, dict(W=32, amp_beta=4.0, aco_gate='gap1')),
        ('qant_b10_naco', run_qant, dict(W=32, amp_beta=1.0, use_aco=False)),
    ]
    for tag, fn, kw in variants:
        out = []
        t0 = time.time()
        for c, name, idx, inst, known in corpus:
            r = fn(inst, known, name, idx, **kw)
            r['corpus'] = c
            out.append(r)
        for j, d in enumerate(cases):
            r = fn(d['inst'], d['opt'], d.get('case'), d.get('idx'), **kw)
            r['corpus'] = 'gap'
            r['gap_kind'] = d.get('kind')
            out.append(r)
        wall = round(time.time() - t0, 2)
        json.dump(out, open('exp/v10f/bench_%s.json' % tag, 'w'), indent=1)
        summarize(out, tag + ' wall ' + str(wall))


if __name__ == '__main__':
    main()
