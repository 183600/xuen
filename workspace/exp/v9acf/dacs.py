"""v9.2 DACS: Dual-end Asynchronous Certificate Search.

A DACS state is a set of sound partial certificates for the *same*
instance.  Each certificate c carries

    L_c <= OPT <= U_c,   proof_c : NO(L_c - 1),   schedule_c : Cmax = U_c.

The certificates are combined by the join

    L = max_c L_c,   U = min_c U_c,

with proof taken from a certificate attaining L and schedule from one
attaining U.  The join is associative, commutative and idempotent, so
worker completion order is irrelevant.  This is the asynchronous layer:
a worker publishes one certificate; the join is the only synchronisation.

The v9.2 worker policy is dual-end: at bracket [L,U] it launches an
exact probe at h=L (lower attack) and at h=U-1 (upper attack).  For
gap one these coincide; for larger gaps they attack the two certificates
that can close the bracket, avoiding the L-vs-U side choice that made
v9.0's lower-first policy corpus-dependent.  A neural side-prior is
optional and is gated by an out-of-distribution test; it may only order
work, never remove the two-end coverage.
"""
from __future__ import annotations

import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import (PartialCertificate, ICFCertificate, cmax, corpora)
from pact import PACT, pact_decide
from rdf import check_schedule


class Cert:
    """A sound bracket plus its two witnesses."""

    __slots__ = ('inst', 'L', 'U', 'schedule', 'machine', 'proof',
                 'source', 'h', 'lp', 'cert_lp', 't', 'workers')

    def __init__(self, inst, L, U, schedule, machine, proof,
                 source='initial', h=None, lp=0, cert_lp=0, t=0.0,
                 workers=()):
        self.inst = inst
        self.L = int(L)
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.proof = proof
        self.source = source
        self.h = h
        self.lp = int(lp)
        self.cert_lp = int(cert_lp)
        self.t = float(t)
        self.workers = tuple(workers)

    def to_partial(self):
        return PartialCertificate(self.inst, self.L, self.U,
                                  self.schedule, self.machine,
                                  self.proof)

    def audit(self):
        return bool(self.to_partial().audit_rdf())

    def final(self):
        c = ICFCertificate(self.inst, self.U, self.schedule,
                           self.machine, self.proof)
        return c if self.L == self.U else None


