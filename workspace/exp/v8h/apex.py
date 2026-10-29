"""v8.7 APEX-ALC: approximation-ratio proof exchange with LP pinning.

APEX keeps the v8.1 CRISP bracket but changes what a lower bound is.
A lower-bound fact is a first-class proof object, not a syntactic promise
to produce an oracle NO at ub-1.  The proof store accepts:

  * combinatorial bounds (critical path, eligibility load);
  * energy/window NO certificates;
  * Farkas certificates from the root LP at h;
  * the LP value function: L* = min { h : P_h feasible };
  * oracle NO states from CHD.

The LP value function is the approximation algorithm on the lower side.
Its gap g = OPT - L* is the integrality gap of the start-time relaxation.
The exact oracle is only asked to close g (or to construct a schedule at
L* when the LP solution is fractional).  An LNS/MILP repair closes the
remaining upper side without spending a CHD query.

Every accepted schedule passes check_schedule; every NO proof is replayed
by an independent checker; audit/proof_complete are inherited.
"""
import sys
import time

sys.path[:0] = ['exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from chip import chip_bounds
from cab import CABOpt
from chd import CHD
from rdf import check_schedule
from cert import verify, integer_certificate
from scale import verify_prep, energy_cert, windows
from po import heads_tails
from lbp import lp_threshold, lp_schedule, farkas_bounds, cp_cert
from lns import lns_drop


def bound_lb(inst):
    """The v8.1 critical-path + eligibility-load lower bound."""
    n, m, elig = inst['n'], inst['m'], inst['elig']
    est, q = heads_tails(inst, 0, [0] * n)
    lb = max(est[i] + inst['p'][i] + q[i] for i in range(n))
    for mask in range(1, 1 << m):
        jobs = [i for i in range(n)
                if all((mask >> k) & 1 for k in elig[i])]
        load = sum(inst['p'][i] for i in jobs)
        cnt = bin(mask).count('1')
        lb = max(lb, (load + cnt - 1) // cnt)
    return lb


class Proof:
    kind = 'proof'

    def __init__(self, inst, h):
        self.inst = inst
        self.h = h

    def audit_rdf(self):
        return True

    def proof_complete(self):
        return True

    def __repr__(self):
        return '%s@%s' % (self.kind, self.h)


class BoundProof(Proof):
    kind = 'bound'

    def __init__(self, inst, h, value):
        super().__init__(inst, h)
        self.value = value

    def audit_rdf(self):
        return bound_lb(self.inst) == self.value

    def proof_complete(self):
        return self.audit_rdf()


class EnergyProof(Proof):
    kind = 'energy'

    def __init__(self, inst, h, cert):
        super().__init__(inst, h)
        self.cert = cert
        self.kind = cert.get('kind', 'energy') if cert else 'energy'

    def audit_rdf(self):
        c = self.cert
        if c is None:
            return False
        if c.get('kind') == 'window' and 'job' not in c:
            est, lst, _ = windows(self.inst, self.h)
            return any(est[i] > lst[i] for i in range(self.inst['n']))
        return verify_prep(self.inst, self.h, c)

    def proof_complete(self):
        return self.audit_rdf()


class FarkasProof(Proof):
    kind = 'farkas'

    def __init__(self, inst, h, cert):
        super().__init__(inst, h)
        self.cert = cert

    def audit_rdf(self):
        return bool(self.cert is not None
                    and verify(self.inst, self.h, self.cert))

    def proof_complete(self):
        return self.audit_rdf()


class OracleProof(Proof):
    kind = 'oracle'

    def __init__(self, rdf):
        super().__init__(rdf.inst, rdf.h)
        self.rdf = rdf

    def audit_rdf(self):
        return bool(self.rdf.audit_rdf())

    def proof_complete(self):
        return bool(self.rdf.proof_complete())


class APEX(CABOpt):
    """LP-pinned bracket + first-class lower-bound proofs + LNS repair."""

    def __init__(self, inst, scan_cap=4, lns_budget=32, lns_kmax=14,
                 lns_tlim=0.4, lns_stall=6, use_lp=True, use_lns=True,
                 use_lp_sched=True, use_proof=True, **kw):
        super().__init__(inst, **kw)
        self.scan_cap = scan_cap
        self.lns_budget = lns_budget
        self.lns_kmax = lns_kmax
        self.lns_tlim = lns_tlim
        self.lns_stall = lns_stall
        self.use_lp = use_lp
        self.use_lns = use_lns
        self.use_lp_sched = use_lp_sched
        self.use_proof = use_proof
        self.chip = None
        self.pin = None
        self.proofs = {}
        self.pin_lp = 0
        self.lns_stats = None
        self.stats = dict(lp_pin=0, lns_used=0, lns_exact=0, lp_sched=0,
                          farkas=0, energy=0, bound=0, oracle=0,
                          scan_q=0, bin_q=0, proof_final=0)

    # ------------------------------------------------------------ proofs
    def _record_proof(self, p):
        if p is None:
            return None
        self.proofs[p.h] = p
        if p.kind in ('window', 'energy'):
            self.stats['energy'] += 1
        elif p.kind == 'bound':
            self.stats['bound'] += 1
        elif p.kind == 'farkas':
            self.stats['farkas'] += 1
        elif p.kind == 'oracle':
            self.stats['oracle'] += 1
        return p

    def _lp_no_proof(self, h):
        c = cp_cert(self.inst, h)
        if c is not None:
            return self._record_proof(FarkasProof(self.inst, h, c))
        p = self.pin or {}
        ps = p.get('param')
        if ps is not None:
            c = farkas_bounds(ps.lp, h, ps.bounds_h(h))
            if c is not None and verify(self.inst, h, c):
                return self._record_proof(FarkasProof(self.inst, h, c))
        elig = any(len(set(self.inst['elig'][i])) < self.inst['m']
                   for i in range(self.inst['n']))
        c = integer_certificate(self.inst, h, use_dom=True,
                                elig_aware=elig)
        if c is not None and verify(self.inst, h, c):
            return self._record_proof(FarkasProof(self.inst, h, c))
        return None

    def _ensure_lb_proof(self, value):
        h = value - 1
        if h in self.proofs:
            return self.proofs[h]
        if h in self.no_states:
            return self._record_proof(OracleProof(self.no_states[h]))
        if value == bound_lb(self.inst):
            return self._record_proof(
                BoundProof(self.inst, h, value))
        c = energy_cert(self.inst, h, 64, 20000)
        if c is not None and EnergyProof(self.inst, h, c).audit_rdf():
            return self._record_proof(EnergyProof(self.inst, h, c))
        return self._lp_no_proof(h)

    # ------------------------------------------------------------- bounds
    def _lp_schedule_at(self, h):
        p = self.pin or {}
        ps = p.get('param')
        if ps is None:
            return None
        res = p.get('last_res') if p.get('last_h') == h else None
        if res is None:
            res = ps.solve_h(h)
            self.pin_lp += 1
            self.stats['lp_pin'] = self.pin_lp
        return lp_schedule(ps, self.inst, h, res=res)

    def initial_bounds(self):
        b = chip_bounds(self.inst)
        self.chip = b
        if not b.get('ok') or b.get('ub') is None:
            return b.get('lb'), None, None, None
        for h, c in b.get('certs', []):
            self._record_proof(EnergyProof(self.inst, h, c))
        lb, ub = b['lb'], b['ub']
        sched, mach = b['schedule'], b['machine']

        if self.use_lp and lb < ub:
            pin = lp_threshold(self.inst, lb, ub, T=ub)
            self.pin = pin
            self.pin_lp = pin['solves']
            self.stats['lp_pin'] = self.pin_lp
            lpb = (max(lb, pin['lb'])
                   if pin.get('ok') and pin.get('lb') is not None else lb)
            if lpb > lb:
                p = self._lp_no_proof(lpb - 1)
                if p is None:
                    lpb = lb
            lb = lpb
        else:
            self.pin = dict(ok=True, lb=lb, ub=lb, solves=0, param=None)

        if self.use_lp_sched and lb < ub:
            got = self._lp_schedule_at(lb)
            if got is not None:
                sched, mach = got
                ub = lb
                self.stats['lp_sched'] += 1

        if self.use_lns and lb < ub and ub - lb >= 2:
            ub2, s2, m2, st = lns_drop(
                self.inst, ub, sched, mach, budget=self.lns_budget,
                kmax=self.lns_kmax, tlim=self.lns_tlim, seed=0,
                stall=self.lns_stall)
            self.lns_stats = st
            self.stats['lns_used'] += 1
            if (ub2 < ub and check_schedule(self.inst, ub2, s2, m2)):
                ub, sched, mach = ub2, s2, m2
            if ub == lb:
                self.stats['lns_exact'] += 1

        self.lb0, self.ub0 = lb, ub
        return lb, ub, sched, mach

    # ------------------------------------------------------------ oracle
    def _decide(self, h):
        rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
                  hull_disc=4, hull_on=True)
        try:
            v, st = rdf.decide(budget=self.per_query_lp,
                               nodecap=self.per_query_nodes)
        except Exception:
            v, st = None, rdf._stats('exception')
        self.last_oracle = rdf
        return v, st, rdf

    def _accept_yes(self, rdf, h):
        n, p = self.inst['n'], self.inst['p']
        cmax = max(rdf.schedule[i] + p[i] for i in range(n))
        if cmax > h or not check_schedule(self.inst, cmax,
                                          rdf.schedule, rdf.machine):
            return False
        if cmax < self.opt:
            self.opt = cmax
            self.schedule = list(rdf.schedule)
            self.machine = list(rdf.machine)
        return True

    def _final_proof(self):
        p = self._ensure_lb_proof(self.lb)
        if p is not None:
            self.lb_proof = p
            self.certified = True
            self.stats['proof_final'] += 1
            return True
        v, st, rdf = self._decide(self.lb - 1)
        self.queries += 1
        self._absorb(st)
        self._record(self.lb - 1, v, st)
        if v is False:
            self.no_states[self.lb - 1] = rdf
            self.lb_proof = OracleProof(rdf)
            self.certified = True
            self.stats['proof_final'] += 1
            return True
        return False

    def optimize(self):
        lb, ub, sched, mach = self.initial_bounds()
        if ub is None:
            return self._result()
        self.lb, self.opt = lb, ub
        self.schedule, self.machine = sched, mach
        self.lb0, self.ub0 = lb, ub

        if self.use_proof:
            if lb == ub:
                self._final_proof()
                return self._result()
        else:
            if lb == ub:
                v, st, rdf = self._decide(ub - 1)
                self.queries += 1
                self._absorb(st)
                self._record(ub - 1, v, st)
                if v is False:
                    self.no_states[ub - 1] = rdf
                    self.lb_proof = OracleProof(rdf)
                    self.certified = True
                return self._result()

        while self.lb < self.opt and self.queries < self.max_queries:
            if self.opt - self.lb <= self.scan_cap:
                h = self.lb
                self.stats['scan_q'] += 1
            else:
                h = (self.lb + self.opt) // 2
                self.stats['bin_q'] += 1
            v, st, rdf = self._decide(h)
            self.queries += 1
            self._absorb(st)
            self._record(h, v, st)
            if v is True:
                self._accept_yes(rdf, h)
            elif v is False:
                self.lb = max(self.lb, h + 1)
                self.no_states[h] = rdf
                self.lb_proof = OracleProof(rdf)
                self._record_proof(self.lb_proof)
            else:
                self.unknown += 1
                self._recover_unknown(h)

        if self.lb == self.opt:
            if self.use_proof:
                self._final_proof()
            elif (self.opt - 1) not in self.no_states:
                v, st, rdf = self._decide(self.opt - 1)
                self.queries += 1
                self._absorb(st)
                self._record(self.opt - 1, v, st)
                if v is False:
                    self.no_states[self.opt - 1] = rdf
                    self.lb_proof = OracleProof(rdf)
                    self.certified = True
            else:
                self.lb_proof = OracleProof(self.no_states[self.opt - 1])
                self.certified = True
        return self._result()


def run(cls, inst, known, name, idx, **kw):
    t0 = time.time()
    co = cls(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['lifts'] = b.get('lifts')
    r['drops'] = b.get('drops')
    r['pin_lb'] = p.get('lb')
    r['pin_ub'] = p.get('ub')
    r['pin_solves'] = p.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                              'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r
