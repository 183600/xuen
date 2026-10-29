"""Scaling of divide-and-conquer WIDP on disjoint unions.

All copies are independent (disjoint machine sets), so the global optimum
is the component optimum and one component NO(opt-1) proof suffices for
global NO(opt-1).  Global PACT must refute the monolithic LP at every
leaf.  The experiment isolates the structural divide step.
"""
import json
import sys
import time

sys.path[:0] = ['exp/v10w', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from dc_widp import (dc_widp_certificate, decomposition, subinstance,
                     union_inst)
from pact import pact_decide


def proof_nodes(p):
    if p is None or not hasattr(p, 'tree'):
        return 0

    def rec(x):
        if x is None:
            return 0
        if x[0] in ('leaf', 'empty'):
            return 1
        return 1 + rec(x[4]) + rec(x[5])
    return rec(p.tree)


def main():
    cases = json.load(open('exp/v10c/gap_cases.json'))
    base = cases[1]['inst']
    opt = cases[1]['opt']
    rows = []
    for k in (1, 2, 3, 4):
        inst = union_inst(base, k)
        comps = decomposition(inst)
        t0 = time.time()
        r = pact_decide(inst, opt - 1, depthcap=None, nodecap=None,
                        timelimit=10)
        pt = time.time() - t0
        t0 = time.time()
        d = dc_widp_certificate(inst, opt)
        dt = time.time() - t0
        row = dict(k=k, n=inst['n'], m=inst['m'], comps=len(comps),
                   opt=opt,
                   pact=dict(verdict=r['verdict'], nodes=r.get('nodes'),
                             lp=r.get('lp_solves'),
                             cert_lp=r.get('cert_lp'),
                             timeout=r.get('timeout', False),
                             proof_nodes=proof_nodes(r.get('proof')),
                             t=round(pt, 3)),
                   dc=dict(ok=d['ok'], states=d.get('states'),
                           t=round(dt, 3)))
        rows.append(row)
        print('k=%d n=%d m=%d comps=%d | PACT v=%s nodes=%s lp=%s '
              'timeout=%s t=%.2fs | DC-WIDP ok=%s states=%s t=%.2fs'
              % (k, inst['n'], inst['m'], len(comps),
                 r['verdict'], r.get('nodes'), r.get('lp_solves'),
                 r.get('timeout', False), pt, d['ok'], d.get('states'), dt),
              flush=True)
    json.dump(rows, open('exp/v10w/bench_scaling.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
