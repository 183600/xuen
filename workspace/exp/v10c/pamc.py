"""PAMC: Pareto-Amortized Monte-Carlo certifier for fixed-h scheduling.

This is a direct extension of v9.0 ICF-PACT.  The state is

    (L, U, s, m, pi, A, kappa)

where (L,U,s,m,pi) is the ICF partial certificate, A is a verified
Pareto archive of schedules non-dominated in (Cmax, total completion),
and kappa is a sample credit account.

The probe horizon is a quantile of the open bracket:

    h = L + round(q * (U - L - 1)),   0 < q < 1.

At h we first try a randomized primal probe (LP distribution sampling,
greedy list scheduling, LP integral point, archive hits).  Only a
schedule checked by check_schedule can lower U.  If the primal probe
fails, we call the exact three-valued PACT decider on the same root LP.
A NO proof can raise L; a YES schedule can lower U; UNKNOWN leaves the
state unchanged.

Every sample consumes one unit of credit.  Credit starts at gamma*g0
and is recharged by gamma times every bracket reduction.  Since the
bracket can shrink at most 2*g0 in total, the number of samples over a
run is at most 3*gamma*g0.  This is the amortized part; it is a hard
runtime cap, not an assumption about distributions.

The randomized part has one-sided error in the certificate sense: a
failure to find a schedule is never interpreted as NO.  Thus the output
is always a valid partial certificate, or an optimality certificate when
L=U, independent of the random outcomes.  Randomness changes only how
much work is done before the exact fallback.
"""
import sys
import math
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide
from icf import (PartialCertificate, ICFCertificate, cmax, corpora)
from chip import base_bounds
from ptb import ParetoArchive, primal_probe, exact_with_root
from rdf import check_schedule


