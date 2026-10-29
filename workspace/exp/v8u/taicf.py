"""v9.1 TA-ICF: threshold-anchored invariant-carrying frontier.

v9.0 ICF keeps a certified bracket

    C = (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s)=U,  L<=U,

and closes the bracket with probes.  This module adds a cheap prescan
that anchors the bracket at the LP value function

    h* = min { h : P(h) is feasible },

where P(h) is the start-time SD LP at horizon h.  The prescan is a
parametric binary search: one matrix at T=U, different variable bounds.
It returns a Farkas proof of NO(h*-1), hence a *certified* lower bound.
The outer ICF invariant is unchanged.  The only new transition is

    ANCHOR:  (L, U, pi)  ->  (h*, U, pi*)     with h* >= L.

After ANCHOR the residual gap is OPT - h*, the SD-LP integrality gap.
On the 252-instance corpus and the 160-instance weak corpus this gap is
0 or 1, so the ICF loop needs at most two probes.

A second oracle, SAT-ICF, replaces the first YES probe by a time-indexed
SAT model.  A SAT model is a schedule and is checked by check_schedule;
an UNSAT answer only says "no integer schedule", and is *not* accepted as
a certificate.  The NO side always comes from PACT/LP Farkas proofs, so
the certificate language is unchanged.
"""
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import PartialCertificate, ICFCertificate, cmax, _choose_h
from pact import pact_decide
from lbp import ParametricSD, farkas_bounds
from po import heads_tails
from rdf import check_schedule
from cert import verify


def _sat_schedule(inst, h, forbid=None, solver='glucose'):
    """Time-indexed SAT encoding of fixed-h scheduling.

    Returns dict(verdict, starts, machines, cmax, vars, clauses, t).
    The encoding is only a primal oracle: an UNSAT answer is not a proof.
    """
    from pysat.solvers import Glucose3, Cadical153
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    forbid = set(forbid or ())
    var = {}
    top = 0
    clauses = []
    by_task = [[] for _ in range(n)]
    covers = [[[] for _ in range(max(h, 0))] for _ in range(m)]
    for i in range(n):
        for k in inst['elig'][i]:
            lo = est[i]
            hi = h - q[i] - p[i]
            for t in range(lo, hi + 1):
                if (i, t) in forbid:
                    continue
                top += 1
                var[(i, k, t)] = top
                by_task[i].append(top)
                for u in range(t, min(t + p[i], h)):
                    covers[k][u].append(top)
    for i in range(n):
        lits = by_task[i]
        if not lits:
            return dict(verdict=False, why='empty', vars=top, t=time.time() - t0)
        clauses.append(lits[:])
        for a in range(len(lits)):
            for b in range(a + 1, len(lits)):
                clauses.append([-lits[a], -lits[b]])
    for k in range(m):
        for u in range(h):
            lits = covers[k][u]
            if len(lits) > 1:
                for a in range(len(lits)):
                    for b in range(a + 1, len(lits)):
                        clauses.append([-lits[a], -lits[b]])
    for i in range(n):
        for j in inst['succ'][i]:
            for (ii, ki, ti), vi in var.items():
                if ii != i:
                    continue
                for (jj, kj, tj), vj in var.items():
                    if jj != j:
                        continue
                    if ti + p[i] > tj:
                        clauses.append([-vi, -vj])
    s = (Cadical153 if solver == 'cadical' else Glucose3)(
        bootstrap_with=clauses)
    ok = s.solve()
    stats = dict(vars=top, clauses=len(clauses), t=time.time() - t0)
    if not ok:
        s.delete()
        stats.update(verdict=False, why='unsat')
        return stats
    model = s.get_model()
    s.delete()
    true = set(x for x in model if x > 0)
    starts = [None] * n
    mach = [None] * n
    for (i, k, t), v in var.items():
        if v in true:
            starts[i] = t
            mach[i] = k
    good = (all(x is not None for x in starts)
            and check_schedule(inst, h, starts, mach))
    stats.update(verdict=bool(good), starts=starts, machines=mach,
                 cmax=(max(starts[i] + p[i] for i in range(n))
                       if good else None))
    return stats



class FarkasPin:
    """A fixed-h LP Farkas certificate used as the ICF lower-bound proof."""

    kind = 'pin'

    def __init__(self, inst, h, cert):
        self.inst = inst
        self.h = int(h)
        self.cert = cert

    def audit_rdf(self):
        try:
            return bool(self.cert is not None
                        and verify(self.inst, self.h, self.cert))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def threshold_anchor(inst, L, U, T=None):
    """Parametric LP threshold plus a Farkas certificate at h*-1.

    Returns dict(h, cert, solves, ok, last_bad).  The certificate is built
    from the *same* parametric matrix, so no second SDLP is constructed.
    """
    if T is None:
        T = U
    ps = ParametricSD(inst, T)
    lo, hi = int(L), int(U)
    last_bad = None
    solves = 0
    ok = True
    while lo < hi:
        mid = (lo + hi) // 2
        bounds = ps.bounds_h(mid)
        res = ps.solve_h(mid)
        solves += 1
        if res.status == 0:
            hi = mid
        elif res.status == 2:
            lo = mid + 1
            last_bad = (mid, bounds)
        else:
            ok = False
            break
    cert = None
    if ok and lo > L and last_bad is not None and last_bad[0] == lo - 1:
        c = farkas_bounds(ps.lp, last_bad[0], last_bad[1])
        if c is not None and verify(inst, last_bad[0], c):
            cert = c
            solves += 1
        else:
            ok = False
    return dict(h=lo, cert=cert, solves=solves, ok=ok,
                last_bad=(None if last_bad is None else last_bad[0]))


