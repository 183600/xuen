"""Scaling experiment for ICF-DC on disjoint unions.

A base instance is chosen from the mined gap corpus (orig-01: n=10,
m=2, OPT=57, one PACT decision at 56 costs 267 nodes).  For k=1..4 we
build the disjoint union of k copies on disjoint machine sets.  The
union has the same OPT (components run in parallel), but the global PACT
decision tree must make the whole LP infeasible at every leaf, so its
work grows with k.  ICF-DC short-circuits on the first NO component: its
NO-side work and its certificate are independent of k.

Global PACT is capped at 20 s per k.  ICF-DC uses the same per-component
`pact_decide`, so the comparison isolates the decomposition rule.
"""
import json
import sys
import time

sys.path[:0] = ['exp/v9r2', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8j', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from dc import (DCCertificate, dc_decide, dc_init, decomposition,
                solve_dc, union_inst)
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


def run_k(base, k, cap=20):
    inst = union_inst(base, k)
    comps = decomposition(inst)
    st = dc_init(inst, comps)
    U = st['U']
    out = dict(k=k, n=inst['n'], m=inst['m'], comps=len(comps),
               L=st['L'], U=U, init_t=st['t'], init_lp=st['init_lp'])
    t0 = time.time()
    r = pact_decide(inst, U - 1, depthcap=None, nodecap=None,
                    timelimit=cap)
    out['pact'] = dict(verdict=r['verdict'], nodes=r.get('nodes'),
                       lp=r.get('lp_solves'), cert_lp=r.get('cert_lp'),
                       timeout=r.get('timeout', False),
                       t=round(time.time() - t0, 3),
                       proof_nodes=proof_nodes(r.get('proof')))
    t0 = time.time()
    d = dc_decide(inst, U - 1, comps=comps, timelimit=cap)
    out['dc_decide'] = dict(verdict=d['verdict'], stopped=d['stopped'],
                            nodes=d['nodes'], lp=d['lp_solves'],
                            cert_lp=d['cert_lp'], t=d['t'])
    if d['verdict'] is False:
        cert = DCCertificate(inst, U, st['schedule'], st['machine'],
                             comps, d['critical'])
        out['dc_cert'] = dict(audit=cert.audit_rdf(),
                              proof_nodes=proof_nodes(d['critical'][2]),
                              proof_h=d['critical'][2].h)
    out['wall'] = round(time.time() - t0, 3)
    return out


if __name__ == '__main__':
    cases = json.load(open('exp/v10c/gap_cases.json'))
    base = cases[1]['inst']
    print('base', cases[1]['case'], 'n', base['n'], 'm', base['m'],
          'opt', cases[1]['opt'], flush=True)
    rows = []
    for k in (1, 2, 3, 4):
        r = run_k(base, k)
        rows.append(r)
        print('k=%d n=%d m=%d comps=%d U=%d | PACT v=%s nodes=%s lp=%s '
              'timeout=%s t=%.2fs | DC v=%s stop=%s nodes=%d t=%.2fs '
              'cert=%s'
              % (r['k'], r['n'], r['m'], r['comps'], r['U'],
                 r['pact']['verdict'], r['pact']['nodes'],
                 r['pact']['lp'], r['pact']['timeout'], r['pact']['t'],
                 r['dc_decide']['verdict'], r['dc_decide']['stopped'],
                 r['dc_decide']['nodes'], r['dc_decide']['t'],
                 r.get('dc_cert', {}).get('audit')), flush=True)

    counts = []
    for f in ('exp/v10c/gap_cases.json',):
        for x in json.load(open(f)):
            counts.append(len(decomposition(x['inst'])))
    import icf
    for _tag, _name, _idx, inst, _known in icf.corpora():
        counts.append(len(decomposition(inst)))
    json.dump(dict(rows=rows,
                   decomp=dict(n=len(counts),
                               one=sum(1 for c in counts if c == 1),
                               max=max(counts),
                               hist={str(c): counts.count(c)
                                     for c in sorted(set(counts))})),
              open('exp/v9r2/dc_bench.json', 'w'), indent=1)
    print('decomposition counts', {c: counts.count(c)
                                   for c in sorted(set(counts))},
          flush=True)
