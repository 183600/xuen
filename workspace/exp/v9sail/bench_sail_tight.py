"""Tight-corpus benchmark: v9.0 ICF vs SAIL configurations.

The corpus is the 252-instance v9.0 corpus.  Every configuration is
checked against the same known optimum, the same initial bounds, and
the same complete pact_decide oracle.  The table reports probes,
search LPs, SA iterations/time, wall time, and certificate audits.

Configurations:
  icf        : v9.0 lower-first (baseline)
  sail-300   : SA 300 iters / 1 restart
  sail-600   : SA 600 iters / 1 restart
  sail-1500  : SA 1500 iters / 2 restarts
  sail-6000  : SA 6000 iters / 4 restarts
  sail-1500s17: same as sail-1500 with seed 17
"""
import json
import sys
import time

sys.path[:0] = ['exp/v9sail', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, run_icf
from sail import run_sail, decode_interval


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
    for tag, pred in (('gap0', lambda r: r['ub0'] == r['lb0']),
                      ('gap1', lambda r: r['ub0'] - r['lb0'] == 1),
                      ('gap5', lambda r: r['ub0'] - r['lb0'] == 5)):
        rs = [r for r in rows if pred(r)]
        if rs:
            print(tag, 'n', len(rs), 'q', sum(r['queries'] for r in rs),
                  'lp', sum(r['pact_lp'] for r in rs),
                  't', round(sum(r['t'] for r in rs), 2))


def main():
    configs = [('icf', None), ('sail-300', (300, 1, 0)),
               ('sail-600', (600, 1, 0)), ('sail-1500', (1500, 2, 0)),
               ('sail-6000', (6000, 4, 0)),
               ('sail-1500s17', (1500, 2, 17))]
    all_rows = {}
    for label, cfg in configs:
        t0 = time.time()
        rows = []
        for corpus, name, idx, inst, known in corpora():
            if cfg is None:
                r = run_icf(inst, known, name, idx,
                            policy='lower-first')
            else:
                iters, rest, seed = cfg
                r = run_sail(inst, known, name, idx,
                             sa_iters=iters, sa_restarts=rest,
                             seed=seed, decoder=decode_interval)
            r['corpus'] = corpus
            rows.append(r)
        wall = round(time.time() - t0, 2)
        all_rows[label] = rows
        with open('exp/v9sail/bench_tight_%s.json' % label, 'w') as f:
            json.dump(rows, f, indent=1)
        aggregate(rows, '%s (wall %.2f)' % (label, wall))
    with open('exp/v9sail/bench_tight_all.json', 'w') as f:
        json.dump(all_rows, f, indent=1)
    base = {(r['corpus'], r['name'], r['idx']): r
            for r in all_rows['icf']}
    print('\n== deltas vs icf ==')
    for label, rows in all_rows.items():
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
