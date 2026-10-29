"""v9.1 PACE-PACT: P-class / Approximation / Exact trichotomy.

PACE keeps the v9.0 ICF bracket

    L <= OPT <= U,   pi : NO(L-1),   (s,m) feasible with Cmax(s)=U,

and adds two polynomial-time front layers plus one stopping rule:

  P-layer  (P-class): critical-path / work / interval-energy bounds from
           chip_bounds, and the start-time LP value function L*.  If the
           LP at L* is integral, its vertex decodes to a schedule of
           length L*, so the instance is closed exactly in polynomial
           time (given the LP lower-bound proof).

  A-layer  (approximation): if U <= (1+eps) L, the same state is a
           certified (1+eps)-approximation.  The ratio is checked on the
           state, not assumed from a heuristic.

  X-layer  (exact search): if neither P nor A closes the state, run the
           v9.0 ICF lower-first loop with the complete PACT decision
           oracle.  The loop may stop at the A-gate (mode='approx') or
           only at L=U (mode='exact').

Every state still carries the ICF partial certificate.  The new object is
a *regime* annotation: P (exact, polynomial witness), A (ratio), X
(exact search), or B (budget-exhausted bracket).  The audit does not
trust the annotation: P/A/X all replay pi and check_schedule.
"""
import sys
import time
import collections

