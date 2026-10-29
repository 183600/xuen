"""PACT-SAT: certified PACT bracket with a SAT witness oracle for YES probes.

The LP branch-and-bound side keeps all NO refutations (postconditions as
core clauses).  The SAT side is used only to produce YES witnesses; it never
contributes a NO claim, so its soundness is irrelevant.  Every SAT schedule is
rechecked by the same RDF checker used by PACT.
"""
import sys
import time

sys.path[:0] = ['exp/v8t', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from po import heads_tails
from rdf import check_schedule
try:
    from pysat.solvers import Cadical153
    HAVE_PYSAT = True
except Exception:
    Cadical153 = None
    HAVE_PYSAT = False
from pact import PACT, pact_decide, ga_schedule, OracleProof


class SATWitness:
    def __init__(self, inst):
        self.inst = inst
        self.calls = 0
        self.yes = 0
        self.unknown = 0
        self.time = 0.0
        self.last = None

    def encode(self, h):
        inst = self.inst
        n, m, p = inst['n'], inst['m'], inst['p']
        est, q = heads_tails(inst, 0, [0] * n)
        var = {}
        ranges = {}
        for i in range(n):
            lo, hi = est[i], h - q[i] - p[i]
            if hi < lo:
                return None, None
            for k in inst['elig'][i]:
                for t in range(lo, hi + 1):
                    var[(i, k, t)] = len(var) + 1
        clauses = []

        def add(cl):
            s = set(cl)
            if any(-l in s for l in s):
                return
            clauses.append(sorted(s))

        for i in range(n):
            lits = [v for (j, k, t), v in var.items() if j == i]
            if not lits:
                return None, None
            add(lits)
            for a in range(len(lits)):
                for b in range(a + 1, len(lits)):
                    add([-lits[a], -lits[b]])
        for i in range(n):
            vi = [(k, t, v) for (ii, k, t), v in var.items() if ii == i]
            for j in inst['succ'][i]:
                vj = [(l, u, v) for (jj, l, u), v in var.items() if jj == j]
                for k, t, a in vi:
                    for l, u, b in vj:
                        if u < t + p[i]:
                            add([-a, -b])
        for k in range(m):
            jobs = [i for i in range(n) if k in inst['elig'][i]]
            for x in range(len(jobs)):
                i = jobs[x]
                vi = [(t, v) for (ii, kk, t), v in var.items()
                      if ii == i and kk == k]
                for y in range(x + 1, len(jobs)):
                    j = jobs[y]
                    vj = [(u, v) for (jj, kk, u), v in var.items()
                          if jj == j and kk == k]
                    for t, a in vi:
                        for u, b in vj:
                            if t < u + p[j] and u < t + p[i]:
                                add([-a, -b])
        return clauses, var

    def solve(self, h):
        t0 = time.time()
        self.calls += 1
        if not HAVE_PYSAT:
            self.time += time.time() - t0
            self.unknown += 1
            return None
        clauses, var = self.encode(h)
        if clauses is None:
            self.time += time.time() - t0
            self.unknown += 1
            return None
        s = Cadical153(bootstrap_with=clauses, with_proof=False)
        ok = s.solve()
        model = s.get_model() if ok else None
        s.delete()
        if not ok:
            self.time += time.time() - t0
            self.unknown += 1
            return None
        starts = [None] * self.inst['n']
        mach = [None] * self.inst['n']
        for (i, k, t), v in var.items():
            if model[v - 1] > 0:
                if starts[i] is not None:
                    self.time += time.time() - t0
                    self.unknown += 1
                    return None
                starts[i] = t
                mach[i] = k
        if any(x is None for x in starts):
            self.time += time.time() - t0
            self.unknown += 1
            return None
        cmax = max(starts[i] + self.inst['p'][i]
                   for i in range(self.inst['n']))
        if not check_schedule(self.inst, cmax, starts, mach):
            self.time += time.time() - t0
            self.unknown += 1
            return None
        self.time += time.time() - t0
        self.yes += 1
        return starts, mach, cmax


class PACTSAT(PACT):
    phase1_budget = 0.05
    sat_min_n = 16

    def __init__(self, inst, **kw):
        super().__init__(inst, **kw)
        if not HAVE_PYSAT:
            self.phase1_budget = None
        self.sat = SATWitness(inst)
        self.stats.update(sat_calls=0, sat_yes=0, sat_unknown=0, sat_t=0.0)

    def _run_depth(self, h, d):
        r = pact_decide(self.inst, h, depthcap=d,
                        nodecap=self.pact_nodecap,
                        timelimit=getattr(self, 'phase1_budget', None))
        self.pact_calls += 1
        self.pact_lp += r['lp_solves']
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r['nodes']
        return r

    def _probe(self, h):
        """PACT probe with a SAT YES oracle inserted before complete search."""
        if self.pact_mode == 'closing' and self.opt - self.lb > 1:
            return super()._probe(h)
        if self.pact_mode == 'closing':
            return super()._probe(h)
        # Phase 1: parameterized NO-first iterative deepening.
        if self.pact_depth is None:
            depth_list = []
        elif self.pact_iterative:
            depth_list = list(range(self.pact_depth + 1))
        else:
            depth_list = [self.pact_depth]
        for d in depth_list:
            r = self._run_depth(h, d)
            if r['verdict'] is False:
                self.pact_no += 1
                self.stats['pact_no'] += 1
                self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                       engine='pact', depth=d))
                return False, r['proof']
            if r['verdict'] is True:
                self.pact_yes += 1
                self.stats['pact_yes'] += 1
                s, m = r['schedule'], r['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.steps.append(dict(h=h, v=True, schedule=s,
                                       machine=m, cmax=cmax,
                                       engine='pact', depth=d))
                return True, (s, m, cmax)
            self.pact_unknown += 1
            self.stats['pact_unknown'] += 1
        # Phase 3: SAT witness oracle (before the expensive GA / complete search).
        got = None
        if self.inst['n'] >= getattr(self, 'sat_min_n', 0):
            got = self.sat.solve(h)
            self.stats['sat_calls'] += 1
        if got is not None:
            s, m, cmax = got
            self.stats['sat_yes'] += 1
            self.steps.append(dict(h=h, v=True, schedule=s,
                                   machine=m, cmax=cmax,
                                   engine='sat'))
            return True, (s, m, cmax)
        if self.inst['n'] >= getattr(self, 'sat_min_n', 0):
            self.stats['sat_unknown'] += 1
        # Phase 2: genetic upper side.
        if self.use_ga:
            got, st = ga_schedule(self.inst, h, pop=self.ga_pop,
                                  gens=self.ga_gens,
                                  budget=self.ga_budget)
            self.ga_stats.append(st)
            if got is not None:
                s, m = got
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.stats['ga_yes'] += 1
                self.steps.append(dict(h=h, v=True, schedule=s,
                                       machine=m, cmax=cmax,
                                       engine='ga'))
                return True, (s, m, cmax)
            self.stats['ga_no'] += 1
        # Phase 4: complete certificate search (no depth cap).
        if self.complete_fallback:
            self.stats['complete_fallback'] += 1
            r = pact_decide(self.inst, h, depthcap=None,
                            nodecap=None)
            self.pact_lp += r['lp_solves']
            self.pact_cert_lp += r.get('cert_lp', 0)
            self.pact_nodes += r['nodes']
            if r['verdict'] is False:
                self.pact_no += 1
                self.stats['pact_no'] += 1
                self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                       engine='complete'))
                return False, r['proof']
            if r['verdict'] is True:
                self.pact_yes += 1
                self.stats['pact_yes'] += 1
                s, m = r['schedule'], r['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.steps.append(dict(h=h, v=True, schedule=s,
                                       machine=m, cmax=cmax,
                                       engine='complete'))
                return True, (s, m, cmax)
        # Phase 5: CHD last resort.
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            self.steps.append(dict(h=h, v=False, proof=rdf,
                                   engine='chd'))
        elif v is True:
            s, m = rdf.schedule, rdf.machine
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='chd'))
        else:
            self.steps.append(dict(h=h, v=None, engine='chd'))
        return v, rdf

    def _result(self):
        r = super()._result()
        r['sat_calls'] = self.sat.calls
        r['sat_yes'] = self.sat.yes
        r['sat_unknown'] = self.sat.unknown
        r['sat_t'] = round(self.sat.time, 4)
        return r


def run_pact_sat(inst, known, name, idx, **kw):
    t0 = time.time()
    co = PACTSAT(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    r['sat_calls'] = co.sat.calls
    r['sat_yes'] = co.sat.yes
    r['sat_unknown'] = co.sat.unknown
    r['sat_t'] = round(co.sat.time, 4)
    r['sat_min_n'] = getattr(co, 'sat_min_n', None)
    r['phase1_budget'] = getattr(co, 'phase1_budget', None)
    b = getattr(co, 'chip', None) or {}
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = p.get('lb')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                              'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r
