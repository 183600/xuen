"""v8.4 CCB-ALC: certificate-carrying bracket.

The bracket invariant only needs *some* replayable proof at its endpoints:

    LB <= OPT <= UB,
    LB is backed by a NO certificate at LB-1,
    UB is backed by a replayed schedule.

CRISP (v8.1) hard-codes the inner oracle as the only source of NO proofs.
CCB makes the proof type explicit and substitutable.  A bound proof, an
energy/window proof, or a Farkas/LP proof are all first-class as long as
they implement:

    proof.h                  -- the deadline it refutes
    proof.audit_rdf()        -- independent replay
    proof.proof_complete()   -- no unbacked leaf

Consequences:
  * an exact preprocessing bracket needs no oracle call at OPT-1;
  * every cached NO proof can answer a later query at the same h;
  * the certificate path is deterministic (randomness, if any, lives
    only in the optional YES constructor and is checked by replay).

The layer is orthogonal to the inner oracle: CCB(CRISP) uses CHD,
CCBHybrid(HybridCRISP) uses the v8.3 HSC+cut-pool oracle.
"""
import sys

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import CRISP, chip_bounds
from scale import verify_prep, windows
from po import heads_tails
from hybrid_crisp import HybridCRISP


def replay_lb(inst):
    """Recompute the critical-path + eligibility-load lower bound."""
    n, m, p, elig = inst['n'], inst['m'], inst['p'], inst['elig']
    est, q = heads_tails(inst, 0, [0] * n)
    lb = max(est[i] + p[i] + q[i] for i in range(n))
    for mask in range(1, 1 << m):
        jobs = [i for i in range(n)
                if all((mask >> k) & 1 for k in elig[i])]
        load = sum(p[i] for i in jobs)
        cnt = bin(mask).count('1')
        lb = max(lb, (load + cnt - 1) // cnt)
    return lb


class BoundProof:
    """NO proof for every h below the replayable lower bound."""

    def __init__(self, inst, h, lb=None):
        self.inst = inst
        self.h = h
        self.lb = replay_lb(inst) if lb is None else lb
        self.phase = 'bound'
        self.yes_ok = False
        self.schedule = None
        self.machine = None

    def audit_rdf(self):
        return self.h < replay_lb(self.inst)

    def proof_complete(self):
        return self.audit_rdf()

    def _stats(self, why='bound'):
        return dict(why=why, lp_solves=0, nodes=0, yes_nodes=0,
                    mc_evals=0, schedule=None, machine=None,
                    yes_ok=False, phase='bound')


class PrepProof:
    """NO proof from a replayable energy/window inequality at h."""

    def __init__(self, inst, h, cert):
        self.inst = inst
        self.h = h
        self.cert = cert
        self.kind = cert.get('kind')
        self.phase = 'prep'
        self.yes_ok = False
        self.schedule = None
        self.machine = None

    def audit_rdf(self):
        if self.kind == 'energy':
            return bool(verify_prep(self.inst, self.h, self.cert))
        if self.kind == 'window':
            ee, ll, _ = windows(self.inst, self.h)
            return any(ee[i] > ll[i] for i in range(self.inst['n']))
        return False

    def proof_complete(self):
        return self.audit_rdf()

    def _stats(self, why='prep'):
        return dict(why=why, lp_solves=0, nodes=0, yes_nodes=0,
                    mc_evals=0, schedule=None, machine=None,
                    yes_ok=False, phase='prep')


class ProofCarrying:
    """Mixin: proof polymorphism + cache for a CRISP-like bracket."""

    probe_ub1 = False
    probe_width = 3

    def initial_bounds(self):
        lb, ub, starts, machs = super().initial_bounds()
        b = getattr(self, 'chip', None) or {}
        self.prep_proofs = {}
        self.cache_hits = 0
        self.cache_kinds = {}
        self.bound_proofs = 0
        self.energy_proofs = 0
        self.window_proofs = 0
        if ub is None or not b.get('ok', True):
            return lb, ub, starts, machs
        for h, cert in b.get('certs', []):
            p = PrepProof(self.inst, h, cert)
            if p.audit_rdf():
                self.prep_proofs[h] = p
                if p.kind == 'energy':
                    self.energy_proofs += 1
                elif p.kind == 'window':
                    self.window_proofs += 1
        bp = BoundProof(self.inst, b['lb0'] - 1)
        if bp.audit_rdf():
            self.prep_proofs.setdefault(b['lb0'] - 1, bp)
            self.bound_proofs = 1
        if b['lb'] == b['ub']:
            p = self.prep_proofs.get(b['ub'] - 1)
            if p is not None and p.audit_rdf():
                self.no_states[b['ub'] - 1] = p
                self.lb_proof = p
        return lb, ub, starts, machs

    def _cached_no(self, h):
        p = self.no_states.get(h)
        if p is not None and p.audit_rdf():
            k = type(p).__name__
            self.cache_kinds[k] = self.cache_kinds.get(k, 0) + 1
            return p
        p = self.prep_proofs.get(h)
        if p is not None and p.audit_rdf():
            self.no_states[h] = p
            k = type(p).__name__
            self.cache_kinds[k] = self.cache_kinds.get(k, 0) + 1
            return p
        return None

    def optimize(self):
        lb, ub, starts, machs = self.initial_bounds()
        self.lb0, self.ub0 = lb, ub
        self.lb = lb
        if ub is not None:
            self.schedule, self.machine, self.opt = starts, machs, ub
        while self.lb < self.opt and self.queries < self.max_queries:
            w = self.opt - self.lb
            h = (self.opt - 1 if (self.probe_ub1 and w <= self.probe_width)
                 else (self.lb + self.opt) // 2)
            p = self._cached_no(h)
            if p is not None:
                self.cache_hits += 1
                self.lb = max(self.lb, h + 1)
                self._record(h, False, p._stats('cache'))
                continue
            v, st, rdf = self._decide(h)
            self.queries += 1
            self._absorb(st)
            self._record(h, v, st)
            if v is True:
                cmax = max(rdf.schedule[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                if cmax < self.opt:
                    self.opt = cmax
                    self.schedule = list(rdf.schedule)
                    self.machine = list(rdf.machine)
            elif v is False:
                self.lb = max(self.lb, h + 1)
                self.no_states[h] = rdf
                self.lb_proof = rdf
            else:
                self.unknown += 1
                self._recover_unknown(h)
        self.certified = (self.lb == self.opt and self.opt is not None)
        if self.certified and (self.opt - 1) not in self.no_states:
            p = self._cached_no(self.opt - 1)
            if p is not None:
                self.cache_hits += 1
                self.no_states[self.opt - 1] = p
            else:
                v, st, rdf = self._decide(self.opt - 1)
                self.queries += 1
                self._absorb(st)
                self._record(self.opt - 1, v, st)
                if v is False:
                    self.no_states[self.opt - 1] = rdf
                else:
                    self.certified = False
        if self.certified:
            self.lb_proof = self.no_states.get(self.opt - 1)
            if self.lb_proof is None:
                self.certified = False
        return self._result()

    def _result(self):
        r = super()._result()
        r['cache_hits'] = getattr(self, 'cache_hits', 0)
        r['proof_kind'] = (type(self.lb_proof).__name__
                           if self.lb_proof is not None else None)
        r['energy_proofs'] = getattr(self, 'energy_proofs', 0)
        r['window_proofs'] = getattr(self, 'window_proofs', 0)
        r['bound_proofs'] = getattr(self, 'bound_proofs', 0)
        r['prep_proofs'] = len(getattr(self, 'prep_proofs', {}))
        r['cache_kinds'] = dict(getattr(self, 'cache_kinds', {}))
        return r


class CCB(ProofCarrying, CRISP):
    """Certificate-carrying bracket with the v8.1 CHD oracle."""


class CCBHybrid(ProofCarrying, HybridCRISP):
    """Certificate-carrying bracket with the v8.3 HSC+cut-pool oracle."""

    probe_ub1 = True
    probe_width = 3
