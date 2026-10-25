"""Run PACT-C and measure the one-pass audit of every branch proof."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from pact import PACT
from stream_audit import audit_stream, tree_stats


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


def main():
    rows = []
    t0 = time.time()
    for tag, name, idx, inst, known in corpora():
        co = PACT(inst, pact_depth=None, use_ga=False)
        r = co.optimize()
        p = getattr(co, 'lb_proof', None)
        if getattr(p, 'kind', None) != 'branch':
            continue
        tree = p.tree
        nodes, height, leaves = tree_stats(tree)
        ok_rec = p.audit_rdf()
        t1 = time.time()
        ok_st, mx, ne, t_st = audit_stream(inst, p.h, tree)
        t2 = time.time()
        rows.append(dict(corpus=tag, name=name, idx=idx, known=known,
                         h=p.h, nodes=nodes, height=height, leaves=leaves,
                         ok_rec=ok_rec, ok_stream=ok_st, max_stack=mx,
                         events=ne, t_stream=round(t_st, 6),
                         t_rec=round(t2 - t1 - t_st, 6)))
    wall = round(time.time() - t0, 2)
    with open('exp/v9u/bench_stream.json', 'w') as f:
        json.dump(rows, f, indent=1)
    print('wall', wall, 'proofs', len(rows),
          'ok_rec', sum(r['ok_rec'] for r in rows),
          'ok_stream', sum(r['ok_stream'] for r in rows))
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'nodes', sum(r['nodes'] for r in rs),
              'height_max', max(r['height'] for r in rs),
              'stack_max', max(r['max_stack'] for r in rs),
              'events', sum(r['events'] for r in rs),
              't_stream', round(sum(r['t_stream'] for r in rs), 3),
              't_rec', round(sum(r['t_rec'] for r in rs), 3))
    print('global height_max', max(r['height'] for r in rows),
          'stack_max', max(r['max_stack'] for r in rows),
          'nodes', sum(r['nodes'] for r in rows),
          'events', sum(r['events'] for r in rows))


if __name__ == '__main__':
    main()