def init_strong(inst):
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        return None
    lb_proof = co._ensure_lb_proof(int(lb))
    if lb_proof is None:
        r = pact_decide(inst, int(lb) - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            lb_proof = r['proof']
    if lb_proof is None:
        return None
    return (int(lb), int(ub), list(sched), list(mach), lb_proof,
            getattr(co, 'pin_lp', 0))


def init_weak(inst):
    lb, ub, sched, mach, est, q = base_bounds(inst)
    co = PACT(inst, use_lp=False, use_lns=False, use_lp_sched=False,
              pact_mode='complete', use_ga=False)
    proof = co._ensure_lb_proof(lb)
    if proof is None:
        r = pact_decide(inst, lb - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    if proof is None:
        return None
    return (int(lb), int(ub), list(sched), list(mach), proof, 0)


def _horizon(L, U, q):
    """Interior quantile of the open bracket, clamped to [L, U-1]."""
    g = U - L
    if g <= 1:
        return L
    return min(U - 1, max(L, L + int(round(q * (g - 1)))))


def _sample_budget(gap, alpha, credit, kmin=4, kmax=48):
    k = max(kmin, int(math.ceil(alpha * gap)))
    k = min(kmax, k)
    if credit is not None:
        k = min(k, int(math.floor(credit)))
    return max(0, k)


def run_pamc(inst, known, name, idx, initial=None, q=0.8, alpha=8.0,
             gamma=8.0, samples_cap=48, max_probes=64, seed=0,
             credit_mode='cumulative', pareto=True, harvest=True,
             max_rounds=256, q_first=None, k_first=None):
    """Run PAMC and return a benchmark row.

    initial: (L,U,sched,mach,lb_proof,pin_lp) or None for the strong
    PACT initialization.
    credit_mode='cumulative' is the amortized account; 'reset' only
    uses alpha*gap as a per-round budget (useful ablation).
    """
    t0 = time.time()
    if initial is None:
        initial = init_strong(inst)
    if initial is None:
        return dict(name=name, idx=idx, known=known, policy='pamc',
                    ok=False, error='no-initial-state', t=0.0)
    L, U, sched, mach, lb_proof, pin_lp = initial
    L, U = int(L), int(U)
    sched = list(sched) if sched is not None else None
    mach = list(mach) if mach is not None else None
    if sched is None or mach is None or lb_proof is None:
        return dict(name=name, idx=idx, known=known, policy='pamc',
                    ok=False, error='bad-initial-state', t=0.0)

    archive = ParetoArchive(inst, pareto=pareto)
    archive.add(sched, mach, 'initial', U)
    L0, U0 = L, U
    g0 = U - L
    credit = (gamma * g0 + (int(k_first) if k_first is not None else 0)
              if credit_mode == 'cumulative' else None)

    probes = 0
    primal_calls = 0
    primal_lp = 0
    primal_samples = 0
    success_samples = []
    primal_yes = 0
    primal_no_root = 0
    primal_fail = 0
    archive_drops = 0
    archive_hits = 0
    integral_yes = 0
    greedy_yes = 0
    repair_yes = 0
    pact_lp = 0
    pact_nodes = 0
    pact_cert_lp = 0
    unknown_heights = set()
    partial_ok = 0
    partial_fail = 0
    rounds = 0
    rounds_since = 0
    steps = []

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    def recharge(dL, dU):
        nonlocal credit
        if credit is not None:
            credit += gamma * (dL + dU)

    def absorb_exact(rr):
        nonlocal U, sched, mach
        if rr['verdict'] is True:
            s2, m2 = rr['schedule'], rr['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                archive.add(s2, m2, 'exact', c2)
                dU = U - c2
                U = c2
                sched, mach = list(s2), list(m2)
                recharge(0, dU)
                return True
        return False

    audit_state()
    while L < U and probes < max_probes and rounds < max_rounds:
        b = archive.best()
        if b is not None and b[0] < U:
            dU = U - b[0]
            U = b[0]
            sched = list(b[1])
            mach = list(b[2])
            archive_drops += 1
            recharge(0, dU)
        if L >= U:
            break
        gap = U - L
        q_use = q if (q_first is None or rounds > 0) else q_first
        h = _horizon(L, U, q_use)
        if h in unknown_heights:
            cand = [t for t in range(L, U) if t not in unknown_heights]
            if not cand:
                break
            h = cand[len(cand) // 2]
        if rounds == 0 and k_first is not None:
            k = min(int(k_first), int(math.floor(credit)) if credit is not None else int(k_first))
            k = max(0, k)
        else:
            k = _sample_budget(gap, alpha, credit)
        rounds += 1
        rounds_since += 1
        primal = None
        if k > 0:
            primal = primal_probe(inst, h, archive, samples=k,
                                  repairs=0, kmax=14,
                                  seed=seed + probes,
                                  harvest=harvest)
            primal_calls += 1
            used = int(primal['stats'].get('samples', 0))
            primal_samples += used
            primal_lp += primal['stats']['lp']
            if credit is not None:
                credit -= used
            if primal['kind'] == 'yes':
                primal_yes += 1
                success_samples.append(used)
                if primal['stats'].get('archive_hit'):
                    archive_hits += 1
                if primal['stats'].get('integral_yes'):
                    integral_yes += 1
                if primal['stats'].get('greedy_yes'):
                    greedy_yes += 1
                if primal['stats'].get('repair_yes'):
                    repair_yes += 1
                s2, m2 = primal['schedule'], primal['machine']
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    archive.add(s2, m2, 'primal', c2)
                    dU = U - c2
                    U = c2
                    sched, mach = list(s2), list(m2)
                    recharge(0, dU)
                steps.append(dict(h=h, action='primal', v=True,
                                  cmax=c2, L1=L, U1=U,
                                  samples=used, k=k))
                audit_state()
                continue
            if primal['kind'] == 'no_root':
                primal_no_root += 1
                rr = exact_with_root(inst, h, primal['lp'],
                                     primal['res'])
                probes += 1
                pact_lp += rr.get('lp_solves', 0)
                pact_nodes += rr.get('nodes', 0)
                pact_cert_lp += rr.get('cert_lp', 0)
                if rr['verdict'] is False:
                    dL = h + 1 - L
                    L = h + 1
                    lb_proof = rr['proof']
                    recharge(dL, 0)
                elif rr['verdict'] is True:
                    absorb_exact(rr)
                else:
                    unknown_heights.add(h)
                steps.append(dict(h=h, action='root', v=rr['verdict'],
                                  lp=rr.get('lp_solves', 0),
                                  L1=L, U1=U))
                audit_state()
                continue
            primal_fail += 1
        # Exact fallback, sharing the root LP when one was built.
        if primal is not None and primal.get('lp') is not None:
            rr = exact_with_root(inst, h, primal['lp'], primal['res'])
        else:
            rr = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        pact_lp += rr.get('lp_solves', 0)
        pact_nodes += rr.get('nodes', 0)
        pact_cert_lp += rr.get('cert_lp', 0)
        if rr['verdict'] is False:
            dL = h + 1 - L
            L = h + 1
            lb_proof = rr['proof']
            recharge(dL, 0)
        elif rr['verdict'] is True:
            absorb_exact(rr)
        else:
            unknown_heights.add(h)
        steps.append(dict(h=h, action='exact', v=rr['verdict'],
                          lp=rr.get('lp_solves', 0),
                          L1=L, U1=U))
        audit_state()

    b = archive.best()
    if b is not None and b[0] < U:
        U = b[0]
        sched = list(b[1])
        mach = list(b[2])
        archive_drops += 1
    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy='pamc', q=q,
        alpha=alpha, gamma=gamma, credit=(credit if credit is not None
                                          else None),
        opt=U, lb=L, lb0=L0, ub0=U0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        probes=probes, queries=probes,
        primal_calls=primal_calls, primal_lp=primal_lp,
        primal_samples=primal_samples,
        primal_yes=primal_yes, primal_no_root=primal_no_root,
        primal_fail=primal_fail,
        archive_drops=archive_drops, archive_hits=archive_hits,
        integral_yes=integral_yes, greedy_yes=greedy_yes,
        repair_yes=repair_yes,
        pact_lp=pact_lp, pact_nodes=pact_nodes,
        pact_cert_lp=pact_cert_lp,
        total_lp=primal_lp + pact_lp + pact_cert_lp,
        pin_lp=pin_lp,
        archive=len(archive.items), archive_audit=archive.audit(),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final,
        unknown=len(unknown_heights), steps=steps,
        success_samples=success_samples,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final and
                archive.audit()),
    )
