"""TRIAD-PACT: triangulated interval pivot search with typed evidence.

The outer state of ICF-PACT is one bracket [L,U].  TRIAD makes the whole
horizon axis a certificate object:

    vertices  h_0 < h_1 < ... < h_k
    label(h)  in {NO, YES, UNK}
    L = max(L0, max{h+1 : label(h)=NO})
    U = min(U0, min{Cmax(s) : label(h)=YES})

The open cells are the intervals [L, v_1], [v_1, v_2], ..., [v_m, U]
where v_i are the UNK vertices strictly inside (L,U).  NO closes every
horizon <= h; YES closes every horizon >= h.  A probe at h inside an open
cell refines that cell; an UNKNOWN answer splits it into two open cells
and leaves the global bracket unchanged.  Thus the current state is always
a partially correct certificate, and the multi-cell state is useful when
the inner oracle is budgeted.

The pivot is chosen by a policy.  `predicted` uses a learned regression
of the NO/YES boundary; the prediction is an untrusted hint, and a
prediction outside the selected cell falls back to its midpoint.  All
evidence is submitted through EvidenceBus, so soundness never depends on
the predictor.
"""
from __future__ import annotations

import sys
import time
import math
import random

sys.path[:0] = ['exp/v9tri', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import cmax, PartialCertificate, ICFCertificate
from pact import PACT, pact_decide
from rdf import check_schedule
from io_spec import (NO, YES, UNK, Evidence, EvidenceBus,
                     instance_scope)


class OracleStats:
    def __init__(self):
        self.lp = 0
        self.cert_lp = 0
        self.nodes = 0
        self.calls = 0
        self.unknown = 0
        self.no = 0
        self.yes = 0
        self.t = 0.0


def decide(inst, h, co, nodecap=None):
    """One typed probe.  Exceptions are converted to UNK, never to a lie."""
    t0 = time.time()
    st = dict(lp=0, cert_lp=0, nodes=0, verdict=None)
    try:
        r = pact_decide(inst, h, depthcap=None, nodecap=nodecap)
        st['lp'] = r.get('lp_solves', 0)
        st['cert_lp'] = r.get('cert_lp', 0)
        st['nodes'] = r.get('nodes', 0)
        st['verdict'] = r.get('verdict')
        if r['verdict'] is False:
            return (Evidence(NO, h, proof=r['proof'],
                             lp=st['lp'], scope=instance_scope(inst)),
                    st)
        if r['verdict'] is True:
            s, m = r['schedule'], r['machine']
            c = cmax(inst, s)
            if c <= h and check_schedule(inst, c, s, m):
                return (Evidence(YES, h, schedule=list(s),
                                 machine=list(m), cmax=c,
                                 lp=st['lp'],
                                 scope=instance_scope(inst)), st)
            st['verdict'] = None
        # UNKNOWN from the oracle.
        return (Evidence(UNK, h, lp=st['lp'],
                         scope=instance_scope(inst)), st)
    except Exception:
        # The SDLP can be empty for very small h; try the cheap lower-bound
        # certificate path.  If that fails too, the probe is UNKNOWN.
        try:
            p = co._ensure_lb_proof(h + 1)
            if p is not None and p.h == h and p.audit_rdf():
                st['verdict'] = False
                return (Evidence(NO, h, proof=p,
                                 scope=instance_scope(inst)), st)
        except Exception:
            pass
        st['verdict'] = None
        return (Evidence(UNK, h, scope=instance_scope(inst)), st)
    finally:
        st['t'] = time.time() - t0


def prepare(inst, L0=None, U0=None, use_pact_init=True):
    """Build the root certificate and root triangulation."""
    t0 = time.time()
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None or sched is None or mach is None:
        raise RuntimeError('no initial upper bound')
    if U0 is None:
        U0 = int(ub)
    if L0 is None:
        L0 = int(lb)
    U0 = int(U0)
    L0 = int(L0)
    if cmax(inst, sched) != U0:
        # keep the schedule's true makespan as the upper bound
        U0 = int(cmax(inst, sched))
    if not (0 <= L0 <= U0):
        raise ValueError('bad root bracket')
    proof = co._ensure_lb_proof(L0)
    if proof is None or proof.h != L0 - 1 or not proof.audit_rdf():
        # Last resort: a direct complete NO call at L0-1.
        r = pact_decide(inst, L0 - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False and r['proof'].audit_rdf():
            proof = r['proof']
    if proof is None or proof.h != L0 - 1 or not proof.audit_rdf():
        raise RuntimeError('no auditable lower-bound proof at L0-1')
    scope = instance_scope(inst)
    initial = Evidence(NO, L0 - 1, proof=proof, scope=scope)
    bus = EvidenceBus(inst, L0, U0, initial, sched, mach, scope=scope)
    return dict(co=co, bus=bus, L0=L0, U0=U0,
                initial=initial, base_schedule=list(sched),
                base_machine=list(mach), scope=scope,
                init_lp=getattr(co, 'pin_lp', 0),
                init_t=round(time.time() - t0, 5),
                proof_kind=getattr(proof, 'kind', None))


def open_cells(bus):
    pts = sorted(h for h, ev in bus.vertices.items()
                 if ev.kind == UNK and bus.L < h < bus.U)
    bounds = [bus.L] + pts + [bus.U]
    return list(zip(bounds[:-1], bounds[1:]))


def _pick_in_cell(a, b, pred=None, prefer='pred'):
    if b <= a:
        return None
    if prefer == 'lower':
        return a
    if prefer == 'upper':
        return b - 1
    if prefer == 'binary':
        return (a + b) // 2
    if pred is None:
        return (a + b) // 2
    v = int(round(pred))
    if v <= a:
        v = a
    if v >= b:
        v = b - 1
    return v


def choose_pivot(bus, policy='hybrid', pred=None, cells=None, root=False):
    cells = cells or open_cells(bus)
    if not cells:
        return None, None
    if policy == 'lower-first':
        a, b = bus.L, bus.U
        return (a, b), a
    if policy == 'upper-first':
        a, b = bus.L, bus.U
        return (a, b), b - 1
    if policy == 'binary':
        a, b = bus.L, bus.U
        return (a, b), (a + b) // 2
    if policy == 'oracle':
        a, b = bus.L, bus.U
        v = min(max(bus.L, int(pred)), bus.U - 1)
        return (a, b), v
    if policy == 'predicted':
        if pred is None or pred < bus.L or pred >= bus.U:
            # A stale prediction must not make the search linear.
            a, b = bus.L, bus.U
            return (a, b), (a + b) // 2
        # Prefer the cell containing the prediction; otherwise largest.
        for a, b in cells:
            if a < pred < b:
                return (a, b), _pick_in_cell(a, b, pred, 'pred')
        a, b = max(cells, key=lambda x: x[1] - x[0])
        return (a, b), _pick_in_cell(a, b, pred, 'pred')
    if policy == 'hybrid':
        gap = bus.U - bus.L
        if gap <= 1:
            a, b = bus.L, bus.U
            return (a, b), a
        if (root and pred is not None and bus.L - pred >= 1.5
                and gap <= 8):
            # At the root, a learned boundary below L is evidence that the
            # lower bound is already tight (the 252-case regime).  Probe L
            # once; afterwards use binary/predicted so a stale prediction
            # cannot scan linearly.
            a, b = bus.L, bus.U
            return (a, b), a
        if gap <= 3 or pred is None or pred < bus.L or pred >= bus.U:
            a, b = bus.L, bus.U
            return (a, b), (a + b) // 2
        return choose_pivot(bus, 'predicted', pred, cells)
    raise ValueError('unknown policy %r' % (policy,))


def batch_pivots(bus, policy, pred, k):
    """Distinct pivots for a parallel round; at most one per open cell."""
    pivots = []
    cells = open_cells(bus)
    if policy == 'batch-pred' and pred is not None:
        # one pivot near the prediction, then quantiles of the open range
        cells_sorted = sorted(cells, key=lambda x: x[0])
        for j in range(k):
            if j == 0:
                a, b = bus.L, bus.U
                v = _pick_in_cell(a, b, pred, 'pred')
            else:
                frac = j / max(1, k)
                v = int(round(bus.L + frac * (bus.U - bus.L)))
                v = min(max(bus.L, v), bus.U - 1)
            if v not in pivots and v not in bus.vertices:
                pivots.append(v)
    else:
        for a, b in cells:
            v = (a + b) // 2
            if v not in pivots and v not in bus.vertices:
                pivots.append(v)
            if len(pivots) >= k:
                break
    return pivots


def run_triad(inst, known=None, policy='hybrid', pred=None,
              max_probes=64, nodecap=None, batch=1, L0=None, U0=None,
              prepare_ctx=None):
    t0 = time.time()
    if prepare_ctx is None:
        ctx = prepare(inst, L0=L0, U0=U0)
    else:
        ctx = dict(prepare_ctx)
        ctx['bus'] = EvidenceBus(
            inst, ctx['L0'], ctx['U0'], ctx['initial'],
            ctx['base_schedule'], ctx['base_machine'],
            scope=ctx['scope'])
    bus = ctx['bus']
    co = ctx['co']
    st = OracleStats()
    probes = 0
    rounds = 0
    partial_ok = partial_fail = 0
    steps = []
    audits = []
    batch = max(1, int(batch))

    def audit_state():
        nonlocal partial_ok, partial_fail
        ok = bus.audit(require_final=False)
        if ok:
            partial_ok += 1
        else:
            partial_fail += 1
        audits.append(ok)
        return ok

    audit_state()
    while bus.L < bus.U and probes < max_probes:
        before = (bus.L, bus.U)
        if batch == 1:
            cell, v = choose_pivot(bus, policy, pred, root=(probes == 0))
            pivots = [] if v is None else [v]
        else:
            pivots = batch_pivots(bus, policy, pred, batch)
        if not pivots:
            break
        round_ev = []
        for v in pivots:
            if probes >= max_probes:
                break
            ev, s = decide(inst, v, co, nodecap=nodecap)
            probes += 1
            st.lp += s['lp']
            st.cert_lp += s['cert_lp']
            st.nodes += s['nodes']
            st.calls += 1
            st.t += s.get('t', 0.0)
            ok, why = bus.submit(ev)
            if not ok:
                steps.append(dict(v=v, kind=ev.kind, reject=why,
                                  L0=before[0], U0=before[1],
                                  L1=bus.L, U1=bus.U))
                continue
            if ev.kind == NO:
                st.no += 1
            elif ev.kind == YES:
                st.yes += 1
            else:
                st.unknown += 1
            round_ev.append((v, ev.kind))
            steps.append(dict(v=v, kind=ev.kind, lp=ev.lp,
                              L0=before[0], U0=before[1],
                              L1=bus.L, U1=bus.U))
        rounds += 1
        audit_state()
        if bus.L == bus.U:
            break
        if not round_ev and not pivots:
            break

    cert = bus.certificate()
    final_ok = bool(cert.audit_rdf(require_final=(bus.L == bus.U)))
    icf_ok = False
    if bus.L == bus.U:
        try:
            icf = ICFCertificate(inst, bus.U, bus.schedule, bus.machine,
                                 bus.lb_proof)
            icf_ok = bool(icf.audit_rdf())
        except Exception:
            icf_ok = False
    pc = None
    try:
        pc = PartialCertificate(inst, bus.L, bus.U, bus.schedule,
                                bus.machine, bus.lb_proof,
                                probe=probes)
        partial_final = bool(pc.audit_rdf())
    except Exception:
        partial_final = False
    dt = time.time() - t0
    return dict(
        known=known, policy=policy, L0=ctx['L0'], U0=ctx['U0'],
        L=bus.L, U=bus.U, gap0=ctx['U0'] - ctx['L0'],
        gap=bus.U - bus.L, probes=probes, rounds=rounds,
        lp=st.lp, cert_lp=st.cert_lp, nodes=st.nodes,
        unknown=st.unknown, no=st.no, yes=st.yes, oracle_calls=st.calls,
        init_lp=ctx.get('init_lp', 0), init_t=ctx.get('init_t', 0.0),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final, final_audit=final_ok,
        icf_audit=icf_ok,
        certified=bool(bus.L == bus.U and final_ok),
        opt=(known is not None and bus.L == bus.U == known),
        steps=steps, audits=audits,
        proof_kind=ctx.get('proof_kind'),
        pred=pred, t=round(dt, 5),
        cert=cert)