def _farkas_proof(inst, h):
    """A one-leaf NO(h) proof when the SD LP at h is infeasible."""
    if h < 0:
        return None
    r = pact_decide(inst, h, depthcap=0, nodecap=None)
    if r['verdict'] is False:
        return r['proof'], r.get('lp_solves', 0), r.get('cert_lp', 0)
    return None, r.get('lp_solves', 0), r.get('cert_lp', 0)


def run_taicf(inst, known, name, idx, init, policy='lower-first',
              max_probes=64, sat_first=False, sat_solver='glucose',
              audit=True, prescan_min_gap=0, prescan_max_gap=None,
              l_probes=2):
    """Run threshold-anchored ICF.

    ``init`` is (L, U, schedule, machine, lb_proof) from either the weak
    or the full PACT initializer.  Returns a benchmark row with the same
    fields as run_icf, plus prescan statistics.
    """
    t0 = time.time()
    L, U, sched, mach, lb_proof = init
    L, U = int(L), int(U)
    sched = list(sched) if sched is not None else None
    mach = list(mach) if mach is not None else None
    lb0, ub0 = L, U
    prescan_lp = 0
    prescan_h = L
    prescan_moved = 0
    prescan_ok = False
    anchor_proof_lp = 0
    anchor_cert_lp = 0

    gap0 = U - L
    do_prescan = (L < U and gap0 >= prescan_min_gap
                  and (prescan_max_gap is None or gap0 <= prescan_max_gap))
    if do_prescan:
        r = threshold_anchor(inst, L, U, T=U)
        prescan_lp = r.get('solves', 0)
        if r.get('ok'):
            h = int(r['h'])
            if h > U:
                h = U
            if h > L:
                c = r.get('cert')
                p = (FarkasPin(inst, h - 1, c)
                     if c is not None else None)
                if p is not None and p.h == h - 1 and p.audit_rdf():
                    L = h
                    lb_proof = p
                    prescan_moved = 1
                    anchor_cert_lp += 1
                    prescan_ok = True
                else:
                    pp, plp, pclp = _farkas_proof(inst, h - 1)
                    if (pp is not None and pp.h == h - 1
                            and pp.audit_rdf()):
                        L = h
                        lb_proof = pp
                        prescan_moved = 1
                        anchor_proof_lp += plp
                        anchor_cert_lp += pclp
                        prescan_ok = True
            else:
                prescan_ok = True
        prescan_h = L
    else:
        prescan_h = L

    probes = 0
    sat_calls = 0
    sat_yes = 0
    sat_time = 0.0
    pact_lp = 0
    pact_nodes = 0
    pact_cert_lp = 0
    unknown = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    first = True

    def audit_state():
        nonlocal partial_ok, partial_fail
        if not audit:
            return None
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        return pc

    audit_state()
    while L < U and probes < max_probes:
        if policy == 'anchor':
            if prescan_ok and probes < l_probes:
                h = L
            else:
                h = L if (U - L <= 2 or first) else (L + U) // 2
        else:
            h = _choose_h(policy, L, U, first)
        did_sat = False
        if sat_first and h == L:
            sr = _sat_schedule(inst, h, solver=sat_solver)
            sat_calls += 1
            sat_time += sr.get('t', 0.0)
            did_sat = True
            if sr['verdict'] is True:
                s2, m2 = sr['starts'], sr['machines']
                c2 = cmax(inst, s2)
                if c2 <= U and check_schedule(inst, h, s2, m2):
                    U = c2
                    sched, mach = list(s2), list(m2)
                    sat_yes += 1
                    probes += 1
                    steps.append(dict(h=h, v=True, cmax=c2, oracle='sat',
                                      L0=L, U0=U))
                    audit_state()
                    first = False
                    continue
            # UNSAT or invalid model: fall back to PACT for a NO proof
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        pact_lp += r.get('lp_solves', 0)
        pact_nodes += r.get('nodes', 0)
        pact_cert_lp += r.get('cert_lp', 0)
        L0, U0 = L, U
        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lb_proof = proof
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              oracle=('sat-fallback' if did_sat else 'pact'),
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2, oracle='pact',
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            unknown += 1
            steps.append(dict(h=h, v=None, oracle='pact',
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
            break
        audit_state()

    final = (ICFCertificate(inst, U, sched, mach, lb_proof)
             if L == U else None)
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_final = bool(partial.audit_rdf())
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
        pin_lp=0, prescan_lp=prescan_lp, prescan_h=prescan_h,
        prescan_moved=prescan_moved, prescan_ok=prescan_ok,
        anchor_proof_lp=anchor_proof_lp,
        anchor_cert_lp=anchor_cert_lp,
        sat_calls=sat_calls, sat_yes=sat_yes, sat_time=round(sat_time, 4),
        sat_first=sat_first,
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final,
        unknown=unknown, steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        total_audit=final_ok,
        t=round(dt, 4),
        schedule=list(sched) if sched is not None else None,
        machine=list(mach) if mach is not None else None,
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final),
    )
