"""DART-SAT: a SAT oracle with job selectors for dependency cores.

The encoding is the standard time-indexed fixed-horizon CSP.  Every clause
that mentions a job i is guarded by a selector s_i.  Solving under the
assumptions s_1=...=s_n=true is UNSAT exactly when the full fixed-horizon
instance is UNSAT.  When it is UNSAT, the solver's assumption core is a set
C of jobs such that the sub-instance induced by C is UNSAT: setting s_i=false
for i not in C removes every clause that mentions a dropped job, which is
precisely the restriction operation used by CoreNOProof.

The SAT side is used in two ways:

  * YES: decode the model, check it with check_schedule;
  * NO: extract C and hand it to the LP/DPLL side, which must produce a
    replayable BranchProof on the restricted instance.  The SAT core is only
    a dependency heuristic; it never contributes an unchecked NO claim.

All times are integers.  The oracle returns dicts:
  verdict  : True / False / None
  schedule : list or None
  machine  : list or None
  cmax     : int or None
  core_jobs: sorted list of job indices (subset of range(n)) or None
  core_size: int
  reason   : 'sat-yes' / 'sat-no' / 'sat-core' / 'cp' / 'empty' / ...
  t        : seconds
"""
import sys
import time

sys.path[:0] = ['exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from po import heads_tails
from rdf import check_schedule

from pysat.solvers import Cadical153


class SATCoreOracle:
    def __init__(self, inst, timelimit=None, min_n=0):
        self.inst = inst
        self.timelimit = timelimit
        self.min_n = min_n
        self.calls = 0
        self.yes = 0
        self.no = 0
        self.unknown = 0
        self.core_calls = 0
        self.core_size_sum = 0
        self.core_min = None
        self.last_core = None
        self.time = 0.0

    def _encode(self, h):
        inst = self.inst
        n, m, p = inst['n'], inst['m'], inst['p']
        est, q = heads_tails(inst, 0, [0] * n)

        sel = {i: i + 1 for i in range(n)}
        var = {}
        for i in range(n):
            lo, hi = est[i], h - q[i] - p[i]
            if lo > hi:
                return None, None, sel, ('cp', i)
            for k in inst['elig'][i]:
                for t in range(lo, hi + 1):
                    var[(i, k, t)] = n + len(var) + 1
        if not var:
            return None, None, sel, ('empty', None)

        clauses = []

        def add(cl, jobs):
            # Disable the clause if any job it mentions is dropped.
            cl = list(cl) + [-sel[i] for i in jobs if i in sel]
            s = set(cl)
            if any(-l in s for l in s):
                return
            clauses.append(sorted(s))

        for i in range(n):
            lits = [v for (j, k, t), v in var.items() if j == i]
            if not lits:
                return None, None, sel, ('empty', i)
            add(lits, [i])
            for a in range(len(lits)):
                for b in range(a + 1, len(lits)):
                    add([-lits[a], -lits[b]], [i])

        for i in range(n):
            vi = [(k, t, v) for (ii, k, t), v in var.items() if ii == i]
            for j in inst['succ'][i]:
                vj = [(l, u, v) for (jj, l, u), v in var.items()
                      if jj == j]
                for k, t, a in vi:
                    for l, u, b in vj:
                        if u < t + p[i]:
                            add([-a, -b], [i, j])

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
                                add([-a, -b], [i, j])
        return clauses, var, sel, None

    def solve(self, h, want_core=False):
        t0 = time.time()
        self.calls += 1
        clauses, var, sel, bad = self._encode(h)
        if clauses is None:
            self.time += time.time() - t0
            self.unknown += 1
            out = dict(verdict=None, schedule=None, machine=None, cmax=None,
                       core_jobs=None, core_size=0, reason='encode',
                       t=round(time.time() - t0, 5))
            if bad is not None and bad[0] == 'cp' and want_core:
                out.update(verdict=False, reason='cp',
                           core_jobs=[bad[1]], core_size=1)
                self.no += 1
                self.core_calls += 1
                self.core_size_sum += 1
                self.core_min = 1 if self.core_min is None else min(
                    self.core_min, 1)
                self.last_core = [bad[1]]
            return out

        assumptions = [sel[i] for i in range(self.inst['n'])]
        try:
            solver = Cadical153(bootstrap_with=clauses, with_proof=False)
            ok = solver.solve(assumptions=assumptions)
            model = solver.get_model() if ok else None
            core = None
            if not ok and want_core:
                core = solver.get_core()
            solver.delete()
        except Exception:
            self.time += time.time() - t0
            self.unknown += 1
            return dict(verdict=None, schedule=None, machine=None,
                        cmax=None, core_jobs=None, core_size=0,
                        reason='solver-error',
                        t=round(time.time() - t0, 5))

        if ok:
            starts = [None] * self.inst['n']
            mach = [None] * self.inst['n']
            for (i, k, t), v in var.items():
                if model[v - 1] > 0:
                    if starts[i] is not None:
                        self.time += time.time() - t0
                        self.unknown += 1
                        return dict(verdict=None, schedule=None,
                                    machine=None, cmax=None,
                                    core_jobs=None, core_size=0,
                                    reason='model', t=round(
                                        time.time() - t0, 5))
                    starts[i] = t
                    mach[i] = k
            if any(x is None for x in starts):
                self.time += time.time() - t0
                self.unknown += 1
                return dict(verdict=None, schedule=None, machine=None,
                            cmax=None, core_jobs=None, core_size=0,
                            reason='partial-model',
                            t=round(time.time() - t0, 5))
            cmax = max(starts[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            if not check_schedule(self.inst, cmax, starts, mach):
                self.time += time.time() - t0
                self.unknown += 1
                return dict(verdict=None, schedule=None, machine=None,
                            cmax=None, core_jobs=None, core_size=0,
                            reason='check', t=round(time.time() - t0, 5))
            self.time += time.time() - t0
            self.yes += 1
            return dict(verdict=True, schedule=starts, machine=mach,
                        cmax=cmax, core_jobs=None, core_size=0,
                        reason='sat-yes', t=round(time.time() - t0, 5))

        # UNSAT: map the selector core back to job indices.
        jobs = None
        if core:
            rev = {v: i for i, v in sel.items()}
            jobs = sorted({rev[l] for l in core if l in rev})
        self.time += time.time() - t0
        self.no += 1
        if jobs is not None:
            self.core_calls += 1
            self.core_size_sum += len(jobs)
            self.core_min = (len(jobs) if self.core_min is None
                             else min(self.core_min, len(jobs)))
            self.last_core = list(jobs)
        return dict(verdict=False, schedule=None, machine=None, cmax=None,
                    core_jobs=jobs, core_size=len(jobs) if jobs else 0,
                    reason='sat-core' if jobs else 'sat-no',
                    t=round(time.time() - t0, 5))

    def summary(self):
        return dict(calls=self.calls, yes=self.yes, no=self.no,
                    unknown=self.unknown, core_calls=self.core_calls,
                    core_size_avg=(self.core_size_sum / self.core_calls
                                   if self.core_calls else None),
                    core_min=self.core_min, last_core=self.last_core,
                    t=round(self.time, 4))
