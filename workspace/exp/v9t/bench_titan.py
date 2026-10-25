"""Benchmark v9.4 TITAN-ALC: indexed tolerant search + tabu repair.

Modes
-----
full       TITAN with the normal AIDA cascade; tabu only on a hole.
notabu     same, but the tabu repair is disabled.
cap4       a deliberate 4-node space budget: holes are forced, and the
           repair cascade (portfolio + tabu + complete fallback) runs.
cap4_tabu  the same forced-hole run with the tabu repair enabled.
all        all four.
"""
import json
import sys
import time

sys.path[:0] = ['exp/v9t', 'exp/v9a', 'exp/v8o', 'exp/v8j', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from titan import TITAN


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


def one(tag, name, idx, inst, known, **kw):
    t0 = time.time()
    co = TITAN(inst, **kw)
    r = co.optimize()
    dt = round(time.time() - t0, 4)
    titan = r.get('titan', [])
    row = dict(tag=tag, name=name, idx=idx, known=known,
               opt=r.get('opt'), lb=r.get('lb'), ub=r.get('ub0'),
               certified=bool(r.get('certified')),
               Q=int(r.get('queries', 0)),
               audit=bool(r.get('audit')),
               total_audit=bool(r.get('total_audit')),
               cert_h=r.get('cert_h'),
               pin_lp=int(getattr(co, 'pin_lp', 0)),
               titan_lp=int(r.get('titan_lp', 0)),
               titan_cert=int(r.get('titan_cert', 0)),
               titan_nodes=int(r.get('titan_nodes', 0)),
               tabu_calls=sum(1 for x in titan if x.get('titan_tabu')),
               tabu_evals=int(r.get('titan_evals', 0)),
               repairs=sum(1 for x in titan if x.get('titan_repair')),
               fallbacks=sum(1 for x in titan
                             if x.get('titan_fallback')),
               t=dt)
    row['ok'] = bool(row['certified'] and row['opt'] == known
                     and row['audit'] and row['total_audit']
                     and row['cert_h'] == known - 1)
    return row


def summarize(mode, rows, wall):
    print('\n==', mode, '== wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['tag'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'Q', sum(r['Q'] for r in rs),
              'audit', sum(r['total_audit'] for r in rs),
              'pin', sum(r['pin_lp'] for r in rs),
              'titan_lp', sum(r['titan_lp'] for r in rs),
              'certlp', sum(r['titan_cert'] for r in rs),
              'nodes', sum(r['titan_nodes'] for r in rs),
              'tabu', sum(r['tabu_calls'] for r in rs),
              'evals', sum(r['tabu_evals'] for r in rs),
              'repair', sum(r['repairs'] for r in rs),
              'fallback', sum(r['fallbacks'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'Q', sum(r['Q'] for r in rows),
          'audit', sum(r['total_audit'] for r in rows),
          'pin', sum(r['pin_lp'] for r in rows),
          'titan_lp', sum(r['titan_lp'] for r in rows),
          'certlp', sum(r['titan_cert'] for r in rows),
          'nodes', sum(r['titan_nodes'] for r in rows),
          'tabu', sum(r['tabu_calls'] for r in rows),
          'evals', sum(r['tabu_evals'] for r in rows),
          'repair', sum(r['repairs'] for r in rows),
          'fallback', sum(r['fallbacks'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))


def run(mode):
    if mode == 'full':
        kw = dict(titan_cap=None, titan_tabu=True)
    elif mode == 'notabu':
        kw = dict(titan_cap=None, titan_tabu=False)
    elif mode == 'cap4':
        kw = dict(titan_cap=4, titan_tabu=False)
    elif mode == 'cap4_tabu':
        kw = dict(titan_cap=4, titan_tabu=True)
    else:
        raise SystemExit('unknown mode: %s' % mode)
    t0 = time.time()
    rows = []
    for tag, name, idx, inst, known in corpora():
        rows.append(one(tag, name, idx, inst, known, **kw))
    wall = round(time.time() - t0, 2)
    with open('exp/v9t/bench_titan_%s.json' % mode, 'w') as f:
        json.dump(rows, f, indent=1)
    summarize(mode, rows, wall)
    return rows


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which == 'all':
        for m in ('full', 'notabu', 'cap4', 'cap4_tabu'):
            run(m)
    else:
        run(which)
