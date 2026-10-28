"""Benchmark TA-ICF on the 252-instance corpus and the 160-instance weak corpus.

Usage (from the workspace root):
    .venv/bin/python exp/v8u/bench_taicf.py --suite all
    .venv/bin/python exp/v8u/bench_taicf.py --suite main
    .venv/bin/python exp/v8u/bench_taicf.py --suite weak
    .venv/bin/python exp/v8u/bench_taicf.py --suite policy

The weak corpus is the v9.0 weak initialization: chip bounds and the
uncertified base upper bound, with LP pin / LNS disabled.  Its initial
gaps are 4..13, so it is the stress test for the threshold anchor.
"""
import argparse
import json
import os
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, run_icf
from taicf import run_taicf
from pact import PACT


def _weak_rows():
    from hap import weak_rows
    return weak_rows(4)


def _summarize(rows):
    keys = ('probes', 'pact_lp', 'pact_cert_lp', 'pin_lp',
            'prescan_lp', 'anchor_proof_lp', 'anchor_cert_lp',
            'sat_calls', 'sat_yes')
    z = {k: sum(r.get(k, 0) for r in rows) for k in keys}
    # threshold_anchor's Farkas dual is already counted in prescan_lp;
    # anchor_cert_lp is a subset for the normal path.  Only add the
    # cert LP separately when the fallback _farkas_proof path was used.
    z['total_lp'] = (z['pact_lp'] + z['pact_cert_lp'] + z['pin_lp']
                     + z['prescan_lp'] + z['anchor_proof_lp']
                     + (z['anchor_cert_lp'] if z['anchor_proof_lp'] else 0))
    z['n'] = len(rows)
    z['ok'] = sum(bool(r.get('ok')) for r in rows)
    z['certified'] = sum(bool(r.get('certified')) for r in rows)
    z['partial_fail'] = sum(r.get('partial_fail', 0) for r in rows)
    z['partial_checks'] = sum(r.get('partial_ok', 0)
                              + r.get('partial_fail', 0) for r in rows)
    z['t'] = round(sum(r.get('t', 0) for r in rows), 2)
    z['sat_time'] = round(sum(r.get('sat_time', 0) for r in rows), 2)
    return z


def _write(name, rows):
    path = 'exp/v8u/' + name
    with open(path, 'w') as f:
        json.dump(rows, f, indent=1)
    print('wrote', path)


def run_main(sat=False):
    rows = list(corpora())
    out = []
    t0 = time.time()
    for c, name, idx, inst, known in rows:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
        proof = co._ensure_lb_proof(lb)
        r = run_taicf(inst, known, name, idx,
                      (lb, ub, sched, mach, proof),
                      policy='anchor', prescan_min_gap=4, l_probes=2,
                      sat_first=sat)
        r['corpus'] = c
        r['pin_lp'] = getattr(co, 'pin_lp', 0)
        out.append(r)
    tag = 'sat' if sat else 'pact'
    print('main TA-ICF', tag, json.dumps(_summarize(out), sort_keys=True),
          'wall', round(time.time() - t0, 2))
    _write('bench_taicf_main_%s.json' % tag, out)
    return out


def run_weak(sat=False, baselines=True):
    rows = _weak_rows()
    out = []
    t0 = time.time()
    for c, name, idx, inst, known, init in rows:
        r = run_taicf(inst, known, name, idx, init,
                      policy='anchor', prescan_min_gap=4, l_probes=2,
                      sat_first=sat)
        r['corpus'] = c
        out.append(r)
    tag = 'sat' if sat else 'pact'
    print('weak TA-ICF', tag, json.dumps(_summarize(out), sort_keys=True),
          'wall', round(time.time() - t0, 2))
    _write('bench_taicf_weak_%s.json' % tag, out)
    if baselines and not sat:
        base = {}
        for pol in ('lower-first', 'binary'):
            t1 = time.time()
            rs = []
            for c, name, idx, inst, known, init in rows:
                r = run_icf(inst, known, name, idx, policy=pol,
                            initial=init)
                r['corpus'] = c
                rs.append(r)
            print('weak ICF', pol, json.dumps(_summarize(rs),
                                              sort_keys=True),
                  'wall', round(time.time() - t1, 2))
            base[pol] = rs
        _write('bench_taicf_weak_baselines.json', base)
    return out


def run_policy():
    rows = _weak_rows()
    progs = [(tau, lp) for tau in (0, 4, 6, 8) for lp in (1, 2, 3)]
    out = {}
    for tau, lp in progs:
        rs = []
        t0 = time.time()
        for c, name, idx, inst, known, init in rows:
            r = run_taicf(inst, known, name, idx, init,
                          policy='anchor', prescan_min_gap=tau,
                          l_probes=lp)
            rs.append(dict(corpus=c, name=name, idx=idx, known=known,
                           probes=r['probes'],
                           total_lp=(r['pact_lp'] + r['pact_cert_lp']
                                     + r['prescan_lp']
                                     + r['anchor_proof_lp']
                                     + (r['anchor_cert_lp']
                                        if r['anchor_proof_lp'] else 0)),
                           ok=r['ok'], t=r['t']))
        key = '%d,%d' % (tau, lp)
        out[key] = rs
        print('policy', key, 'probes', sum(r['probes'] for r in rs),
              'lp', sum(r['total_lp'] for r in rs),
              'ok', sum(r['ok'] for r in rs),
              'wall', round(time.time() - t0, 2), flush=True)
    _write('bench_taicf_policy.json', out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', default='all',
                    choices=('all', 'main', 'weak', 'policy'))
    ap.add_argument('--sat', action='store_true')
    args = ap.parse_args()
    if args.suite in ('all', 'main'):
        run_main(sat=False)
        if args.sat or args.suite == 'all':
            run_main(sat=True)
    if args.suite in ('all', 'weak'):
        run_weak(sat=False, baselines=True)
        if args.sat or args.suite == 'all':
            run_weak(sat=True, baselines=False)
    if args.suite in ('all', 'policy'):
        run_policy()


if __name__ == '__main__':
    main()
