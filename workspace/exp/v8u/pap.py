"""v9.1 PAP-ICF: provenance-aware probe planning with certified plans.

PAP keeps the v9.0 ICF state and invariant

    C = (L, U, s, m, pi),  pi : NO(L-1), Cmax(s)=U, L<=U,

and adds a *certified probe plan* P to the state.  P is a minimax
decision tree over the bracket [L,U]:

    V(a,b) = min_h max( cY(h) + V(a,h),
                        cN(h) + V(h+1,b) ),      V(a,a)=0.

Every internal node stores its probe height h, its value V(a,b), and the
two child plans.  The plan is optimal for the declared cost model; it is
not trusted as a correctness certificate.  The ICF certificate (pi and
s) remains the only trusted object.

Policies:
  lower-first : first probe L, then binary on the rest.
  minimax     : unit costs cN=cY=1 (height-optimal).
  cost        : cN(h)=1+lam*(h-L)/G, cY(h)=1+lam*(U-h)/G.
  upper-first : probe U-1 (linear scan; kept as a foil).
"""
import sys
import math
import time
import json

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import (PartialCertificate, ICFCertificate, cmax, corpora)
from pact import PACT, pact_decide
from rdf import check_schedule

INF = 1e18


def _costs(L, U, mode, lam=2.0, pin=None):
    G = max(1, U - L)
    pin = L if pin is None else max(L, min(U, pin))
    if mode == 'minimax':
        return {h: 1.0 for h in range(L, U)}, {h: 1.0 for h in range(L, U)}
    if mode == 'cost':
        return ({h: 1.0 + lam * (h - L) / G for h in range(L, U)},
                {h: 1.0 + lam * (U - h) / G for h in range(L, U)})
    if mode == 'pin':
        return ({h: 1.0 + lam * max(0, h - pin) / G for h in range(L, U)},
                {h: 1.0 + lam * max(0, pin - h) / G for h in range(L, U)})
    raise ValueError(mode)


def build_plan(L, U, mode='minimax', lam=2.0, pin=None):
    """Return (act, value, cN, cY) for the minimax probe DP."""
    if U <= L:
        return {(L, L): L}, {(L, L): 0.0}, {}, {}
    cN, cY = _costs(L, U, mode, lam, pin)
    act, val = {}, {}
    for g in range(0, U - L + 1):
        for a in range(L, U - g + 1):
            b = a + g
            if g == 0:
                act[(a, b)] = a
                val[(a, b)] = 0.0
                continue
            best = INF
            bh = a
            for h in range(a, b):
                z = max(cY[h] + val[(a, h)],
                        cN[h] + val[(h + 1, b)])
                if z < best:
                    best = z
                    bh = h
            act[(a, b)] = bh
            val[(a, b)] = best
    return act, val, cN, cY


def audit_plan(L, U, act, val, mode='minimax', lam=2.0, pin=None):
    """Recompute the Bellman table and check every stored action/value."""
    act2, val2, _, _ = build_plan(L, U, mode, lam, pin)
    if set(act2) != set(act) or set(val2) != set(val):
        return False
    for key in act2:
        if act[key] != act2[key]:
            return False
        if abs(val[key] - val2[key]) > 1e-9:
            return False
    return True


def _choose_h(policy, L, U, first, plan=None):
    if U - L <= 0:
        return L
    if policy == 'lower-first':
        return L if first else (L + U) // 2
    if policy == 'upper-first':
        return U - 1
    if policy == 'binary':
        return (L + U) // 2
    if policy in ('minimax', 'cost', 'pin'):
        if plan is None:
            act, _, _, _ = build_plan(L, U, policy)
            return act[(L, U)]
        return plan[(L, U)]
    raise ValueError(policy)


def shift_schedule(inst, sched, delta):
    return [int(s) + int(delta) for s in sched]


