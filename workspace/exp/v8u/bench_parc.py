"""Benchmark PARC-ICF: primary ICF plus a certified (Cmax, W) frontier.

Run from the workspace root:
    .venv/bin/python exp/v8u/bench_parc.py
"""
import argparse
import collections
import json
import sys
import time

sys.path[:0] = [
    'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
    'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
    'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13',
]

from icf import corpora, run_icf
from parc import bb_secondary, weights, wsum


def pareto_keep(points):
    best = {}
    for p in points:
        cp = p['cmax'] if p['cmax'] is not None else p['h']
        key = (cp, round(p['a'], 9))
        q = best.get(key)
        if (q is None or p['b'] > q['b'] + 1e-9
                or (abs(p['b'] - q['b']) <= 1e-9 and p['D'] < q['D'])):
            best[key] = p
    cand = list(best.values())
    keep = []
    for p in cand:
        cp = p['cmax'] if p['cmax'] is not None else p['h']
        dom = False
        for q in cand:
            if q is p:
                continue
            cq = q['cmax'] if q['cmax'] is not None else q['h']
            if (cq <= cp and q['a'] <= p['a'] + 1e-9
                    and (cq < cp - 1e-9 or q['a'] < p['a'] - 1e-9)):
                dom = True
                break
        if not dom:
            keep.append(p)
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--deltas', default='0,1,2,4,8')
    ap.add_argument('--nodecap', type=int, default=1024)
    ap.add_argument('--eps', type=float, default=0.0)
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--out', default='exp/v8u/bench_parc_unit.json')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()
    deltas = [int(x) for x in args.deltas.split(',') if x.strip()]
    rows = list(corpora())
    if args.start:
        rows = rows[args.start:]
    if args.limit is not None:
        rows = rows[:args.limit]

    out = []
    t0 = time.time()
    for pos, (corpus, name, idx, inst, known) in enumerate(rows):
        k = args.start + pos
        r = run_icf(inst, known, name, idx, policy='lower-first')
        if not r['certified']:
            out.append(dict(k=k, corpus=corpus, name=name, idx=idx,
                            U=known, error='primary'))
            continue
        s, m = r['schedule'], r['machine']
        w = weights(inst, 'unit')
        W0 = wsum(inst, s, w)
        inc, cur = (list(s), list(m)), W0
        pts = []
        for D in deltas:
            o = bb_secondary(inst, known + D, w=w, incumbent=inc,
                             nodecap=args.nodecap, eps=args.eps)
            if o['_best_sched'] is not None and o['a'] < cur - 1e-9:
                inc, cur = o['_best_sched'], o['a']
            pts.append(dict(
                D=D, h=known + D, a=o['a'], b=o['b'],
                exact=o['exact'], eps_ok=o['eps_ok'],
                root=o['root'], cmax=o['best_cmax'],
                nodes=o['nodes'], lp=o['lp'], dive_nodes=o['dive_nodes'],
                dive_best=o['dive_best'], open=o['open'],
                root_integral=o['root_integral'],
                farkas=o['farkas_checks'], farkas_fail=o['farkas_fail'],
                holes=o['holes'], t=o['t'], reason=o['reason']))
        front = pareto_keep(pts)
        out.append(dict(k=k, corpus=corpus, name=name, idx=idx, U=known,
                        W0=W0, W=cur, pts=pts,
                        keep=[p['D'] for p in front], front=len(front),
                        front_pts=[(p['D'], p['cmax'], p['a'], p['b'])
                                   for p in front]))
        if not args.quiet and pos % 25 == 0:
            print(pos, corpus, name, idx, 'W0', W0, 'W', cur,
                  'front', len(front), flush=True)

    json.dump(out, open(args.out, 'w'), indent=1)
    ps = [p for x in out if 'pts' in x for p in x['pts']]
    print('instances', len(out), 'wall', round(time.time() - t0, 2))
    for D in deltas:
        q = [x['pts'][deltas.index(D)] for x in out if 'pts' in x]
        print('D=%d exact=%d eps=%d nodes=%d lp=%d dives=%d W=%g t=%.2f'
              % (D, sum(p['exact'] for p in q),
                 sum(p['eps_ok'] for p in q), sum(p['nodes'] for p in q),
                 sum(p['lp'] + p['dive_nodes'] for p in q),
                 sum(1 for p in q if p['dive_nodes']),
                 sum(p['a'] for p in q), sum(p['t'] for p in q)))
    print('front_hist', dict(sorted(collections.Counter(
        x['front'] for x in out if 'pts' in x).items())))
    print('improved', sum(1 for x in out if x.get('W', x.get('W0', 0)) <
                          x.get('W0', 0)),
          'saved', sum(x.get('W0', 0) - x.get('W', 0) for x in out))
    print('max_ratio', max((p['a'] / p['b'] for p in ps if p['b'] > 0),
                           default=0))
    bad = [(x['name'], x['idx'], p['D'], p['a'], p['b'], p['nodes'])
           for x in out if 'pts' in x for p in x['pts'] if not p['exact']]
    print('not_exact', bad[:20])


if __name__ == '__main__':
    main()
