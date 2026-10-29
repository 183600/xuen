"""Benchmark BALANCE-ICF against fixed probe policies.

Weak init: base_bounds + greedy orders.  This deliberately gives a loose
lower bound and a tight upper bound, exposing the failure mode of the
previous round's lower-first policy.

PACT init: the v8.9 initialization.  This is the regression test: a
prior calibrated on PACT-tight gaps should reproduce lower-first.
"""
import sys
import json
import time
import math
import collections
import argparse

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora
from balance import (initial_state, fit_prior, prior_weights, run_balance,
                     ProbeCache)

TAGS = ('base', 'pert', 'stress')


def load_states(init='weak'):
    rows = []
    for tag, name, idx, inst, known in corpora():
        cache = ProbeCache()
        st = initial_state(inst, known, init=init, cache=cache)
        if st is None:
            print('no state', init, tag, name, idx, flush=True)
            continue
        rows.append(dict(tag=tag, name=name, idx=idx, inst=inst,
                         known=known, cache=cache, state=st))
    return rows


def cv_prior(rows, test_tag):
    train = [dict(L=r['state']['L'], U=r['state']['U'],
                  known=r['known']) for r in rows if r['tag'] != test_tag]
    return fit_prior(train)


def table_from_states(rows):
    return fit_prior([dict(L=r['state']['L'], U=r['state']['U'],
                           known=r['known']) for r in rows])


def policy_list(kind):
    if kind == 'weak':
        return ['lower-first', 'upper-first', 'upper-once', 'binary',
                'pact', 'bayes', 'bayes-cap:2', 'bayes-cap:3',
                'bayes-cap:4', 'bayes:l1', 'bayes:l2', 'bayes-wrong',
                'bayes-uniform', 'bayes-cap:3:f0.05', 'bayes:f0.05',
                'bayes-oracle']
    return ['lower-first', 'binary', 'bayes', 'bayes-cap:3',
            'bayes-wrong']


def run_init(init, policies, out_path):
    t0 = time.time()
    rows = load_states(init)
    print('states', init, len(rows), 'time', round(time.time() - t0, 2),
          flush=True)
    full_table = table_from_states(rows)
    # wrong prior = the table from the other initialization
    other = load_states('pact' if init == 'weak' else 'weak')
    wrong_table = table_from_states(other)
    results = {}
    for tag in TAGS:
        test = [r for r in rows if r['tag'] == tag]
        tab = cv_prior(rows, tag)
        for pol in policies:
            out = []
            for r in test:
                pt = tab
                if pol == 'bayes-wrong':
                    pt = wrong_table
                elif pol == 'bayes-uniform':
                    pt = {}
                elif pol == 'bayes-oracle':
                    pt = full_table
                row = run_balance(
                    r['inst'], r['known'], r['name'], r['idx'],
                    init=init, policy=pol, prior_table=pt,
                    cache=r['cache'])
                row['corpus'] = tag
                out.append(row)
            results.setdefault(pol, []).extend(out)
        print('tag', tag, 'time', round(time.time() - t0, 2), flush=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=1)
    summarize(results, init)
    return results


def summarize(results, init):
    print('\n==', init)
    for pol, rs in results.items():
        print('%-16s n %3d cert %3d ok %3d probes %4d lp %5d certlp %4d '
              'initlp %4d unk %2d pfail %d t %6.2f'
              % (pol, len(rs), sum(r['certified'] for r in rs),
                 sum(r['ok'] for r in rs),
                 sum(r['probes'] for r in rs),
                 sum(r['lp'] for r in rs),
                 sum(r['cert_lp'] for r in rs),
                 sum(r['init_lp'] for r in rs),
                 sum(r['unknown'] for r in rs),
                 sum(r['partial_fail'] for r in rs),
                 sum(r['t'] for r in rs)))
    print('\nby tag (probes/lp/time):')
    for pol, rs in results.items():
        d = {}
        for tag in TAGS:
            xs = [r for r in rs if r['corpus'] == tag]
            d[tag] = (sum(r['probes'] for r in xs),
                      sum(r['lp'] for r in xs),
                      round(sum(r['t'] for r in xs), 2))
        print('%-16s %s' % (pol, d))


def calibration(rows):
    print('\n== gap distributions')
    for init in ('weak', 'pact'):
        rr = load_states(init)
        c = collections.Counter((r['state']['U'] - r['state']['L'],
                                 r['known'] - r['state']['L'],
                                 r['state']['U'] - r['known'])
                                for r in rr)
        print(init, 'g/d/e', sorted(c.items()))
        print(init, 'd', collections.Counter(
            r['known'] - r['state']['L'] for r in rr))
        print(init, 'e', collections.Counter(
            r['state']['U'] - r['known'] for r in rr))
        print(init, 'oracle probes', collections.Counter(
            (0 if r['state']['L'] == r['state']['U'] == r['known'] else
             1 if ((r['state']['L'] == r['known']) ^
                   (r['state']['U'] == r['known'])) else 2)
            for r in rr))


def logloss(rows, table, test_tag):
    train_rows = [dict(L=r['state']['L'], U=r['state']['U'],
                       known=r['known']) for r in rows
                  if r['tag'] != test_tag]
    vals = []
    for r in rows:
        if r['tag'] != test_tag:
            continue
        g = r['state']['U'] - r['state']['L']
        d = r['known'] - r['state']['L']
        if g <= 0:
            continue
        w = prior_weights(table, g)
        vals.append(-math.log(max(w[d], 1e-12)))
    return sum(vals) / max(1, len(vals))


def prior_calibration():
    for init in ('weak', 'pact'):
        rows = load_states(init)
        other = load_states('pact' if init == 'weak' else 'weak')
        wrong = table_from_states(other)
        print('\n== prior log-loss', init)
        for tag in TAGS:
            tab = cv_prior(rows, tag)
            print(tag, 'cv', round(logloss(rows, tab, tag), 4),
                  'wrong', round(logloss(rows, wrong, tag), 4))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--init', default='weak')
    ap.add_argument('--only', default='')
    ap.add_argument('--out', default='')
    args = ap.parse_args()
    if args.only:
        pols = [x for x in args.only.split(',') if x]
    else:
        pols = policy_list(args.init)
    out = args.out or ('exp/v8u/bench_balance_%s.json' % args.init)
    run_init(args.init, pols, out)
