"""v9.3 KICF: kernelized invariant-carrying frontier.

KICF keeps the v9.0 ICF invariant

    pi proves NO(L-1) and (s,m) proves Cmax(s)=U

but replaces every probe by a kernelized decision:

    h -> EHC reduction -> (empty ? EhcProof : PACT on reduced domains)

The reduction log is the synthesized program.  It is replayable, can be
budgeted, and can be minimized into a small kernel certificate.  This
module is the one-leaf specialization; the proof objects compose with
the v9.0 frontier.
"""
import sys
import time

sys.path[:0] = ['exp/v93', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import (PACT, PartialCertificate, ICFCertificate, _choose_h,
                 cmax, _proof_forbid)
from rdf import check_schedule
from pact import pact_decide
from sdecc import SDLP, heads_tails
from sage import _elig_aware
from ehc2 import (propagate, EhcProof, ReducedNOProof,
                  removed_literals, minimize_events, initial_domains)


def kernel_decide(inst, h, use_prec=True, use_energy=True,
                  energy_mode='all', max_energy_checks=None,
                  max_iters=None, policy=None, seed=0,
                  depthcap=None, nodecap=None, timelimit=None,
                  minimize=False, root_filter=True):
    """Certified decision at horizon h with an EHC reduction front-end."""
    t0 = time.time()
    D, info = propagate(inst, h, use_prec=use_prec,
                        use_energy=use_energy,
                        energy_mode=energy_mode,
                        max_energy_checks=max_energy_checks,
                        max_iters=max_iters)
    teh = time.time() - t0
    base = dict(ehc_t=teh, ehc_checks=info.get('energy_checks', 0),
                ehc_iters=info.get('iters', 0),
                ehc_budget_hit=info.get('budget_hit', False),
                ehc_events=len(info.get('events', [])),
                ehc_min_events=None, removed=0, decide_t=0.0,
                reduced=False, fallback=False, fallback_lp=0)
    if D is None:
        events = info.get('events', [])
        if minimize:
            events = minimize_events(inst, h, events,
                                     info.get('initial_empty'))
            base['ehc_min_events'] = len(events)
        proof = EhcProof(inst, h, events, info.get('initial_empty'))
        return dict(verdict=False, proof=proof, schedule=None,
                    machine=None, nodes=0, leaves=0, depth=0,
                    lp_solves=0, cert_lp=0, unknown=False, t=teh,
                    ehc_empty=True, ehc_reason=info.get('reason'),
                    **base)
    F = removed_literals(inst, h, D)
    base['removed'] = len(F)
    base['ehc_empty'] = False
    base['root_filter'] = False
    base['root_status'] = None
    base['skipped_reduction'] = False
    root_lp = None
    root_res = None
    extra_lp = 0
    if F and root_filter:
        # Synthesized policy: pay one root LP to decide whether the
        # reduction is safe/useful.  Empty reduced LP or an integral
        # reduced root are strong signals; a feasible fractional root is
        # where reduction can change PACT's branching and create holes,
        # so we keep the unreduced procedure there.
        est, q = heads_tails(inst, 0, [0] * inst['n'])
        elig = _elig_aware(inst)
        root_lp = SDLP(inst, h, est, q, use_dom=True,
                       elig_aware=elig, forbid=F)
        root_base = [(0, 1)] * root_lp.N
        root_res = root_lp.solve(root_base)
        extra_lp = 1
        base['root_filter'] = True
        base['root_status'] = int(root_res.status)
        frac = False
        if root_res.status == 0:
            for c, key in enumerate(root_lp.cols):
                zc = root_res.x[c]
                if 1e-7 < zc < 1 - 1e-7:
                    frac = True
                    break
        if root_res.status != 2 and frac:
            base['skipped_reduction'] = True
            root_lp = None
            root_res = None
    td = time.time()
    if base['skipped_reduction']:
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        policy=policy, seed=seed, forbid0=None,
                        timelimit=timelimit)
    else:
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        policy=policy, seed=seed, forbid0=F,
                        root_lp=root_lp, root_res=root_res,
                        timelimit=timelimit)
    r = dict(r)
    if extra_lp:
        r['lp_solves'] = r.get('lp_solves', 0) + extra_lp
    base['decide_t'] = time.time() - td
    base['reduced'] = bool(F) and not base['skipped_reduction']
    if r['verdict'] is None and F and not base['skipped_reduction']:
        # A reduction can remove the only fractional variable of an LP
        # leaf.  In that rare case PACT's integer leaf certificate may
        # fail, so fall back to the unreduced decision.  Completeness is
        # preserved; the reduction is simply not used on this probe.
        wasted_lp = r.get('lp_solves', 0)
        wasted_nodes = r.get('nodes', 0)
        wasted_cert = r.get('cert_lp', 0)
        td = time.time()
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        policy=policy, seed=seed, forbid0=None,
                        timelimit=timelimit)
        r = dict(r)
        r['lp_solves'] = r.get('lp_solves', 0) + wasted_lp
        r['nodes'] = r.get('nodes', 0) + wasted_nodes
        r['cert_lp'] = r.get('cert_lp', 0) + wasted_cert
        base['fallback'] = True
        base['fallback_lp'] = wasted_lp
        base['decide_t'] += time.time() - td
    elif r['verdict'] is False:
        r = dict(r)
        r['proof'] = ReducedNOProof(inst, h, info.get('events', []),
                                    r['proof'],
                                    info.get('initial_empty'))
    r.update(base)
    r['t'] = time.time() - t0
    return r