def initial_cert(inst, stats=None):
    """PACT's certified initial bracket with an audited NO(L-1) proof."""
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None or sched is None:
        return None
    proof = co._ensure_lb_proof(int(lb))
    if proof is None:
        r = pact_decide(inst, int(lb) - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    if proof is None:
        return None
    c = Cert(inst, lb, ub, sched, mach, proof, source='initial')
    if stats is not None:
        stats['pin_lp'] = stats.get('pin_lp', 0) + getattr(co, 'pin_lp', 0)
    return c if c.audit() else None


def join(certs):
    """Join a non-empty iterable of certificates for the same instance."""
    certs = [c for c in certs if c is not None]
    if not certs:
        return None
    lo = max(certs, key=lambda c: (c.L, -c.lp))
    hi = min(certs, key=lambda c: (c.U, c.lp))
    out = Cert(lo.inst, lo.L, hi.U, hi.schedule, hi.machine, lo.proof,
               source='join', h=None,
               lp=sum(c.lp for c in certs),
               cert_lp=sum(c.cert_lp for c in certs),
               t=max(c.t for c in certs),
               workers=tuple(w for c in certs for w in c.workers))
    return out


def _probe_cert(inst, h, base):
    t0 = time.time()
    r = pact_decide(inst, h, depthcap=None, nodecap=None)
    dt = time.time() - t0
    lp = int(r.get('lp_solves', 0))
    cl = int(r.get('cert_lp', 0))
    if r['verdict'] is False:
        proof = r['proof']
        if proof is None or proof.h != h:
            return None, dict(lp=lp, cert_lp=cl, t=dt, verdict='hole')
        c = Cert(inst, h + 1, base.U, base.schedule, base.machine,
                 proof, source='lower', h=h, lp=lp, cert_lp=cl, t=dt,
                 workers=('L',))
        return (c if c.audit() else None), dict(lp=lp, cert_lp=cl,
                                                t=dt, verdict='NO')
    if r['verdict'] is True:
        s2, m2 = r['schedule'], r['machine']
        u2 = cmax(inst, s2)
        if u2 < base.L or not check_schedule(inst, u2, s2, m2):
            return None, dict(lp=lp, cert_lp=cl, t=dt, verdict='bad-yes')
        c = Cert(inst, base.L, u2, s2, m2, base.proof,
                 source='upper', h=h, lp=lp, cert_lp=cl, t=dt,
                 workers=('U',))
        return (c if c.audit() else None), dict(lp=lp, cert_lp=cl,
                                                t=dt, verdict='YES')
    return None, dict(lp=lp, cert_lp=cl, t=dt, verdict='UNKNOWN')


def _horizons(mode, L, U):
    if U <= L:
        return []
    if mode in ('both', 'both-parallel'):
        return sorted(set([L, U - 1]))
    if mode == 'both-race':
        return [L, U - 1]
    if mode == 'lower':
        return [L]
    if mode == 'upper':
        return [U - 1]
    if mode == 'binary':
        return [(L + U) // 2]
    if mode == 'grid':
        if U - L > 10:
            step = (U - L) // 5 + 1
            return sorted(set([L] + list(range(L + step, U, step))
                               + [U - 1]))
        return list(range(L, U))
    raise ValueError('unknown mode %r' % (mode,))


def run_dacs(inst, known, name, idx, mode='both-parallel',
             max_rounds=16, side_model=None, audit=True):
    """Run one DACS instance.

    mode:
      both-parallel : launch L and U-1 together, join after both finish
      both-race     : launch L first; skip U-1 if L already closes
      lower/upper   : single-end scanning (baselines)
      binary        : midpoint policy
      grid          : probe all horizons in a capped grid
      neural        : gated side-prior first, then dual-end fallback
    """
    t0 = time.time()
    stats = dict(pin_lp=0, probes=0, lp=0, cert_lp=0, rounds=0,
                 audit_ok=0, audit_fail=0, unknown=0, cancelled=0)
    base = initial_cert(inst, stats)
    if base is None:
        return dict(name=name, idx=idx, known=known, mode=mode,
                    ok=False, error='no-initial-cert', t=0.0, **stats)
    G = base
    initial_L, initial_U = base.L, base.U
    trace = []
    neural_used = False
    fallback = False

    for rnd in range(max_rounds):
        if G.L >= G.U:
            break
        stats['rounds'] = rnd + 1
        if mode == 'neural' and not fallback and side_model is not None:
            p_upper, ood = side_model(inst, G.L, G.U)
            neural_used = True
            if ood:
                # Distribution shift: never trust the side, cover both ends.
                hs = [G.L, G.U - 1]
            else:
                hs = [G.U - 1] if p_upper >= 0.5 else [G.L]
                fallback = True
        elif mode == 'neural':
            hs = [G.L, G.U - 1]
        else:
            hs = _horizons(mode, G.L, G.U)
        hs = [h for h in hs if G.L <= h <= G.U - 1]
        if not hs:
            break
        round_certs = []
        round_times = []
        round_lp = 0
        round_cert_lp = 0
        aborted = False
        for j, h in enumerate(hs):
            c, st = _probe_cert(inst, h, G)
            stats['probes'] += 1
            stats['lp'] += st['lp']
            stats['cert_lp'] += st['cert_lp']
            round_lp += st['lp']
            round_cert_lp += st['cert_lp']
            round_times.append(st['t'])
            if st['verdict'] == 'UNKNOWN':
                stats['unknown'] += 1
            if c is not None:
                round_certs.append(c)
                if audit:
                    if c.audit():
                        stats['audit_ok'] += 1
                    else:
                        stats['audit_fail'] += 1
            if mode == 'both-race':
                tmp = join([G] + round_certs)
                if tmp is not None and tmp.L >= tmp.U:
                    stats['cancelled'] += len(hs) - j - 1
                    aborted = True
                    break
        if round_certs:
            G2 = join([G] + round_certs)
            if G2 is None:
                break
            G = G2
        else:
            if mode != 'both-race':
                break
        if audit:
            if G.audit():
                stats['audit_ok'] += 1
            else:
                stats['audit_fail'] += 1
        trace.append(dict(round=rnd, horizons=hs, L=G.L, U=G.U,
                          lp=round_lp, cert_lp=round_cert_lp,
                          t=round(max(round_times) if round_times else 0.0),
                          cancelled=0))
        if mode == 'neural':
            if fallback:
                mode = 'both-parallel'
            # after the first neural round, always use dual-end coverage
            mode = 'both-parallel'
        if G.L >= G.U:
            break

    final = G.final()
    final_ok = bool(final is not None and final.audit_rdf()) \
        if audit else bool(final is not None)
    partial_ok = bool(G.audit()) if audit else True
    dt = time.time() - t0
    return dict(name=name, idx=idx, known=known, mode=mode,
                opt=G.U, lb=G.L, lb0=initial_L, ub0=initial_U,
                certified=bool(G.L == G.U and final_ok),
                audit=final_ok, partial_final=partial_ok,
                cert_h=(G.U - 1 if G.L == G.U else None),
                rounds=stats['rounds'], probes=stats['probes'],
                lp=stats['lp'], cert_lp=stats['cert_lp'],
                pin_lp=stats['pin_lp'],
                audit_ok=stats['audit_ok'],
                audit_fail=stats['audit_fail'],
                unknown=stats['unknown'],
                cancelled=stats['cancelled'],
                neural_used=neural_used,
                trace=trace,
                t=round(dt, 4),
                ok=bool(G.L == G.U and G.U == known and final_ok
                        and stats['audit_fail'] == 0 and partial_ok))
