"""Weak-upper-bound benchmark: bracket repair by SAIL.

For every instance we keep the tight certified lower bound and its
proof, but replace the upper bound by a deliberately weak serial
schedule (random topological order, random eligible machines, no
overlap).  This creates a wide bracket that the v9.0 lower-first loop
must close by binary probing.  SAIL instead runs its primal search:
the annealer lowers U, and the dual probe at L closes the bracket.

Configurations:
  icf        : v9.0 lower-first on the weak bracket
  sail-300   : SA 300 iters / 1 restart before each probe
  sail-1500  : SA 1500 iters / 2 restarts before each probe
"""
import json
import sys
import time

sys.path[:0] = ['exp/v9sail', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, run_icf
from sail import (run_sail, decode_interval, weak_serial_schedule)
from pact import PACT


def initial_rows():
    out = []
    for corpus, name, idx, inst, known in corpora():
        co = PACT(inst, pact_mode='complete', use_ga=False)
        L, U, sched, mach = co.initial_bounds()
        proof = co._ensure_lb_proof(L)
        ws, wm, wc = weak_serial_schedule(inst, seed=idx + 7)
        out.append(dict(corpus=corpus, name=name, idx=idx, inst=inst,
                        known=known, L=int(L), U0=int(U),
                        weakU=int(wc), sched=ws, mach=wm,
                        proof=proof, pin_lp=getattr(co, 'pin_lp', 0)))
    return out


def aggregate(rows, label):
    print('\n==', label, '==')
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'lp', sum(r['pact_lp'] for r in rs),
              'sa_it', sum(r.get('sa_iters', 0) for r in rs),
              'sa_t', round(sum(r.get('sa_time', 0.0) for r in rs), 2),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'lp', sum(r['pact_lp'] for r in rows),
          'sa_it', sum(r.get('sa_iters', 0) for r in rows),
          'sa_t', round(sum(r.get('sa_time', 0.0) for r in rows), 2),
          't', round(sum(r['t'] for r in rows), 2),
          'partial_fail', sum(r.get('partial_fail', 0) for r in rows),
          'closure_bad', sum(not r.get('closure_audit', True)
                             for r in rows))
    # split by tight lower-bound status
    for tag, pred in (('L=OPT', lambda r: r['lb0'] == r['known']),
                      ('L=OPT-1', lambda r: r['lb0'] == r['known'] - 1)):
        rs = [r for r in rows if pred(r)]
        if rs:
            print(tag, 'n', len(rs), 'q', sum(r['queries'] for r in rs),
                  'lp', sum(r['pact_lp'] for r in rs),
                  't', round(sum(r['t'] for r in rs), 2),
                  'sa_t', round(sum(r.get('sa_time', 0.0) for r in rs), 2))


def main():
    which = sys.argv[1:] or ['icf', 'sail-300', 'sail-1500']
    base = initial_rows()
    print('instances', len(base),
          'weakU-OPT', sum(r['weakU'] - r['known'] for r in base),
          'mean', round(sum(r['weakU'] - r['known']
                            for r in base) / len(base), 2))
    out = {}
    if 'icf' in which:
        rows = []
        t0 = time.time()
        for r in base:
            x = run_icf(r['inst'], r['known'], r['name'], r['idx'],
                        policy='lower-first',
                        initial=(r['L'], r['weakU'], r['sched'],
                                 r['mach'], r['proof']))
            x['corpus'] = r['corpus']
            rows.append(x)
        print('icf wall', round(time.time() - t0, 2))
        out['icf'] = rows
        aggregate(rows, 'icf weak-U')
    if 'sail-300' in which:
        rows = []
        t0 = time.time()
        for r in base:
            x = run_sail(r['inst'], r['known'], r['name'], r['idx'],
                         sa_iters=300, sa_restarts=1, seed=0,
                         decoder=decode_interval,
                         initial=(r['L'], r['weakU'], r['sched'],
                                  r['mach'], r['proof']))
            x['corpus'] = r['corpus']
            rows.append(x)
        print('sail-300 wall', round(time.time() - t0, 2))
        out['sail-300'] = rows
        aggregate(rows, 'sail-300 weak-U')
    if 'sail-1500' in which:
        rows = []
        t0 = time.time()
        for r in base:
            x = run_sail(r['inst'], r['known'], r['name'], r['idx'],
                         sa_iters=1500, sa_restarts=2, seed=0,
                         decoder=decode_interval,
                         initial=(r['L'], r['weakU'], r['sched'],
                                  r['mach'], r['proof']))
            x['corpus'] = r['corpus']
            rows.append(x)
        print('sail-1500 wall', round(time.time() - t0, 2))
        out['sail-1500'] = rows
        aggregate(rows, 'sail-1500 weak-U')
    with open('exp/v9sail/bench_sail_weak.json', 'w') as f:
        json.dump(out, f, indent=1)
    if 'icf' in out:
        b = {(r['corpus'], r['name'], r['idx']): r for r in out['icf']}
        print('\n== deltas vs icf weak-U ==')
        for label, rows in out.items():
            if label == 'icf':
                continue
            dq = dlp = 0
            for r in rows:
                x = b[(r['corpus'], r['name'], r['idx'])]
                dq += r['queries'] - x['queries']
                dlp += r['pact_lp'] - x['pact_lp']
            print(label, 'dq', dq, 'dlp', dlp)


if __name__ == '__main__':
    main()