def run_kicf(inst, known, name, idx, policy='lower-first', max_probes=64,
             use_pact_init=True, kernel_init=True, minimize_final=False,
             energy_mode='all', max_energy_checks=None, max_iters=None,
             initial=None, timelimit=None):
    """Run KICF on one instance and return a benchmark row."""
    t0 = time.time()
    if initial is not None:
        L, U, sched, mach, lb_proof = initial
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        co = None
    else:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
        if ub is None:
            return dict(name=name, idx=idx, known=known, policy=policy,
                        ok=False, error='no-initial-ub', t=0.0)
        L, U = int(lb), int(ub)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        lb_proof = co._ensure_lb_proof(L)
        if kernel_init:
            D, info = propagate(inst, L - 1, energy_mode=energy_mode,
                                max_energy_checks=max_energy_checks,
                                max_iters=max_iters)
            if D is None:
                lb_proof = EhcProof(inst, L - 1, info.get('events', []),
                                    info.get('initial_empty'))
        if lb_proof is None:
            r = kernel_decide(inst, L - 1, energy_mode=energy_mode,
                              max_energy_checks=max_energy_checks,
                              max_iters=max_iters)
            if r['verdict'] is False:
                lb_proof = r['proof']
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-lb-proof', t=0.0)

    probes = 0
    pact_lp = 0
    pact_nodes = 0
    pact_cert_lp = 0
    ehc_empty = 0
    ehc_removed = 0
    ehc_events = 0
    ehc_checks = 0
    ehc_time = 0.0
    fallback = 0
    fallback_lp = 0
    unknown = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    first = True
    lb0, ub0 = L, U

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        return pc

    audit_state()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = _choose_h(policy, L, U, first)
        r = kernel_decide(inst, h, energy_mode=energy_mode,
                          max_energy_checks=max_energy_checks,
                          max_iters=max_iters, timelimit=timelimit)
        probes += 1
        first = False
        pact_lp += r.get('lp_solves', 0)
        pact_nodes += r.get('nodes', 0)
        pact_cert_lp += r.get('cert_lp', 0)
        ehc_empty += 1 if r.get('ehc_empty') else 0
        ehc_removed += r.get('removed', 0)
        ehc_events += r.get('ehc_events', 0)
        ehc_checks += r.get('ehc_checks', 0)
        ehc_time += r.get('ehc_t', 0.0)
        fallback += 1 if r.get('fallback') else 0
        fallback_lp += r.get('fallback_lp', 0)

        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lb_proof = proof
            if co is not None:
                co._record_proof(proof)
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              ehc_empty=r.get('ehc_empty', False),
                              removed=r.get('removed', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              ehc_empty=False,
                              removed=r.get('removed', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            unknown += 1
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              ehc_empty=r.get('ehc_empty', False),
                              removed=r.get('removed', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
            break
        audit_state()

    final_events = None
    final_min_events = None
    if L == U and lb_proof is not None:
        final_events = len(getattr(lb_proof, 'events', ()) or ())
    if minimize_final and L == U and lb_proof is not None \
            and getattr(lb_proof, 'kind', '') == 'ehc2':
        ev = minimize_events(inst, U - 1, lb_proof.events,
                             getattr(lb_proof, 'initial_empty', None))
        final_min_events = len(ev)
        lb_proof = EhcProof(inst, U - 1, ev,
                            getattr(lb_proof, 'initial_empty', None))

    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_ok_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy,
        opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes,
        pact_lp=pact_lp, pact_nodes=pact_nodes,
        pact_cert_lp=pact_cert_lp,
        pin_lp=getattr(co, 'pin_lp', 0),
        ehc_empty=ehc_empty, ehc_removed=ehc_removed,
        ehc_events=ehc_events, ehc_checks=ehc_checks,
        ehc_time=round(ehc_time, 4), fallback=fallback,
        fallback_lp=fallback_lp,
        final_events=final_events, final_min_events=final_min_events,
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_ok_final,
        unknown=unknown, steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        total_audit=final_ok,
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_ok_final),
    )


def corpora():
    from icf import corpora as _c
    return _c()
