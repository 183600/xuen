"""v9.1 AB-SAT/ICF: SAT-shielded null-window Alpha-Beta on top of ICF-PACT.

The trusted state is v9.0's partial certificate

    (L, U, s, m, pi)   with   pi : NO(L-1), Cmax(s)=U, L<=U.

The outer loop always opens the null window h = U-1.  An untrusted SAT
oracle may return a checked schedule (fail-high) or an UNSAT hint.  The
hint never enters a proof: only pact_decide(h) may move L.  A trusted
NO(U-1) closes the bracket because the incumbent already gives OPT<=U.
"""
import sys
import time

sys.path[:0] = ['exp/v9ab', 'exp/v8t', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import (PartialCertificate, ICFCertificate, cmax, _choose_h)
from pact import PACT, pact_decide
from pact_sat import SATWitness
from rdf import check_schedule


def _audit(inst, L, U, s, m, pi, probe):
    pc = PartialCertificate(inst, L, U, s, m, pi, probe=probe)
    return pc, bool(pc.audit_rdf())


def run_ab_sat(inst, known, name, idx, max_probes=64, fallback='lower-first',
               sat_enabled=True):
    """Run AB-SAT/ICF on one instance and return a benchmark row."""
    t0 = time.time()
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-initial-ub', t=0.0)
    L, U = int(lb), int(ub)
    sched = list(sched) if sched is not None else None
    mach = list(mach) if mach is not None else None
    pi = co._ensure_lb_proof(L)
    if pi is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            pi = r['proof']
    if pi is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-lb-proof', t=0.0)

    sat = SATWitness(inst) if sat_enabled else None
    probes = sat_calls = sat_yes = sat_unsat = sat_unknown = 0
    search_lp = search_nodes = cert_lp = 0
    partial_ok = partial_fail = 0
    steps = []
    first = True
    lb0, ub0 = L, U

    def check_state():
        nonlocal partial_ok, partial_fail
        pc, ok = _audit(inst, L, U, sched, mach, pi, probes)
        if ok:
            partial_ok += 1
        else:
            partial_fail += 1
        return pc

    check_state()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = U - 1
        if sat is not None:
            sat_calls += 1
            got = sat.solve(h)
            if got is not None:
                s2, m2, c2 = got
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U, sched, mach = c2, list(s2), list(m2)
                    sat_yes += 1
                    probes += 1
                    steps.append(dict(h=h, v=True, engine='sat',
                                      cmax=c2, L0=L0, U0=U0,
                                      L1=L, U1=U))
                    check_state()
                    continue
            else:
                sat_unsat += 1
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        search_lp += r.get('lp_solves', 0)
        search_nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            L, pi = h + 1, r['proof']
            steps.append(dict(h=h, v=False, engine='pact',
                              lp=r.get('lp_solves', 0),
                              cert_lp=r.get('cert_lp', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
            break
        if r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U, sched, mach = c2, list(s2), list(m2)
            steps.append(dict(h=h, v=True, engine='pact',
                              cmax=c2, lp=r.get('lp_solves', 0),
                              cert_lp=r.get('cert_lp', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            sat_unknown += 1
            h2 = _choose_h(fallback, L, U, first)
            d2 = pact_decide(inst, h2, depthcap=None, nodecap=None)
            probes += 1
            search_lp += d2.get('lp_solves', 0)
            search_nodes += d2.get('nodes', 0)
            cert_lp += d2.get('cert_lp', 0)
            if d2['verdict'] is False:
                L, pi = h2 + 1, d2['proof']
            elif d2['verdict'] is True:
                s2, m2 = d2['schedule'], d2['machine']
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U, sched, mach = c2, list(s2), list(m2)
            else:
                steps.append(dict(h=h2, v=None, engine='fallback',
                                  L0=L0, U0=U0, L1=L, U1=U))
                break
        first = False
        check_state()

    final = ICFCertificate(inst, U, sched, mach, pi) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    pc = PartialCertificate(inst, L, U, sched, mach, pi, probe=probes)
    partial_final = bool(pc.audit_rdf())
    return dict(
        name=name, idx=idx, known=known,
        opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok), audit=final_ok,
        cert_h=(U - 1 if L == U else None),
        probes=probes, queries=probes,
        pact_lp=search_lp, pact_nodes=search_nodes,
        pact_cert_lp=cert_lp,
        sat_calls=sat_calls, sat_yes=sat_yes, sat_unsat=sat_unsat,
        sat_unknown=sat_unknown, sat_t=(round(sat.time, 4) if sat else 0.0),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final, steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(pi, 'kind', None)),
        t=round(time.time() - t0, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final))
