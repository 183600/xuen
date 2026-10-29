"""Benchmark PTB-ICF against v9.0 ICF on the 252-instance corpus and
on a weak-initialization stress suite.

Weak initialization uses only critical-path / eligibility-load bounds
and a greedy schedule (`chip.base_bounds`), so gaps are 0..13 rather
than the 0/1/5 produced by the full PACT initializer.  Both methods get
the same initial state and the same audited lower-bound proof.
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_bounds
from pact import PACT, pact_decide
from icf import (corpora, run_icf, PartialCertificate, ICFCertificate,
                 cmax, _choose_h)
from ptb import run_ptb
from rdf import check_schedule


def init_weak(inst):
    lb, ub, sched, mach, est, q = base_bounds(inst)
    co = PACT(inst, use_lp=False, use_lns=False, use_lp_sched=False,
              pact_mode='complete', use_ga=False)
    proof = co._ensure_lb_proof(lb)
    if proof is None:
        r = pact_decide(inst, lb - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    return lb, ub, sched, mach, proof


def run_base(inst, known, name, idx, initial, policy='lower-first',
             max_probes=64, escape=True):
    t0 = time.time()
    L, U, sched, mach, proof = initial
    sched = list(sched)
    mach = list(mach)
    probes = lp = nodes = cert_lp = 0
    first = True
    lb0, ub0 = L, U
    partial_ok = partial_fail = 0
    unknown = set()

    def audit():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit()
    while L < U and probes < max_probes:
        if escape and _choose_h(policy, L, U, first) in unknown:
            cand = [t for t in range(L, U) if t not in unknown]
            if not cand:
                break
            h = cand[len(cand) // 2]
        else:
            h = _choose_h(policy, L, U, first)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
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
                sched, mach = list(s2), list(m2)
        else:
            if escape:
                unknown.add(h)
            else:
                break
        audit()
    final = ICFCertificate(inst, U, sched, mach, proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    return dict(name=name, idx=idx, known=known, policy=policy,
                lb=L, ub=U, lb0=lb0, ub0=ub0,
                probes=probes, lp=lp, nodes=nodes, cert_lp=cert_lp,
                total_lp=lp + cert_lp,
                partial_ok=partial_ok, partial_fail=partial_fail,
                partial_final=bool(PartialCertificate(
                    inst, L, U, sched, mach, proof).audit_rdf()),
                certified=bool(L == U and final_ok),
                audit=final_ok,
                ok=bool(L == U and U == known and final_ok and
                        partial_fail == 0),
                t=round(time.time() - t0, 4))


def summarize(rows, label):
    n = len(rows)
    print('\n==', label, 'n', n)
    for pol in sorted(set(r['policy'] for r in rows)):
        rs = [r for r in rows if r['policy'] == pol]
        print(pol,
              'ok', sum(r['ok'] for r in rs),
              'probes', sum(r['probes'] for r in rs),
              'searchLP', sum(r.get('pact_lp', r.get('lp', 0))
                              for r in rs),
              'certLP', sum(r.get('pact_cert_lp',
                                  r.get('cert_lp', 0)) for r in rs),
              'primalLP', sum(r.get('primal_lp', 0) for r in rs),
              'totalLP', sum(r['total_lp'] for r in rs),
              't', round(sum(r['t'] for r in rs), 3),
              'partial_fail', sum(r['partial_fail'] for r in rs),
              'audit', sum(r['audit'] for r in rs),
              'archive_drops', sum(r.get('archive_drops', 0)
                                   for r in rs),
              'greedy_yes', sum(r.get('greedy_yes', 0) for r in rs),
              'integral_yes', sum(r.get('integral_yes', 0)
                                  for r in rs),
              'archive_audit', sum(r.get('archive_audit', 0)
                                   for r in rs))
    by_gap = collections.defaultdict(list)
    for r in rows:
        by_gap[r['ub0'] - r['lb0']].append(r)
    print('gap histogram', dict(sorted(collections.Counter(
        r['ub0'] - r['lb0'] for r in rows).items())))


def main():
    out = dict(normal={}, weak={})
    normal = []
    for corpus, name, idx, inst, known in corpora():
        r = run_ptb(inst, known, name, idx, policy='ptb')
        r['corpus'] = corpus
        normal.append(r)
    out['normal']['ptb'] = normal

    base = json.load(open('exp/v8u/bench_icf_lower-first.json'))
    for pol, path in [('lower-first', 'exp/v8u/bench_icf_lower-first.json'),
                      ('binary', 'exp/v8u/bench_icf_binary.json')]:
        rows = json.load(open(path))
        for r in rows:
            r['total_lp'] = r['pact_lp'] + r['pact_cert_lp']
            r['policy'] = pol
        out['normal'][pol] = rows

    weak = []
    for corpus, name, idx, inst, known in corpora():
        initial = init_weak(inst)
        lb, ub = initial[0], initial[1]
        if ub - lb < 4:
            continue
        for pol in ('lower-first', 'binary'):
            r = run_base(inst, known, name, idx, initial, pol,
                         escape=True)
            r['corpus'] = corpus
            r['policy'] = pol
            weak.append(r)
        r = run_ptb(inst, known, name, idx, policy='ptb',
                    initial=initial)
        r['corpus'] = corpus
        r['policy'] = 'ptb'
        weak.append(r)
        if len([x for x in weak if x['policy'] == 'ptb']) % 20 == 0:
            print('weak', len([x for x in weak if x['policy'] == 'ptb']),
                  flush=True)
    out['weak'] = weak
    json.dump(out, open('exp/v8u/bench_ptb.json', 'w'), indent=1)

    for tag, rows in [('normal', normal),
                      ('normal-lf', out['normal']['lower-first']),
                      ('normal-bin', out['normal']['binary']),
                      ('weak', weak)]:
        summarize(rows, tag)


if __name__ == '__main__':
    main()
