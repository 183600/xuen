"""v9.1 ICF-AID: ICF-PACT with an abstract-interpreted depth-first inner.

The outer state is still ICF's partial certificate

    (L, U, s, m, pi)

but the inner decision oracle is either

  * aida   : memoized interval-box DAG (exp/v9a/aida.py), or
  * aidf   : the live AID-Frontier from exp/v9ai/aidf.py.

Both inner searches are depth-first box refinements: tighten a box,
solve the restricted SDLP, and split on a fractional job.  The difference
is the proof object.  AIDA shares closed boxes through a DAG; AIDF keeps
the explicit DFS partition tree, so every intermediate state is a
frontier certificate with open leaves and local lower bounds.
"""
import sys
import time

sys.path[:0] = ['exp/v9ai', 'exp/v9a', 'exp/v8j', 'exp/v8u', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from icf import (PartialCertificate, ICFCertificate, cmax, corpora,
                 CertLeafProof)
from pact import PACT, pact_decide
from chip import chip_bounds
from sage import _domain
from aidf import search, LiftedFrontierProof
from aida import AIDA, aida_branch_decide, DEFAULT_POLICIES
from rdf import check_schedule


def choose_h(policy, L, U, first):
    if U - L <= 0:
        return L
    if policy == 'lower-first':
        return L if first else (L + U) // 2
    if policy == 'upper-first':
        return U - 1
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'pact':
        return L if U - L <= 4 else (L + U) // 2
    raise ValueError('unknown policy %r' % (policy,))


def _aida_call(inst, h, aida_kwargs):
    kw = dict(policies=DEFAULT_POLICIES, closure=True)
    kw.update(aida_kwargs or {})
    r = aida_branch_decide(inst, h, **kw)
    explicit_closure = bool(aida_kwargs and 'closure' in aida_kwargs)
    if r['verdict'] is None and not explicit_closure:
        # AIDA's production portfolio retries without precedence closure:
        # closure narrows the LP and can make the integral decoder fail on
        # a feasible box, while the wider box is often decoded directly.
        kw2 = dict(kw)
        kw2['closure'] = False
        r2 = aida_branch_decide(inst, h, **kw2)
        for k in ('nodes', 'leaves', 'lp_solves', 'cert_lp',
                  'memo_hits', 'sub_hits', 't'):
            if k in r2:
                r2[k] = r2.get(k, 0) + r.get(k, 0)
        r2['closure_fallback'] = True
        r2['first_attempt_lp'] = r.get('lp_solves', 0)
        return r2
    r['closure_fallback'] = False
    return r


def run_icf_aid(inst, known, name, idx, policy='lower-first',
                max_probes=64, inner='aida', budget=10000,
                aida_kwargs=None, init_engine='pact'):
    t0 = time.time()
    chip = None
    if init_engine == 'chip':
        chip = chip_bounds(inst)
        if not chip.get('ok') or chip.get('ub') is None:
            return dict(name=name, idx=idx, known=known, ok=False,
                        error='no-initial-ub', t=0.0)
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub = chip['lb'], chip['ub']
        sched, mach = chip['schedule'], chip['machine']
    else:
        if init_engine == 'aida':
            co = AIDA(inst, use_ga=False)
        else:
            co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-initial-ub', t=0.0)

    L, U = int(lb), int(ub)
    sched = list(sched) if sched is not None else None
    mach = list(mach) if mach is not None else None
    lb_proof = None
    if chip is not None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            lb_proof = r['proof']
    else:
        lb_proof = co._ensure_lb_proof(L)
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-lb-proof', t=0.0)

    probes = 0
    inner_lp = 0
    inner_nodes = 0
    inner_cert_lp = 0
    unknown = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    inner_stats = []
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
        h = choose_h(policy, L, U, first)
        if inner == 'aidf':
            s = search(inst, h, budget=budget)
            lp = s.stats['lp_solves']
            cert_lp = s.stats.get('cert_lp', 0)
            nodes = s.stats['nodes']
            verdict = s.verdict
            proof = s.proof() if verdict is False else None
            sch = (s.schedule, s.machine) if verdict is True else None
            inner_stats.append(dict(s.stats))
        else:
            r = _aida_call(inst, h, aida_kwargs)
            lp = r.get('lp_solves', 0)
            cert_lp = r.get('cert_lp', 0)
            nodes = r.get('nodes', 0)
            verdict = r['verdict']
            proof = r.get('proof')
            sch = ((r.get('schedule'), r.get('machine'))
                   if verdict is True else None)
        probes += 1
        first = False
        inner_lp += lp
        inner_nodes += nodes
        inner_cert_lp += cert_lp

        if verdict is False:
            L = h + 1
            lb_proof = proof
            steps.append(dict(h=h, v=False,
                              kind=getattr(proof, 'kind', None),
                              lp=lp, cert_lp=cert_lp, nodes=nodes,
                              L0=L0, U0=U0, L1=L, U1=U))
        elif verdict is True:
            s2, m2 = sch
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2, lp=lp,
                              cert_lp=cert_lp, nodes=nodes,
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            unknown += 1
            lifted = False
            if inner == 'aidf':
                Lnew = max(L, s.local_L())
                if Lnew > L:
                    lp2 = LiftedFrontierProof(inst, Lnew - 1, h, s.tree)
                    if lp2.audit_rdf():
                        L = Lnew
                        lb_proof = lp2
                        lifted = True
            steps.append(dict(h=h, v=None, lp=lp, cert_lp=cert_lp,
                              nodes=nodes, L0=L0, U0=U0, L1=L,
                              U1=U, lifted=lifted))
            break
        audit_state()

    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_ok_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy, inner=inner,
        opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes,
        inner_lp=inner_lp, inner_nodes=inner_nodes,
        inner_cert_lp=inner_cert_lp,
        pin_lp=getattr(co, 'pin_lp', 0),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_ok_final,
        unknown=unknown, steps=steps, inner_stats=inner_stats,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_ok_final),
    )
