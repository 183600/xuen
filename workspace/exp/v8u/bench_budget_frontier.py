"""Benchmark FRI-ICF: capped single-leaf ICF vs. multi-leaf frontier refinement.

Both methods share the same PACT initialization and the same fixed-h
oracle.  The only difference is the budget: the oracle is capped at
``nodecap`` LP nodes per decision.  Single-leaf ICF returns a partial
certificate on UNKNOWN; the frontier refines the leaf and continues.

Run from the workspace root:

    .venv/bin/python exp/v8u/bench_budget_frontier.py --suite normal
    .venv/bin/python exp/v8u/bench_budget_frontier.py --suite weak

The weak suite uses ``hap.weak_rows(4)``: critical-path lower bounds and a
greedy upper bound, so the initial gaps are 4..13 rather than 0/1/5.
"""
import argparse
import json
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import (corpora, cmax, _choose_h, PartialCertificate,
                 ICFCertificate)
from pact import PACT, pact_decide
from rdf import check_schedule
from hap import weak_rows
from tamo import run_tamo


def _initial(inst, initial):
    if initial is not None:
        L, U, s, m, proof = initial
        return (int(L), int(U), list(s), list(m), proof)
    co = PACT(inst, pact_mode='complete', use_ga=False)
    L, U, s, m = co.initial_bounds()
    if U is None:
        raise RuntimeError('no initial upper bound')
    proof = co._ensure_lb_proof(L)
    if proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    if proof is None:
        raise RuntimeError('no initial lower-bound proof')
    return int(L), int(U), list(s), list(m), proof


def run_capped_icf(inst, known, name, idx, initial=None, nodecap=1,
                   policy='lower-first', max_probes=64):
    """v9.0 ICF with a node-capped oracle; UNKNOWN stops the loop."""
    t0 = time.time()
    try:
        L, U, s, m, proof = _initial(inst, initial)
    except Exception as exc:
        return dict(name=name, idx=idx, known=known, ok=False,
                    certified=False, error=str(exc), t=0.0)
    probes = lp = nodes = cert_lp = unknown = 0
    partial_ok = partial_fail = 0
    first = True
    lb0, ub0 = L, U

    def audit():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, s, m, proof, probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit()
    while L < U and probes < max_probes:
        h = _choose_h(policy, L, U, first)
        r = pact_decide(inst, h, depthcap=None, nodecap=nodecap)
        probes += 1
        first = False
        lp += r.get('lp_solves', 0)
        nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            L = h + 1
            proof = r['proof']
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                s, m = list(s2), list(m2)
        else:
            unknown += 1
            break
        audit()

    final = ICFCertificate(inst, U, s, m, proof) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, s, m, proof, probe=probes)
    partial_final = bool(partial.audit_rdf())
    return dict(
        name=name, idx=idx, known=known, nodecap=nodecap, policy=policy,
        lb0=lb0, ub0=ub0, L=L, U=U, opt=U,
        probes=probes, lp=lp, nodes=nodes, cert_lp=cert_lp,
        unknown=unknown,
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final,
        certified=bool(L == U and final_ok),
        audit=final_ok,
        ok=bool(L == U == known and final_ok and partial_fail == 0),
        t=round(time.time() - t0, 4),
    )


def run_suite(which='normal', nodecap=1, audit_every=True):
    if which == 'normal':
        items = [(c, name, idx, inst, known, None)
                 for c, name, idx, inst, known in corpora()]
    elif which == 'weak':
        items = [(c, name, idx, inst, known, initial)
                 for c, name, idx, inst, known, initial
                 in weak_rows(4)]
    else:
        raise ValueError(which)

    rows = []
    t0 = time.time()
    for j, (c, name, idx, inst, known, initial) in enumerate(items):
        cap = run_capped_icf(inst, known, name, idx, initial=initial,
                             nodecap=nodecap)
        cap['corpus'] = c
        cap['method'] = 'capped-icf'
        fr = run_tamo(inst, known, name, idx, B=nodecap, initial=initial,
                      audit_every=audit_every)
        fr['corpus'] = c
        fr['method'] = 'frontier'
        # Keep a single row with both outcomes so rescue counts are direct.
        row = dict(corpus=c, name=name, idx=idx, known=known,
                   initial_gap=cap['ub0'] - cap['lb0'])
        for k, v in cap.items():
            if k not in row:
                row['capped_' + k] = v
        for k, v in fr.items():
            if k in ('name', 'idx', 'known', 'corpus'):
                continue
            if k in row:
                row['frontier_' + k] = v
            else:
                row[k] = v
        row['capped_certified'] = bool(cap.get('certified'))
        row['frontier_certified'] = bool(fr.get('certified'))
        row['rescued'] = bool(not cap.get('certified')
                              and fr.get('certified'))
        rows.append(row)
        if (j + 1) % 20 == 0 or j + 1 == len(items):
            print('%s %d/%d %s t=%.1f' % (which, j + 1, len(items),
                                          name, time.time() - t0),
                  flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=('normal', 'weak', 'both'),
                    default='both')
    ap.add_argument('--nodecap', type=int, default=1)
    ap.add_argument('--no-audit', action='store_true')
    args = ap.parse_args()
    audit_every = not args.no_audit
    suites = ('normal', 'weak') if args.suite == 'both' else (args.suite,)
    for which in suites:
        rows = run_suite(which, nodecap=args.nodecap,
                         audit_every=audit_every)
        path = 'exp/v8u/bench_budget_%s.json' % which
        with open(path, 'w') as f:
            json.dump(rows, f, indent=1)
        print('\n==', which, '->', path)
        for c in ('base', 'pert', 'stress'):
            rs = [r for r in rows if r.get('corpus') == c]
            if rs:
                print(c, 'n', len(rs),
                      'capped cert', sum(r['capped_certified'] for r in rs),
                      'frontier cert', sum(r['frontier_certified']
                                           for r in rs),
                      'rescued', sum(r['rescued'] for r in rs),
                      'frontier probes',
                      sum(r.get('probes', 0) for r in rs),
                      'splits', sum(r.get('splits', 0) for r in rs))
        print('all n', len(rows),
              'capped cert', sum(r['capped_certified'] for r in rows),
              'frontier cert', sum(r['frontier_certified']
                                   for r in rows),
              'rescued', sum(r['rescued'] for r in rows),
              'capped unknown', sum(r.get('capped_unknown', 0)
                                    for r in rows),
              'capped probes', sum(r.get('capped_probes', 0)
                                   for r in rows),
              'capped lp', sum(r.get('capped_lp', 0) for r in rows),
              'frontier probes', sum(r.get('probes', 0) for r in rows),
              'frontier splits', sum(r.get('splits', 0) for r in rows),
              'frontier lp', sum(r.get('lp', 0) for r in rows),
              'frontier cert_lp', sum(r.get('cert_lp', 0)
                                      for r in rows),
              'frontier max_leaves',
              max(r.get('max_leaves', 0) for r in rows),
              'partial_fail', sum(r.get('partial_fail', 0)
                                  for r in rows),
              'rank_fail', sum(r.get('rank_fail', 0) for r in rows),
              't capped', round(sum(r.get('capped_t', 0)
                                    for r in rows), 2),
              't frontier', round(sum(r.get('t', 0) for r in rows), 2))


if __name__ == '__main__':
    main()
