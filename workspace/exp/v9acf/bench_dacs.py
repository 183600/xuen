"""Benchmark DACS on the 252 corpus and the 16-instance gap stress set."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9acf', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from dacs import run_dacs
from icf import corpora


def gap_rows():
    return json.load(open('exp/v10b/gap_stress.json'))


def summarize(rows, label):
    n = len(rows)
    print('%-22s n=%3d ok=%3d cert=%3d probes=%4d lp=%5d certLP=%4d '
          'rounds=%3d aud_fail=%d unknown=%d t=%6.2fs'
          % (label, n, sum(r['ok'] for r in rows),
             sum(r['certified'] for r in rows),
             sum(r['probes'] for r in rows), sum(r['lp'] for r in rows),
             sum(r['cert_lp'] for r in rows),
             sum(r['rounds'] for r in rows),
             sum(r['audit_fail'] for r in rows),
             sum(r['unknown'] for r in rows),
             sum(r['t'] for r in rows)))


def run_corpus():
    rows = list(corpora())
    out = {}
    for mode in ('both-parallel', 'both-race'):
        t0 = time.time()
        rs = []
        for corpus, name, idx, inst, known in rows:
            r = run_dacs(inst, known, name, idx, mode=mode)
            r['corpus'] = corpus
            rs.append(r)
        out[mode] = rs
        print('\n== 252', mode, 'wall', round(time.time() - t0, 2))
        summarize(rs, 'all')
        for c in ('base', 'pert', 'stress'):
            summarize([r for r in rs if r['corpus'] == c], c)
        hist = collections.Counter((r['ub0'] - r['lb0'], r['probes'],
                                    r['rounds']) for r in rs)
        print('(gap,probes,rounds):', dict(sorted(hist.items())))
        lh = [r for r in rs if r['name'] == 'large_het' and r['idx'] == 7]
        if lh:
            print('large_het 7', {k: lh[0][k] for k in
                                  ('lb0', 'ub0', 'opt', 'probes', 'lp',
                                   'rounds', 'ok')})
    with open('exp/v9acf/bench_dacs_252.json', 'w') as f:
        json.dump(out, f, indent=1)


def run_gap():
    out = {}
    for mode in ('both-parallel', 'both-race', 'lower', 'upper',
                 'binary'):
        t0 = time.time()
        rs = []
        for d in gap_rows():
            r = run_dacs(d['inst'], d['opt'], 'gap', d['idx'],
                         mode=mode)
            r['seed'] = d['seed']
            rs.append(r)
        out[mode] = rs
        print('\n== gap', mode, 'wall', round(time.time() - t0, 2))
        summarize(rs, 'gap')
    with open('exp/v9acf/bench_dacs_gap.json', 'w') as f:
        json.dump(out, f, indent=1)


if __name__ == '__main__':
    run_corpus()
    run_gap()
