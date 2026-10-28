"""Benchmark PBC-ICF on the normal 252 and weak 160 suites.

Examples (run from the workspace root):

    .venv/bin/python exp/v8u/bench_pbc.py --suite normal \
        --policies lower-first:1,batch-mid:2,batch-mid:4

    .venv/bin/python exp/v8u/bench_pbc.py --suite weak \
        --policies lower-first:1,binary:1,batch-mid:2,batch-mid:4

    .venv/bin/python exp/v8u/bench_pbc.py --suite weak \
        --policies batch-mid:2 --workers 2 --out /tmp/pbc_weak_par2.json
"""
import argparse
import json
import multiprocessing as mp
import sys
import time
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pbc import run_pbc, normal_items, weak_items


def parse_policies(text):
    out = []
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        if ':' in part:
            pol, p = part.split(':', 1)
            out.append((pol, int(p)))
        else:
            out.append((part, 1))
    return out


def suite_items(suite, limit):
    items = normal_items() if suite == 'normal' else weak_items(4)
    return items[:limit] if limit else items


def summarize(rows, label):
    def s(k):
        return sum((r.get(k, 0) or 0) for r in rows)

    print('==', label, '==')
    print('n', len(rows), 'ok', sum(1 for r in rows if r.get('ok')),
          'cert', sum(1 for r in rows if r.get('certified')),
          'probes', s('probes'), 'rounds', s('rounds'),
          'lp', s('lp'), 'cert_lp', s('cert_lp'),
          'span_lp', s('span_lp'), 'nodes', s('nodes'),
          'useful', s('useful'), 'dominated', s('dominated'),
          'unknown', s('unknown'), 'invalid', s('invalid'),
          'stalls', s('stalls'),
          'partial_ok', s('partial_ok'), 'partial_fail', s('partial_fail'),
          'complex_checks', s('complex_checks'),
          'complex_fail', s('complex_fail'),
          't', round(sum((r.get('t', 0) or 0) for r in rows), 2))
    print('probe_hist',
          dict(sorted(collections.Counter(r.get('probes', 0)
                                          for r in rows).items())))
    print('round_hist',
          dict(sorted(collections.Counter(r.get('rounds', 0)
                                          for r in rows).items())))
    print('gap_hist',
          dict(sorted(collections.Counter(r.get('gap0', 0)
                                          for r in rows).items())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=['normal', 'weak'], required=True)
    ap.add_argument('--policies',
                    default='lower-first:1,binary:1,batch-mid:2,batch-mid:4')
    ap.add_argument('--workers', type=int, default=0,
                    help='0 = serial; >0 = persistent process pool')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    items = suite_items(args.suite, args.limit)
    policies = parse_policies(args.policies)
    pool = None
    if args.workers > 0:
        pool = mp.get_context('fork').Pool(args.workers)
    rows = []
    t0 = time.time()
    try:
        for pol, P in policies:
            for c, name, idx, inst, known, ini in items:
                r = run_pbc(inst, known, name, idx, policy=pol, P=P,
                            initial=ini, pool=pool)
                r['corpus'] = c
                r['suite'] = args.suite
                rows.append(r)
            summarize([r for r in rows if r['policy'] == pol and
                       r['P'] == P],
                      '%s %s P=%d' % (args.suite, pol, P))
    finally:
        if pool is not None:
            pool.close()
            pool.join()
    wall = round(time.time() - t0, 2)
    print('total wall', wall, 'rows', len(rows))
    if args.out:
        meta = dict(suite=args.suite, policies=policies,
                    workers=args.workers, limit=args.limit,
                    total_s=wall, n=len(rows))
        with open(args.out, 'w') as f:
            json.dump(dict(meta=meta, rows=rows), f, indent=1)
        print('wrote', args.out)


if __name__ == '__main__':
    main()
