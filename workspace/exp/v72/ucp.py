"""v7.2 UCP-ALC: unit-core probing on top of v7.1 QNC-ALC.

v7.1 only extracts a Farkas certificate when a node LP is *infeasible*.  A
feasible node therefore yields no certificate, even though the LP is the
best possible oracle for a counterfactual question:

    forbid one start (i,t) of the current LP -- is the result still feasible?

If the answer is no, the exact Farkas certificate is a *unit core*: every
feasible schedule must start job i at t.  This is a globally valid clause,
exactly the |E|=1 case of v7.1's quorum, but obtained without ever visiting
an infeasible node.  Two unit cores on the same job at different starts are
a contradiction, so the instance is NO at the root.

The probe schedule is deterministic (no RNG):
  * only converged lazy-SD LPs are probed;
  * jobs are ranked by (# incident SD cuts, |fractional support| == 2, id);
  * within a job the two starts are taken in decreasing LP mass.
This is the method-of-conditional-expectations reading of a random prober
that samples a start from the LP distribution: the first probe is the mode,
the second the runner-up, and jobs with the most tight SD rows are tried
first.  We do not claim the surrogate equals the true success probability;
we measure the gap (forced-atom precision) in the experiments.

Fallback is unchanged v7.1: median branching, leaf Farkas extraction,
quorum clause, force and audit.
"""
import sys
sys.path[:0] = ['exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import collections
import numpy as np
from qnc import QNC, Budget, farkas_int
from cert import verify


class UCP(QNC):
    def __init__(self, inst, h, probe_on=True, probe_jobs=1,
                 probe_cap=8, probe_gate=True,
                 use_force=False, **kw):
        super().__init__(inst, h, **kw)
        self.probe_on = probe_on
        self.probe_jobs = probe_jobs
        self.probe_cap = probe_cap
        self.probe_gate = probe_gate
        self.use_force = use_force
        self.probe_off = False
        self.probes = 0                 # LP solves spent on probing
        self.probe_jobs_tried = 0
        self.unit_cores = []            # (job, start, cert)
        self.pairs = 0                  # contradictory unit-core pairs
        self.cert_fail_probe = 0
        self.pair_witness = None          # (job, t1, t2) for a pair NO
        self._converged = False
        self._start_cols = collections.defaultdict(list)
        for cc, key in enumerate(self.lp.cols):
            self._start_cols[(key[0], key[-1])].append(cc)

    # ------------------------------------------------------------- solving
    def _solve(self, bounds, max_rounds, topk):
        """QNC._solve, but remember whether the lazy SD LP converged."""
        self._converged = False
        res = None
        for _ in range(max_rounds):
            if self.lp_solves >= self.budget:
                raise Budget
            res = self.lp.solve(bounds)
            self.lp_solves += 1
            if res.status != 0:
                return res, None
            viol = self.lp.separate(res.x, topk=topk)
            if not viol:
                self._converged = True
                return res, res.x
            for _, i, j, t in viol:
                if (i, j, t) not in self.lp.cutset:
                    self.lp.cutset.add((i, j, t))
                    self.lp.cuts.append((i, j, t))
        return res, (res.x if res is not None and res.status == 0 else None)

    # -------------------------------------------------------------- probing
    def _cut_degree(self):
        inc = collections.Counter()
        for (i, j, t) in self.lp.cuts:
            inc[i] += 1
            inc[j] += 1
        return inc

    def _support(self, z):
        """Start-time mass per job.  For eligibility-aware LPs the columns
        (i,k,t) are aggregated over machines, because a unit core is a
        statement about the start time, not about one machine copy."""
        agg = collections.defaultdict(float)
        for c, key in enumerate(self.lp.cols):
            if z[c] > 1e-7:
                agg[(key[0], key[-1])] += float(z[c])
        supp = collections.defaultdict(list)
        for (i, t), mass in agg.items():
            if 1e-7 < mass < 1 - 1e-7:
                supp[i].append((mass, t))
        return supp

    def _rank_jobs(self, z):
        """Deterministic job order for pair probing.

        (1) two fractional atoms first: probing both then covers the whole
            fractional support of the job, so two failures are a proof;
        (2) more incident tight SD cuts first;
        (3) smaller job id.
        """
        supp = self._support(z)
        inc = self._cut_degree()
        cand = []
        for i, atoms in supp.items():
            if len(atoms) < 2:
                continue
            atoms.sort(key=lambda a: (-a[0], a[1]))
            cand.append((len(atoms) != 2, -inc[i], i, atoms))
        cand.sort(key=lambda x: (x[0], x[1], x[2]))
        return cand

    def _probe_one(self, bounds, i, t):
        """Delete every column with start (i,t); return (unit?, cert).

        Counting one LP.  In an eligibility-aware LP this removes all
        machine copies of the start, which is what the clause s_i=t means.
        """
        if self.lp_solves >= self.budget:
            raise Budget
        b = list(bounds)
        for cc in self._start_cols[(i, t)]:
            b[cc] = (0, 0)
        res = self.lp.solve(b)
        self.lp_solves += 1
        self.probes += 1
        if res.status != 2:
            return False, None
        cert, slack = farkas_int(self.lp, {(i, t)})
        if cert is None:
            self.cert_fail_probe += 1
            return False, None
        if not verify(self.inst, self.h, cert, forbid={(i, t)},
                      elig_aware=self.elig):
            self.cert_fail_probe += 1
            return False, None
        return True, cert

    def _learn_unit(self, i, t, cert):
        """Record a unit clause, intersect the forced domain.  Returns
        'empty' if the intersection became empty (that is a NO proof)."""
        key = (i, t)
        self.leaves.append((frozenset({key}), frozenset({key}), cert))
        self.clauses.append(frozenset({key}))
        self.unit_cores.append((i, t, cert))
        new = {t} & set(self.force.get(i, self.domain(i)))
        self.force[i] = frozenset(new)
        return 'empty' if not new else 'force'

    def _probe_pair(self, bounds, i, atoms):
        """Probe the two heaviest fractional starts of job i.

        Returns ('pair', [...]) for two unit cores, ('force', t, cert) for
        one, or ('none', None, None)."""
        units = []
        for k, (mass, t) in enumerate(atoms[:2]):
            ok, cert = self._probe_one(bounds, i, t)
            if ok:
                units.append((t, cert))
            elif k == 0 and self.probe_gate:
                # the first probe of the first job is feasible: the LP is
                # not fragile, abandon probing instead of paying for a
                # full failed portfolio at every node.
                self.probe_off = True
                break
        if len(units) == 2:
            return 'pair', units, None
        if len(units) == 1:
            return 'force', units[0][0], units[0][1]
        return 'none', None, None

    # --------------------------------------------------------------- search
    def _branch(self, bounds, depth, nodecap, max_rounds, topk):
        while True:
            bounds, _ = self._apply_force(bounds)
            i0 = self._empty_job(bounds) if self.use_empty else None
            if i0 is not None:
                self.empty_prunes += 1
                return False, 'empty'
            F = self._forbids(bounds)
            for E in self.clauses:
                if E <= F:
                    self.prunes += 1
                    return False, 'clause'
            self.nodes += 1
            if self.nodes > nodecap:
                raise Budget
            res, z = self._solve(bounds, max_rounds, topk)
            if res.status == 2:
                self._learn(F)
                return False, 'no'
            if z is None:
                return None, 'roundcap'
            frac = [(abs(z[cc] - 0.5), cc, key[0], key[-1])
                    for cc, key in enumerate(self.lp.cols)
                    if 1e-7 < z[cc] < 1 - 1e-7]
            if not frac:
                return True, 'yes'

            # ---- counterfactual unit-core probing on the converged LP ----
            if (self.probe_on and self._converged and not self.probe_off
                    and depth == 0 and self.probes < self.probe_cap):
                acted = False
                for _, _, i, atoms in self._rank_jobs(z)[:self.probe_jobs]:
                    self.probe_jobs_tried += 1
                    kind, a, cert = self._probe_pair(bounds, i, atoms)
                    if kind == 'pair':
                        # two globally forced starts on one job: contradiction
                        for t, c in a:
                            self._learn_unit(i, t, c)
                        self.pairs += 1
                        self.pair_witness = (i, a[0][0], a[1][0])
                        return False, 'pair'
                    if kind == 'force' and self.use_force:
                        st = self._learn_unit(i, a, cert)
                        if st == 'empty':
                            return False, 'force_empty'
                        acted = True
                        break
                if acted:
                    continue

            # -------------------- v7.1 median branching fallback ----------
            frac.sort()
            _, cc, i, t = frac[0]
            times = sorted(self.domain(i))
            s = 0.0
            mid = t
            for tt in times:
                if self.elig:
                    s += sum(z[self.lp.idx[(i, k, tt)]]
                             for k in self.lp.base.elig[i]
                             if (i, k, tt) in self.lp.idx)
                else:
                    s += z[self.lp.idx[(i, tt)]]
                if s >= 0.5:
                    mid = tt
                    break
            if mid >= times[-1]:
                mid = times[-1] - 1
            lo = list(bounds)
            hi2 = list(bounds)
            for tt in times:
                if self.elig:
                    for k in self.lp.base.elig[i]:
                        if (i, k, tt) in self.lp.idx:
                            c2 = self.lp.idx[(i, k, tt)]
                            if tt > mid:
                                lo[c2] = (0, 0)
                            else:
                                hi2[c2] = (0, 0)
                else:
                    c2 = self.lp.idx[(i, tt)]
                    if tt > mid:
                        lo[c2] = (0, 0)
                    else:
                        hi2[c2] = (0, 0)
            a, why = self._branch(lo, depth + 1, nodecap, max_rounds, topk)
            if a is not False:
                return a, why
            return self._branch(hi2, depth + 1, nodecap, max_rounds, topk)

    # ---------------------------------------------------------------- stats
    def _stats(self, why):
        st = super()._stats(why)
        st.update(probes=self.probes, probe_jobs=self.probe_jobs_tried,
                  unit_cores=[(i, t) for i, t, _ in self.unit_cores],
                  pairs=self.pairs, cert_fail_probe=self.cert_fail_probe,
                  pair_witness=self.pair_witness)
        return st

    def audit_full(self):
        """QNC leaf replay plus the pair/force contradiction witness."""
        if not self.audit():
            return False
        unit = {}
        for F, E, c in self.leaves:
            if len(E) == 1:
                i, t = next(iter(E))
                unit[(i, t)] = c
        if self.pair_witness is not None:
            i, t1, t2 = self.pair_witness
            return t1 != t2 and (i, t1) in unit and (i, t2) in unit
        if any(len(S) == 0 for S in self.force.values()):
            return True
        return True
