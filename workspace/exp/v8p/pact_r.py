"""v9.0 PACT-R: PACT with residual certificates and certified ledgers.

This module keeps PACT's outer bracket, LP pin, LP rounding, LNS, STAB and
optional GENETIC-UB, and replaces the boolean+payload probe by the typed
contract of residual.py.  In the default mode every probe is a complete
residual search (depthcap=None, nodecap=None); if the search nevertheless
returns OPEN (a failed Farkas attempt or an unassigned machine leaf), the
probe falls back to CHD and the trace records the engine.
"""
import sys
import time

sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof, OracleProof, bound_lb
from sage import SAGE
from rdf import check_schedule
from residual import ResidualSearch, ClosedProof, ResidualProof, decide


class PACT_R(SAGE):
    def __init__(self, inst, mode='complete', probe_budget=None,
                 probe_depth=None, use_ga=True, **kw):
        super().__init__(inst, use_ga=use_ga, **kw)
        self.mode = mode
        self.probe_budget = probe_budget
        self.probe_depth = probe_depth
        self.res_calls = 0
        self.res_no = 0
        self.res_yes = 0
        self.res_open = 0
        self.res_lp = 0
        self.res_cert_lp = 0
        self.res_nodes = 0
        self.res_holes = 0
        self.res_ledgers = []
        self.steps = []
        self.probe_log = []
        self.total_cert = None
        self.total_audit = False
        self.stats.update(res_no=0, res_yes=0, res_open=0,
                          res_fallback=0)

    def _record_res(self, r):
        self.res_calls += 1
        self.res_lp += r['lp_solves']
        self.res_cert_lp += r.get('cert_lp', 0)
        self.res_nodes += r['nodes']
        self.res_holes += r.get('holes', 0)
        if r.get('proof') is not None:
            self.res_ledgers.append(r['proof'].ledger)
        return r

    def _probe(self, h):
        n0 = len(self.steps)
        out = self._probe_inner(h)
        eng = (self.steps[-1].get('engine')
               if len(self.steps) > n0 else None)
        self.probe_log.append(dict(h=h, v=out[0], engine=eng))
        return out

    def _probe_inner(self, h):
        if self.mode == 'sage':
            return super()._probe(h)
        r = self._record_res(decide(self.inst, h,
                                    depthcap=self.probe_depth,
                                    nodecap=self.probe_budget))
        if r['verdict'] is False:
            self.res_no += 1
            self.stats['res_no'] += 1
            p = r['proof']
            if not isinstance(p, Proof) or not p.audit_rdf():
                self.stats['res_fallback'] += 1
                return self._fallback(h, r)
            self._record_proof(p)
            self.steps.append(dict(h=h, v=False, proof=p,
                                   engine='residual',
                                   ledger=dict(p.ledger)))
            return False, p
        if r['verdict'] is True:
            self.res_yes += 1
            self.stats['res_yes'] += 1
            s, m = r['schedule']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            if not check_schedule(self.inst, cmax, s, m):
                self.stats['res_fallback'] += 1
                return self._fallback(h, r)
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='residual'))
            return True, (s, m, cmax)
        self.res_open += 1
        self.stats['res_open'] += 1
        return self._fallback(h, r)

    def _fallback(self, h, r):
        """A residual is valuable, but a bracket step needs a verdict.

        For the 252-instance certificate benchmark the residual is kept
        in the ledger and CHD is asked once, so the outer bracket never
        loses a step.  The report separates res_open from Q.
        """
        if self.use_ga:
            from sage import ga_schedule
            got, st = ga_schedule(self.inst, h, pop=self.ga_pop,
                                  gens=self.ga_gens,
                                  budget=self.ga_budget)
            self.ga_stats.append(st)
            if got is not None:
                s, m = got
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                if check_schedule(self.inst, cmax, s, m):
                    self.stats['ga_yes'] += 1
                    self.steps.append(dict(h=h, v=True, schedule=s,
                                           machine=m, cmax=cmax,
                                           engine='ga'))
                    return True, (s, m, cmax)
            self.stats['ga_no'] += 1
        self.stats['res_fallback'] += 1
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            p = rdf if isinstance(rdf, Proof) else OracleProof(rdf)
            self.steps.append(dict(h=h, v=False, proof=p, engine='chd'))
            return False, p
        if v is True:
            s, m = rdf.schedule, rdf.machine
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='chd'))
            return True, (s, m, cmax)
        self.steps.append(dict(h=h, v=None, engine='chd'))
        return v, rdf

    def initial_bounds(self):
        b = super().initial_bounds()
        self.init_lb, self.init_ub = b[0], b[1]
        self.init_schedule = list(b[2]) if b[2] is not None else None
        self.init_machine = list(b[3]) if b[3] is not None else None
        return b

    def optimize(self):
        self.steps = []
        lb, ub, sched, mach = self.initial_bounds()
        if ub is None:
            return self._result()
        self.steps = []
        self.lb, self.opt = lb, ub
        self.schedule, self.machine = sched, mach
        self.lb0, self.ub0 = lb, ub
        self.pin_lp_total = getattr(self, 'pin_lp', 0)
        if self.lb == self.opt:
            self._final_proof()
            self._build_total()
            return self._result()
        limit = max(self.max_queries, (self.ub0 - self.lb0) + 1)
        while self.lb < self.opt and self.queries < limit:
            if self.opt - self.lb <= self.scan_cap:
                h = self.lb
                self.stats['scan_q'] += 1
            else:
                h = (self.lb + self.opt) // 2
                self.stats['bin_q'] += 1
            v, payload = self._probe(h)
            if v is True:
                if isinstance(payload, tuple):
                    s, m, cmax = payload
                else:
                    rdf = payload
                    s, m = rdf.schedule, rdf.machine
                    cmax = max(s[i] + self.inst['p'][i]
                               for i in range(self.inst['n']))
                if cmax < self.opt and check_schedule(self.inst, cmax, s, m):
                    self.schedule = list(s)
                    self.machine = list(m)
                    self.opt = cmax
            elif v is False:
                self.lb = max(self.lb, h + 1)
                if isinstance(payload, Proof):
                    self._record_proof(payload)
                    self.lb_proof = payload
                else:
                    self.no_states[h] = payload
                    self.lb_proof = payload
            else:
                self.unknown += 1
                self._recover_unknown(h)
        if self.lb == self.opt:
            self._final_proof()
        self._build_total()
        return self._result()

    def _build_total(self):
        if not self.certified or self.lb != self.opt:
            self.total_cert = None
            self.total_audit = False
            return
        init_lb_proof = self.proofs.get(self.lb0 - 1)
        init_bound = bound_lb(self.inst)
        cert = TotalTraceR(
            self.inst, self.opt, self.lb0, self.ub0, init_lb_proof,
            init_bound if init_lb_proof is None else None,
            self.init_schedule, self.init_machine, self.steps,
            self.lb_proof, self.schedule, self.machine)
        self.total_cert = cert
        self.total_audit = bool(cert.audit_rdf())
        if not self.total_audit:
            self.certified = False

    def _result(self):
        r = super()._result()
        r.update(total_audit=self.total_audit,
                 res_calls=self.res_calls, res_no=self.res_no,
                 res_yes=self.res_yes, res_open=self.res_open,
                 res_lp=self.res_lp, res_cert_lp=self.res_cert_lp,
                 res_nodes=self.res_nodes, res_holes=self.res_holes,
                 res_ledgers=self.res_ledgers,
                 probe_log=self.probe_log,
                 total_kind=getattr(getattr(self, 'total_cert', None),
                                    'kind', None))
        return r