sys.path[:0] = ['exp/v9pa', 'exp/v8b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof, BoundProof, EnergyProof, FarkasProof, bound_lb
from chip import chip_bounds
from lbp import lp_threshold, lp_schedule, cp_cert, farkas_bounds
from pact import PACT, pact_decide
from sage import _elig_aware, _domain
from sdecc import SDLP
from po import heads_tails
from cert import verify, integer_certificate
from rdf import check_schedule
from scl import sgs_greedy
from icf import cmax, PartialCertificate, ICFCertificate


# --------------------------------------------------------------- helpers
def _lp_priority_sgs(inst, pin, h):
    """Polynomial-time primal heuristic: LP-mean-start priority SGS.

    The LP vertex may be fractional; its expected start time is a
    precedence-independent priority.  sgs_greedy is a serial SGS that
    respects precedence and eligibility, so the output is a feasible
    schedule.  This is a heuristic upper bound, never a certificate.
    """
    if pin is None or not pin.get('ok') or pin.get('param') is None:
        return None
    ps = pin['param']
    try:
        if pin.get('last_h') == h and pin.get('last_res') is not None:
            res = pin['last_res']
        else:
            res = ps.solve_h(h)
        z = res.x
        n = inst['n']
        mass = [0.0] * n
        total = [0.0] * n
        for c, key in enumerate(ps.cols):
            i, t = key[0], key[-1]
            v = z[c]
            if v > 1e-9:
                mass[i] += t * v
                total[i] += v
        rank = {}
        for i in range(n):
            rank[i] = (mass[i] / total[i]) if total[i] > 1e-9 else 0.0
        got = sgs_greedy(inst, rank)
        if got is None:
            return None
        s, m, c = got
        if c <= h and check_schedule(inst, c, s, m):
            return s, m, c
        return None
    except Exception:
        return None


def _lp_no_proof(inst, h, pin):
    """A replayable NO(h) proof from the P-layer, or None."""
    c = cp_cert(inst, h)
    if c is not None:
        p = FarkasProof(inst, h, c)
        if p.audit_rdf():
            return p
    if pin is not None and pin.get('ok') and pin.get('param') is not None:
        ps = pin['param']
        try:
            c = farkas_bounds(ps.lp, h, ps.bounds_h(h))
        except Exception:
            c = None
        if c is not None:
            p = FarkasProof(inst, h, c)
            if p.audit_rdf():
                return p
    try:
        c = integer_certificate(inst, h, use_dom=True,
                                elig_aware=_elig_aware(inst))
    except Exception:
        c = None
    if c is not None:
        p = FarkasProof(inst, h, c)
        if p.audit_rdf():
            return p
    return None


def _get_lb_proof(inst, L, chip, pin, co):
    """Proof of NO(L-1), reusing chip certificates first."""
    h = int(L) - 1
    if h < 0:
        return None
    # chip certificates are recorded at every lifted horizon
    for hh, cert in chip.get('certs', []):
        if hh == h:
            p = EnergyProof(inst, h, cert)
            if p.audit_rdf():
                co._record_proof(p)
                return p
    if L == bound_lb(inst):
        p = BoundProof(inst, h, L)
        if p.audit_rdf():
            co._record_proof(p)
            return p
    p = _lp_no_proof(inst, h, pin)
    if p is not None:
        co._record_proof(p)
        return p
    # Last resort: ask the complete oracle.  This is not polynomial, but
    # it only happens if every P-layer proof fails to replay.
    r = pact_decide(inst, h, depthcap=None, nodecap=None)
    if r['verdict'] is False and r.get('proof') is not None:
        co._record_proof(r['proof'])
        return r['proof']
    return None


# --------------------------------------------------------------- state
class PACECertificate:
    """A certified bracket with a regime tag.

    regime:
      'P'  exact, polynomial witness (chip or integral LP)
      'A'  (1+eps)-approximate; U <= (1+eps)L
      'X'  exact after ICF search
      'B'  partial bracket (budget/unknown)
    """

    kind = 'pace-cert'

    def __init__(self, inst, L, U, schedule, machine, lb_proof,
                 regime, eps=0.1, stage='', probes=0):
        self.inst = inst
        self.L = int(L)
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.lb_proof = lb_proof
        self.regime = regime
        self.eps = float(eps)
        self.stage = stage
        self.probes = int(probes)

    def _sched_ok(self):
        if self.schedule is None or self.machine is None:
            return False
        c = cmax(self.inst, self.schedule)
        if c != self.U:
            return False
        return bool(check_schedule(self.inst, c, self.schedule,
                                   self.machine))

    def audit_rdf(self):
        try:
            if self.lb_proof is None:
                return False
            if self.lb_proof.h != self.L - 1:
                return False
            if not self.lb_proof.audit_rdf():
                return False
            if self.L > self.U:
                return False
            if not self._sched_ok():
                return False
            if self.regime == 'P' and self.L != self.U:
                return False
            if self.regime == 'X' and self.L != self.U:
                return False
            if self.regime in ('P', 'X'):
                return True
            if self.regime == 'A':
                return self.U <= (1.0 + self.eps) * self.L + 1e-12
            if self.regime == 'B':
                return True
            return False
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------------------- P/A layer
def pace_bounds(inst, eps=0.1, stop_at_approx=True):
    """Polynomial-time P/A preprocessing.  Returns a dict with stages.

    stop_at_approx=False is used by exact mode: a ratio certificate is
    still recorded, but the LP pin and the exact search are allowed to
    continue.  This keeps the P/A layer and the exact layer comparable
    on the same initial bracket.
    """
    b = chip_bounds(inst)
    out = dict(chip=b, chip_lb=b.get('lb'), chip_ub=b.get('ub'),
               chip_gap=(b.get('ub') - b.get('lb')
                         if b.get('ub') is not None else None),
               stage='chip', pin=None, lp_lb=None, lp_ub=None,
               lp_exact=False, lp_sched=False)
    if not b.get('ok') or b.get('ub') is None:
        return out
    L, U = int(b['lb']), int(b['ub'])
    s, m = b['schedule'], b['machine']
    if L == U:
        out.update(stage='chip-exact', L=L, U=U, schedule=s, machine=m)
        return out
    if stop_at_approx and U <= (1.0 + eps) * L + 1e-12:
        out.update(stage='chip-approx', L=L, U=U, schedule=s, machine=m)
        return out

    # LP value function: polynomial number of LP solves.
    try:
        pin = lp_threshold(inst, L, U, T=U)
    except Exception:
        pin = dict(ok=False)
    out['pin'] = pin
    if pin.get('ok') and pin.get('lb') is not None:
        L2 = max(L, int(pin['lb']))
        # An integral LP at L2 is a polynomial exact witness.
        got = None
        if pin.get('last_h') == L2 and pin.get('last_res') is not None:
            got = lp_schedule(pin['param'], inst, L2,
                              res=pin['last_res'])
        if got is None:
            try:
                got = lp_schedule(pin['param'], inst, L2)
            except Exception:
                got = None
        if got is not None:
            s2, m2 = got
            c2 = cmax(inst, s2)
            if c2 <= U and check_schedule(inst, c2, s2, m2):
                U, s, m = c2, s2, m2
                out['lp_sched'] = True
        L = L2
    out['lp_lb'] = L
    out['lp_ub'] = U
    out['L'] = L
    out['U'] = U
    out['schedule'] = s
    out['machine'] = m
    if L == U:
        out['stage'] = 'lp-exact'
        out['lp_exact'] = True
        return out
    if U <= (1.0 + eps) * L + 1e-12:
        out['stage'] = 'lp-approx'
        return out
    out['stage'] = 'open'
    return out


# --------------------------------------------------------------- main loop
def _choose_h(policy, L, U, first):
    if U - L <= 0:
        return L
    if policy == 'lower-first':
        return L if first else (L + U) // 2
    if policy == 'pact':
        return L if U - L <= 4 else (L + U) // 2
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'upper-first':
        return U - 1
    raise ValueError(policy)


def run_pace(inst, known, name, idx, eps=0.1, mode='approx',
             policy='lower-first', max_probes=64, init='poly'):
    """Run PACE and return a benchmark row.

    mode='approx' stops as soon as the A-gate holds; mode='exact' ignores
    the gate and only stops at L=U or budget exhaustion.
    """
    t0 = time.time()
    if init == 'pact':
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, s0, m0 = co.initial_bounds()
        if ub is None:
            return dict(name=name, idx=idx, known=known, eps=eps,
                        mode=mode, init=init, ok=False,
                        error='no-bounds', stage='pact-init',
                        t=round(time.time() - t0, 4))
        L, U = int(lb), int(ub)
        s, m = list(s0), list(m0)
        c0 = cmax(inst, s)
        if c0 <= U and check_schedule(inst, c0, s, m):
            U = c0
        pre = dict(chip=dict(), chip_lb=L, chip_ub=U, pin=None,
                   stage='pact-init', L=L, U=U, schedule=s, machine=m)
    else:
        co = None
        pre = pace_bounds(inst, eps=eps, stop_at_approx=(mode == 'approx'))
    L = pre.get('L')
    U = pre.get('U')
    s = pre.get('schedule')
    m = pre.get('machine')
    stage = pre['stage']
    probes = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    lp_solves = 0
    cert_lp = 0

    if L is None or U is None or s is None or m is None:
        return dict(name=name, idx=idx, known=known, eps=eps,
                    mode=mode, ok=False, error='no-bounds',
                    stage=stage, t=round(time.time() - t0, 4))

    if co is None:
        co = PACT(inst, pact_mode='complete', use_ga=False)
    chip = pre['chip']
    pin = pre.get('pin')
    # record chip certificates so _ensure_lb_proof can reuse them
    for hh, cert in chip.get('certs', []):
        co._record_proof(EnergyProof(inst, hh, cert))
    if init == 'pact':
        lb_proof = co._ensure_lb_proof(L)
        if lb_proof is None:
            lb_proof = _get_lb_proof(inst, L, chip, pin, co)
    else:
        lb_proof = _get_lb_proof(inst, L, chip, pin, co)

    def audit(regime, stg, probe_count):
        nonlocal partial_ok, partial_fail
        pc = PACECertificate(inst, L, U, s, m, lb_proof, regime,
                             eps=eps, stage=stg, probes=probe_count)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        return pc

    # If the P/A layer already closed, return without exact search.
    if lb_proof is not None:
        if L == U:
            audit('P', stage, 0)
            cert = ICFCertificate(inst, U, s, m, lb_proof)
            final_ok = bool(cert.audit_rdf())
            dt = time.time() - t0
            return dict(name=name, idx=idx, known=known, eps=eps,
                        mode=mode, ok=bool(final_ok
                                           and (known is None or U == known)
                                           and partial_fail == 0),
                        certified=final_ok,
                        known_exact=bool(U == known),
                        audit=final_ok, stage=stage, regime='P',
                        L=L, U=U, lb0=pre['chip_lb'],
                        ub0=pre['chip_ub'], probes=0,
                        lp_solves=0, cert_lp=0,
                        partial_ok=partial_ok,
                        partial_fail=partial_fail,
                        partial_final=final_ok, steps=steps,
                        t=round(dt, 4))
        if mode == 'approx' and U <= (1.0 + eps) * L + 1e-12:
            audit('A', stage, 0)
            pc = PACECertificate(inst, L, U, s, m, lb_proof, 'A',
                                 eps=eps, stage=stage)
            audit_ok = bool(pc.audit_rdf())
            ok = bool(audit_ok and (known is None or U == known
                                    or U <= (1.0 + eps) * known + 1e-12))
            dt = time.time() - t0
            return dict(name=name, idx=idx, known=known, eps=eps,
                        mode=mode, ok=ok, certified=audit_ok,
                        known_exact=bool(U == known),
                        known_ratio_ok=bool(known is None
                                            or U <= (1.0 + eps) * known + 1e-12),
                        audit=audit_ok, stage=stage,
                        regime='A', L=L, U=U, lb0=pre['chip_lb'],
                        ub0=pre['chip_ub'], probes=0,
                        lp_solves=0, cert_lp=0,
                        partial_ok=partial_ok,
                        partial_fail=partial_fail,
                        partial_final=bool(pc.audit_rdf()),
                        ratio=U / L if L else None, steps=steps,
                        t=round(dt, 4))

    # Exact ICF loop with an A-gate.
    first = True
    if lb_proof is not None:
        audit('B', 'open', 0)
    while L < U and probes < max_probes and lb_proof is not None:
        L0, U0 = L, U
        h = _choose_h(policy, L, U, first)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        lp_solves += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            p = r['proof']
            L = h + 1
            lb_proof = p
            co._record_proof(p)
            steps.append(dict(h=h, v=False, kind=p.kind,
                              lp=r.get('lp_solves', 0), L0=L0, U0=U0,
                              L1=L, U1=U))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U, s, m = c2, list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0), L0=L0, U0=U0,
                              L1=L, U1=U))
        else:
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
            break
        if lb_proof is None:
            break
        if L == U:
            audit('X', 'search-exact', probes)
            break
        if mode == 'approx' and U <= (1.0 + eps) * L + 1e-12:
            audit('A', 'search-approx', probes)
            break
        audit('B', 'open', probes)

    if L == U:
        regime = 'X' if probes else 'P'
        pc = PACECertificate(inst, L, U, s, m, lb_proof, regime,
                             eps=eps, stage='final', probes=probes)
        final_ok = bool(pc.audit_rdf())
        cert = ICFCertificate(inst, U, s, m, lb_proof)
        exact_ok = bool(cert.audit_rdf())
        dt = time.time() - t0
        return dict(name=name, idx=idx, known=known, eps=eps,
                    mode=mode, ok=bool(exact_ok
                                       and (known is None or U == known)
                                       and partial_fail == 0),
                    certified=exact_ok,
                    known_exact=bool(U == known),
                    audit=exact_ok, stage='search-exact', regime=regime,
                    L=L, U=U, lb0=pre['chip_lb'], ub0=pre['chip_ub'],
                    probes=probes, lp_solves=lp_solves,
                    cert_lp=cert_lp, partial_ok=partial_ok,
                    partial_fail=partial_fail,
                    partial_final=final_ok, ratio=1.0, steps=steps,
                    t=round(dt, 4))
    if U <= (1.0 + eps) * L + 1e-12:
        pc = PACECertificate(inst, L, U, s, m, lb_proof, 'A',
                             eps=eps, stage='final', probes=probes)
        audit_ok = bool(pc.audit_rdf())
        ok = bool(audit_ok and (known is None or U == known
                                or U <= (1.0 + eps) * known + 1e-12))
        dt = time.time() - t0
        return dict(name=name, idx=idx, known=known, eps=eps,
                    mode=mode, ok=ok, certified=audit_ok,
                    known_exact=bool(U == known),
                    known_ratio_ok=bool(known is None
                                        or U <= (1.0 + eps) * known + 1e-12),
                    audit=audit_ok, stage='search-approx',
                    regime='A', L=L, U=U, lb0=pre['chip_lb'],
                    ub0=pre['chip_ub'], probes=probes,
                    lp_solves=lp_solves, cert_lp=cert_lp,
                    partial_ok=partial_ok, partial_fail=partial_fail,
                    partial_final=bool(pc.audit_rdf()),
                    ratio=U / L if L else None, steps=steps,
                    t=round(dt, 4))
    pc = PACECertificate(inst, L, U, s, m, lb_proof, 'B',
                         eps=eps, stage='final', probes=probes)
    dt = time.time() - t0
    return dict(name=name, idx=idx, known=known, eps=eps, mode=mode,
                ok=False, certified=False, audit=bool(pc.audit_rdf()),
                stage='partial', regime='B', L=L, U=U,
                lb0=pre['chip_lb'], ub0=pre['chip_ub'], probes=probes,
                lp_solves=lp_solves, cert_lp=cert_lp,
                partial_ok=partial_ok, partial_fail=partial_fail,
                partial_final=bool(pc.audit_rdf()),
                ratio=U / L if L else None, steps=steps,
                t=round(dt, 4))
