"""AQC-ALC: approximate-query cover ALC (v8.1 candidate).

Combines three ingredients on top of v7.1 QNC:

1. cover cut  gamma(E): sum_{c in E} z_c >= 1  from a leaf quorum E;
2. active unit-core probing at the root, ranked by the fractional LP
   solution (UCP idea), with a pair of disjoint unit cores on one job
   closing the instance immediately;
3. violation-gated root re-solve: z(E) is the cheap approximate query;
   only a violated cut buys an exact root LP.

The root loop is:

    solve root -> if infeasible: NO
               -> if integral: YES
               -> probe top-ranked unit atoms (<= cap)
                    pair -> NO
                    unit -> force + cut, restart
               -> if no unit found: fall back to QCC DFS
"""
import sys, time, collections
sys.path[:0] = ['exp/v81', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
from qnc import Budget, farkas_int
from qcc2 import QCC2
from qcc import cols_of, Closed
from cert import verify


class PairClosed(Exception):
    pass


class AQC(QCC2):
    def __init__(self, inst, h, probe_on=True, probe_jobs=2, probe_cap=8,
                 probe_gate=True, window_on=False, **kw):
        super().__init__(inst, h, **kw)
        self.probe_on = probe_on
        self.probe_jobs = probe_jobs
        self.probe_cap = probe_cap
        self.probe_gate = probe_gate
        self.window_on = window_on
        self.probe_off = False
        self.probes = 0
        self.probe_units = []
        self.pair_witness = None
        self.pairs = 0
        self.window_tries = 0
        self._start_cols = collections.defaultdict(list)
        for c, key in enumerate(self.lp.cols):
            self._start_cols[(key[0], key[-1])].append(c)

    # ------------------------------------------------------------- probing
    def _cut_degree(self):
        inc = collections.Counter()
        for (i, j, t) in self.lp.cuts:
            inc[i] += 1; inc[j] += 1
        return inc

    def _support(self, z):
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

    def _probe_delete(self, E):
        """Solve the current root LP with columns E deleted; 1 LP."""
        if self.lp_solves >= self.budget:
            raise Budget
        bounds = [(0, 1)] * self.lp.N
        for i, S in self.force.items():
            for key, c in self.lp.idx.items():
                if key[0] == i and key[-1] not in S:
                    bounds[c] = (0, 0)
        for key in E:
            for c in self._start_cols[key]:
                bounds[c] = (0, 0)
        res = self.lp.solve(bounds)
        self.lp_solves += 1
        self.probes += 1
        if res.status != 2:
            return False, None, None
        cert, slack = farkas_int(self.lp, set(E))
        if cert is None:
            return False, None, None
        # essential scope of the probe
        Ep = frozenset(key for cc, key in enumerate(self.lp.cols)
                       if key in set(E) and slack[cc] < 0)
        if not verify(self.inst, self.h, cert, forbid=Ep,
                      elig_aware=self.elig):
            return False, None, None
        self.last_sigma = slack
        return True, cert, Ep

    def _learn_probe(self, E, cert):
        self.leaves.append((frozenset(E), frozenset(E), cert))
        self._learn_cover_only(E)
        jobs = {i for i, t in E}
        if len(jobs) == 1:
            i = next(iter(jobs)); ts = frozenset(t for _, t in E)
            new = ts & self.force.get(i, self.domain(i))
            self.force[i] = new
            return 'empty' if not new else 'force'
        return 'cover'

    def _learn_cover_only(self, E):
        key = frozenset(E)
        if key in self._cover_seen:
            return
        self._cover_seen.add(key)
        self._add_covers(E)
        self.cover_added += 1

    def _probe_root(self, z):
        """Return 'pair' | 'unit' | 'window' | None.  May raise Closed."""
        if (not self.probe_on or self.probe_off or self.probes >= self.probe_cap):
            return None
        for _, _, i, atoms in self._rank_jobs(z)[:self.probe_jobs]:
            units = []
            for mass, t in atoms[:2]:
                ok, cert, Ep = self._probe_delete({(i, t)})
                if ok and len(Ep) == 1:
                    units.append((t, cert, Ep))
                elif not ok and not units and self.probe_gate:
                    # first probe of the first job already feasible: the LP
                    # is not fragile, stop probing this root
                    self.probe_off = True
                    return None
            if len(units) == 2 and units[0][0] != units[1][0]:
                self.pairs += 1
                self.pair_witness = (i, units[0][0], units[1][0])
                for t, cert, Ep in units:
                    self._learn_probe(Ep, cert)
                raise PairClosed
            if units:
                t, cert, Ep = units[0]
                st = self._learn_probe(Ep, cert)
                self.probe_units.append((i, t))
                if st == 'empty':
                    raise Closed
                # force/cut changed: exact root query
                self.restarts += 1
                self._check_root()
                return 'unit'
        return None

    # -------------------------------------------------------------- search
    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        try:
            v, why = self._branch([(0, 1)] * self.lp.base.N, 0, nodecap,
                                  max_rounds, topk)
        except PairClosed:
            v, why = False, 'pair'
        except Closed:
            v, why = False, 'cover-root'
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def _branch(self, bounds, depth, nodecap, max_rounds, topk):
        # at a feasible root, try active probes before branching
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
            if depth == 0 and self.root_z is None:
                self.root_z = np.asarray(z)
            if depth == 0:
                acted = self._probe_root(z)
                if acted == 'unit':
                    continue
            frac.sort()
            _, cc, i, t = frac[0]
            times = sorted(self.domain(i))
            s = 0.0; mid = t
            for tt in times:
                s += sum(z[self.lp.idx[(i, k, tt)]]
                         for k in self.lp.base.elig[i]
                         if (i, k, tt) in self.lp.idx) if self.elig \
                     else z[self.lp.idx[(i, tt)]]
                if s >= 0.5:
                    mid = tt; break
            if mid >= times[-1]:
                mid = times[-1] - 1
            lo = list(bounds); hi2 = list(bounds)
            for tt in times:
                if self.elig:
                    for k in self.lp.base.elig[i]:
                        if (i, k, tt) in self.lp.idx:
                            c2 = self.lp.idx[(i, k, tt)]
                            if tt > mid: lo[c2] = (0, 0)
                            else: hi2[c2] = (0, 0)
                else:
                    c2 = self.lp.idx[(i, tt)]
                    if tt > mid: lo[c2] = (0, 0)
                    else: hi2[c2] = (0, 0)
            a, why = self._branch(lo, depth + 1, nodecap, max_rounds, topk)
            if a is not False:
                return a, why
            return self._branch(hi2, depth + 1, nodecap, max_rounds, topk)

    def _stats(self, why):
        st = super()._stats(why)
        if why in ('pair', 'cover-root'):
            st['verdict'] = False
        st.update(probes=self.probes, probe_units=self.probe_units,
                  pairs=self.pairs, pair_witness=self.pair_witness,
                  probe_off=self.probe_off)
        return st