class TotalTraceR(Proof):
    """Total trace with the same contract as PACT's TotalTrace."""

    kind = 'total-trace'

    def __init__(self, inst, opt, lb0, ub0, init_lb_proof, init_bound,
                 init_schedule, init_machine, steps, final_lb_proof,
                 final_schedule, final_machine):
        super().__init__(inst, opt)
        self.opt = opt
        self.lb0 = lb0
        self.ub0 = ub0
        self.init_lb_proof = init_lb_proof
        self.init_bound = init_bound
        self.init_schedule = (list(init_schedule)
                              if init_schedule is not None else None)
        self.init_machine = (list(init_machine)
                             if init_machine is not None else None)
        self.steps = list(steps)
        self.final_lb_proof = final_lb_proof
        self.final_schedule = (list(final_schedule)
                               if final_schedule is not None else None)
        self.final_machine = (list(final_machine)
                              if final_machine is not None else None)

    def _sched_ok(self, h, s, m):
        if s is None or m is None:
            return False
        cmax = max(s[i] + self.inst['p'][i]
                   for i in range(self.inst['n']))
        return cmax <= h and check_schedule(self.inst, cmax, s, m)

    def audit_rdf(self):
        try:
            if self.final_lb_proof is None:
                return False
            if self.final_lb_proof.h != self.opt - 1:
                return False
            if not self.final_lb_proof.audit_rdf():
                return False
            if not self._sched_ok(self.opt, self.final_schedule,
                                  self.final_machine):
                return False
            if not self._sched_ok(self.ub0, self.init_schedule,
                                  self.init_machine):
                return False
            if self.init_lb_proof is not None:
                if self.init_lb_proof.h != self.lb0 - 1:
                    return False
                if not self.init_lb_proof.audit_rdf():
                    return False
            elif self.init_bound is None:
                return False
            elif self.init_bound != bound_lb(self.inst):
                return False
            elif self.lb0 > self.init_bound:
                return False
            if self.lb0 > self.ub0:
                return False
            lb, ub = self.lb0, self.ub0
            for step in self.steps:
                h = step['h']
                v = step['v']
                if not (lb <= h < ub):
                    return False
                if v is False:
                    p = step.get('proof')
                    if p is None or p.h != h or not p.audit_rdf():
                        return False
                    lb = max(lb, h + 1)
                elif v is True:
                    s = step.get('schedule')
                    m = step.get('machine')
                    if not self._sched_ok(h, s, m):
                        return False
                    cmax = max(s[i] + self.inst['p'][i]
                               for i in range(self.inst['n']))
                    ub = min(ub, cmax)
                else:
                    return False
            return lb == ub == self.opt
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def run_pact_r(inst, known, name, idx, **kw):
    t0 = time.time()
    co = PACT_R(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = p.get('lb')
    r['pin_solves'] = p.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['ga_stats'] = getattr(co, 'ga_stats', [])
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                              'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r
