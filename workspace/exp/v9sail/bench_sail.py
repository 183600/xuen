"""Benchmark SAIL-ICF against v9.0 ICF-PACT lower-first on the 252 corpus.

Configurations:
  icf        : v9.0 lower-first (one probe at L, then binary)
  sail       : SA (6000 iters, 4 restarts, seed 0) before each probe
  sail-rand  : same but a different SA seed
  sail-dsu   : SA with the DSU slot decoder (equivalence/slow check)

The artifact table uses `icf`, `sail`, and `sail-rand`; `sail-dsu` is a
smaller cross-check.
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9sail', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, run_icf
from sail import run_sail, decode_interval, decode_dsu


def aggregate(rows, label):
    print('\n==', label, '==')
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'lp', sum(r['pact_lp'] for r in rs),
              'pin', sum(r['pin_lp'] for r in rs),
              'sa_it', sum(r.get('sa_iters', 0) for r in rs),
              'sa_t', round(sum(r.get('sa_time', 0.0) for r in rs), 2),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'lp', sum(r['pact_lp'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          'sa_it', sum(r.get('sa_iters', 0) for r in rows),
          'sa_t', round(sum(r.get('sa_time', 0.0) for r in rows), 2),
          't', round(sum(r['t'] for r in rows), 2),
          'partial_fail', sum(r.get('partial_fail', 0) for r in rows),
          'closure_bad', sum(not r.get('closure_audit', True)
                             for r in rows))


def run(label, fn):
    t0 = time.time()
    rows = []
    for corpus, name, idx, inst, known in corpora():
        r = fn(inst, known, name, idx)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('exp/v9sail/bench_%s.json' % label, 'w') as f:
        json.dump(rows, f, indent=1)
    aggregate(rows, '%s (wall %.2f)' % (label, wall))
    return rows


def main():
    which = sys.argv[1:] or ['icf', 'sail', 'sail-rand']
    out = {}
    if 'icf' in which:
        out['icf'] = run('icf', lambda inst, known, name, idx:
                         run_icf(inst, known, name, idx,
                                 policy='lower-first'))
    if 'sail' in which:
        out['sail'] = run('sail', lambda inst, known, name, idx:
                          run_sail(inst, known, name, idx,
                                   sa_iters=6000, sa_restarts=4,
                                   seed=0, decoder=decode_interval))
    if 'sail-rand' in which:
        out['sail-rand'] = run('sail-rand', lambda inst, known, name, idx:
                               run_sail(inst, known, name, idx,
                                        sa_iters=6000, sa_restarts=4,
                                        seed=17, decoder=decode_interval))
    if 'sail-dsu' in which:
        out['sail-dsu'] = run('sail-dsu', lambda inst, known, name, idx:
                              run_sail(inst, known, name, idx,
                                       sa_iters=1500, sa_restarts=2,
                                       seed=0, decoder=decode_dsu))
    if len(out) > 1 and 'icf' in out:
        base = {(r['corpus'], r['name'], r['idx']): r
                for r in out['icf']}
        print('\n== deltas vs icf ==')
        for label, rows in out.items():
            if label == 'icf':
                continue
            dq = dlp = 0
            better = same = worse = 0
            for r in rows:
                b = base[(r['corpus'], r['name'], r['idx'])]
                d = r['pact_lp'] - b['pact_lp']
                dlp += d
                dq += r['queries'] - b['queries']
                if d < 0:
                    better += 1
                elif d == 0:
                    same += 1
                else:
                    worse += 1
            print(label, 'dq', dq, 'dlp', dlp,
                  'better/same/worse', better, same, worse)


if __name__ == '__main__':
    main()
