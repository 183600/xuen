"""Final BAM-PACT benchmark for the round-1 artifact.

Outputs:
  exp/v10b/bench_bam_main_{W8,W16,W32,W32_naco}.json
  exp/v10b/bench_bam_gap_{W8,W16,W32,W32_naco,W32_binary}.json
  exp/v10b/bench_icf_gap.json  (copy of the ICF gap baseline)
"""
import json
import shutil
import sys
import time

sys.path[:0] = ['exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from bam import run_bam
from icf import corpora


def summarize(rows, label):
    cert = sum(r['certified'] for r in rows)
    audit = sum(r['audit'] for r in rows)
    probes = sum(r['probes'] for r in rows)
    lp = sum(r['lp'] for r in rows)
    certlp = sum(r['cert_lp'] for r in rows)
    pin = sum(r['pin_lp'] for r in rows)
    total = sum(r['total_lp'] for r in rows)
    peak = max(r['peak_leaves'] for r in rows)
    stops = sum(r['memory_stops'] for r in rows)
    t = round(sum(r['t'] for r in rows), 2)
    print('%-18s n=%3d cert=%3d audit=%3d probes=%4d searchLP=%4d '
          'certLP=%4d pinLP=%3d totalLP=%4d peak=%2d stops=%d t=%5.2fs'
          % (label, len(rows), cert, audit, probes, lp, certlp, pin,
             total, peak, stops, t))


def run_main():
    rows = list(corpora())
    for tag, kw in [
        ('W32', dict(W=32, use_aco=True, aco_gamma=0.0,
                    memory_mode='stop', policy='lower')),
        ('W16', dict(W=16, use_aco=True, aco_gamma=0.0,
                    memory_mode='stop', policy='lower')),
        ('W8', dict(W=8, use_aco=True, aco_gamma=0.0,
                   memory_mode='stop', policy='lower')),
        ('W32_naco', dict(W=32, use_aco=False, memory_mode='stop',
                          policy='lower')),
    ]:
        t0 = time.time()
        out = []
        for corpus, name, idx, inst, known in rows:
            r = run_bam(inst, known, name, idx, **kw)
            r['corpus'] = corpus
            out.append(r)
        path = 'exp/v10b/bench_bam_main_%s.json' % tag
        with open(path, 'w') as f:
            json.dump(out, f, indent=1)
        print('\nmain', tag, 'wall', round(time.time() - t0, 2))
        summarize(out, 'all')
        for c in ('base', 'pert', 'stress'):
            summarize([r for r in out if r['corpus'] == c], c)
        print('aco improved instances', sum(1 for r in out
                                            if r['aco_best'] is not None))


def run_gap():
    cases = json.load(open('exp/v10b/gap_stress.json'))
    for tag, kw in [
        ('W32', dict(W=32, use_aco=True, aco_gamma=0.0,
                     memory_mode='stop', policy='lower')),
        ('W16', dict(W=16, use_aco=True, aco_gamma=0.0,
                     memory_mode='stop', policy='lower')),
        ('W8', dict(W=8, use_aco=True, aco_gamma=0.0,
                    memory_mode='stop', policy='lower')),
        ('W32_naco', dict(W=32, use_aco=False, memory_mode='stop',
                          policy='lower')),
        ('W32_binary', dict(W=32, use_aco=True, aco_gamma=0.0,
                            memory_mode='stop', policy='binary')),
    ]:
        t0 = time.time()
        out = []
        for d in cases:
            r = run_bam(d['inst'], d['opt'], 'gap', d['idx'], **kw)
            r['seed'] = d['seed']
            r['lb0'] = d['lb0']
            r['ub0'] = d['ub0']
            out.append(r)
        path = 'exp/v10b/bench_bam_gap_%s.json' % tag
        with open(path, 'w') as f:
            json.dump(out, f, indent=1)
        print('\ngap', tag, 'wall', round(time.time() - t0, 2))
        summarize(out, 'gap')
        print('optimal', sum(r['U'] == r['known'] for r in out),
              'unknown', sum(r['unknown'] for r in out),
              'contractions', sum(r['contractions'] for r in out))


if __name__ == '__main__':
    shutil.copy('/tmp/icf_gap.json', 'exp/v10b/bench_icf_gap.json')
    run_main()
    run_gap()
