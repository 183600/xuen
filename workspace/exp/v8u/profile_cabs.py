"""Collect full per-horizon probe profiles for the CABS calibration.

The profile records, for every h in the initial bracket, the verdict,
search LP, node count, certificate LP, and Cmax of a YES schedule.
These profiles are the calibration data for the prior and the cost
model; they are not used by the certificate checker.
"""
import argparse
import json
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, cmax
from pact import pact_decide


def profile_one(corp, name, idx, inst, known, L, U):
    prof = {}
    for h in range(int(L), int(U)):
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        prof[str(h)] = dict(
            verdict=r['verdict'],
            lp=r.get('lp_solves', 0),
            nodes=r.get('nodes', 0),
            cert_lp=r.get('cert_lp', 0),
            cmax=(cmax(inst, r['schedule'])
                  if r['verdict'] is True else None))
    return dict(corpus=corp, name=name, idx=idx, known=known,
                L=int(L), U=int(U), n=inst['n'], m=inst['m'],
                profile=prof)


def weak_profile(out='exp/v8u/cabs_profile.json'):
    from hap import weak_rows
    rows = weak_rows(4)
    res = []
    t0 = time.time()
    for i, (corp, name, idx, inst, known, init) in enumerate(rows):
        res.append(profile_one(corp, name, idx, inst, known,
                               init[0], init[1]))
        if i % 20 == 0:
            print('weak', i, round(time.time() - t0, 1), flush=True)
    with open(out, 'w') as f:
        json.dump(res, f, indent=1)
    print('weak wrote', len(res), out, round(time.time() - t0, 2))


def main_profile(out='exp/v8u/cabs_profile_main.json'):
    base = json.load(open('exp/v8u/bench_icf_lower-first.json'))
    rows = list(corpora())
    assert len(base) == len(rows)
    res = []
    t0 = time.time()
    for i, ((corp, name, idx, inst, known), b) in enumerate(zip(rows, base)):
        res.append(profile_one(corp, name, idx, inst, known,
                               b['lb0'], b['ub0']))
        if i % 50 == 0:
            print('main', i, round(time.time() - t0, 1), flush=True)
    with open(out, 'w') as f:
        json.dump(res, f, indent=1)
    print('main wrote', len(res), out, round(time.time() - t0, 2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=('weak', 'main', 'both'),
                    default='both')
    args = ap.parse_args()
    if args.suite in ('weak', 'both'):
        weak_profile()
    if args.suite in ('main', 'both'):
        main_profile()
