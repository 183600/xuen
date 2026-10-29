"""Replay ICF probe evidence through the union-find closure.

The closure is a join-semilattice: NO(h) is downward closed, YES(h) is
upward closed, and the bracket is the join of all evidence.  This script
collects the evidence of a v9.0 lower-first run, shuffles it, and checks
that the DSU closure returns the same bracket and audits every witness.

It is a certificate-commutativity test, not a new search.
"""
import json
import random
import sys

sys.path[:0] = ['exp/v9sail', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, cmax
from pact import PACT, pact_decide
from sail import EvidenceDSU


def collect(inst, co):
    L, U, sched, mach = co.initial_bounds()
    L, U = int(L), int(U)
    proof = co._ensure_lb_proof(L)
    ev = [('no', L - 1, proof), ('yes', U, sched, mach)]
    lc, uc = L, U
    first = True
    steps = 0
    while lc < uc and steps < 64:
        h = lc if first else (lc + uc) // 2
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        steps += 1
        first = False
        if r['verdict'] is False:
            ev.append(('no', h, r['proof']))
            lc = h + 1
        elif r['verdict'] is True:
            c = cmax(inst, r['schedule'])
            ev.append(('yes', c, r['schedule'], r['machine']))
            uc = min(uc, c)
        else:
            break
    return (lc, uc), ev, L, U


def replay(inst, ev, H):
    cl = EvidenceDSU(H)
    for e in ev:
        if e[0] == 'no':
            cl.add_no(e[1], e[2])
        else:
            cl.add_yes(e[1], e[2], e[3])
    return cl


def main():
    rng = random.Random(20261027)
    rows = []
    total_shuffles = 0
    mismatches = 0
    audit_fail = 0
    for corpus, name, idx, inst, known in corpora():
        co = PACT(inst, pact_mode='complete', use_ga=False)
        (lc, uc), ev, L0, U0 = collect(inst, co)
        H = max(1, sum(inst['p']))
        # sequential reference
        ref = replay(inst, ev, H)
        ref_bracket = ref.bracket()
        ref_audit = ref.audit(inst)
        if ref_bracket != (lc, uc) or not ref_audit:
            audit_fail += 1
        # shuffle several times
        for trial in range(5):
            sh = ev[:]
            rng.shuffle(sh)
            cl = replay(inst, sh, H)
            total_shuffles += 1
            if cl.bracket() != (lc, uc):
                mismatches += 1
            if not cl.audit(inst):
                audit_fail += 1
        # extreme orders: all NO then all YES, and reverse
        for order in (sorted(ev, key=lambda e: e[0] == 'yes'),
                      sorted(ev, key=lambda e: e[0] == 'no')):
            cl = replay(inst, order, H)
            total_shuffles += 1
            if cl.bracket() != (lc, uc):
                mismatches += 1
            if not cl.audit(inst):
                audit_fail += 1
        rows.append(dict(corpus=corpus, name=name, idx=idx,
                         L0=L0, U0=U0, L=lc, U=uc,
                         evidence=len(ev), audit=ref_audit,
                         bracket=ref_bracket))
    out = dict(instances=len(rows), shuffles=total_shuffles,
               mismatches=mismatches, audit_fail=audit_fail,
               evidence_total=sum(r['evidence'] for r in rows),
               rows=rows)
    with open('exp/v9sail/closure_replay.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('instances', out['instances'], 'shuffles', out['shuffles'],
          'evidence', out['evidence_total'],
          'mismatches', out['mismatches'],
          'audit_fail', out['audit_fail'])


if __name__ == '__main__':
    main()