def run_pap(inst, known, name, idx, policy='lower-first', max_probes=256,
            lam=2.0, plan_mode=None, initial=None, pin=None):
    t0 = time.time()
    co = PACT(inst, pact_mode='complete', use_ga=False)
    if initial is None:
        lb, ub, sched, mach = co.initial_bounds()
        if ub is None:
            return dict(name=name, idx=idx, known=known, policy=policy,
                        ok=False, error='no-initial-ub', t=0.0)
        L, U = int(lb), int(ub)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        lb_proof = co._ensure_lb_proof(L)
        if lb_proof is None:
            r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r['verdict'] is False:
                lb_proof = r['proof']
    else:
        L, U, sched, mach, lb_proof = initial
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-lb-proof', t=0.0)

    mode = plan_mode or ('cost' if policy == 'cost' else
                         'pin' if policy == 'pin' else 'minimax')
    pin0 = L if pin is None else max(L, min(U, int(pin)))
    plan = None
    plan_fail = 0
    if policy in ('minimax', 'cost', 'pin'):
        plan, pval, _, _ = build_plan(L, U, mode, lam, pin0)
        if not audit_plan(L, U, plan, pval, mode, lam, pin0):
            plan_fail += 1

    probes = 0
    pact_lp = 0
    pact_nodes = 0
    pact_cert_lp = 0
    unknown = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    first = True
    lb0, ub0 = L, U

    def audit_state():
        nonlocal partial_ok, partial_fail, plan_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        if policy in ('minimax', 'cost', 'pin') and L < U:
            a2, v2, _, _ = build_plan(L, U, mode, lam, pin0)
            if not audit_plan(L, U, a2, v2, mode, lam, pin0):
                plan_fail += 1

    audit_state()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        if policy in ('minimax', 'cost', 'pin'):
            plan, _, _, _ = build_plan(L, U, mode, lam, pin0)
            h = plan[(L, U)]
        else:
            h = _choose_h(policy, L, U, first)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        pact_lp += r.get('lp_solves', 0)
        pact_nodes += r.get('nodes', 0)
        pact_cert_lp += r.get('cert_lp', 0)

        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lb_proof = proof
            co._record_proof(proof)
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
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
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            unknown += 1
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
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
        name=name, idx=idx, known=known, policy=policy, pin=pin0,
        opt=U, lb=L, lb0=lb0, ub0=ub0, gap0=ub0 - lb0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        queries=probes, probes=probes,
        pact_lp=pact_lp, pact_nodes=pact_nodes,
        pact_cert_lp=pact_cert_lp,
        pin_lp=getattr(co, 'pin_lp', 0),
        partial_ok=partial_ok, partial_fail=partial_fail,
        plan_fail=plan_fail,
        partial_final=partial_ok_final,
        unknown=unknown, steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and plan_fail == 0 and
                partial_ok_final),
    )


def worst_case_probes(G, policy):
    """Exact worst-case probes; G = U-L, optima in {L,...,U}."""
    if G <= 0:
        return 0
    if policy == 'lower-first':
        return 1 + int(math.ceil(math.log2(G)))
    if policy == 'binary':
        return int(math.ceil(math.log2(G + 1)))
    if policy == 'upper-first':
        return G
    if policy == 'minimax-unit':
        act, _, _, _ = build_plan(0, G, 'minimax')
        memo = {}

        def w(a, b):
            if a >= b:
                return 0
            if (a, b) not in memo:
                h = act[(a, b)]
                memo[(a, b)] = 1 + max(w(a, h), w(h + 1, b))
            return memo[(a, b)]

        return w(0, G)
    raise ValueError(policy)


def worst_case_cost(G, mode='pin', lam=2.0, pin=0):
    """DP value: worst-case model cost, not probe count."""
    if G <= 0:
        return 0.0
    _, val, _, _ = build_plan(0, G, mode, lam, pin)
    return val[(0, G)]


if __name__ == '__main__':
    for G in (2, 3, 4, 5, 8, 16, 32, 64):
        print('G', G, {p: worst_case_probes(G, p)
                       for p in ('lower-first', 'binary', 'upper-first',
                                 'minimax-unit')},
              'pin-cost', worst_case_cost(G, 'pin', 2.0, 0))
