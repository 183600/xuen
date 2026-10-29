"""v8.2 SQR-ALC: singleton-split quorum refutation on top of v7.1 QNC.

A split certificate for a node N is a pair of Farkas certificates for the
two sides of one domain split s_i = t vs s_i != t:

    Phi^-  proves  LP_N with column (i,t) deleted infeasible
           => every feasible schedule of N has s_i = t   (unit quorum)
    Phi^+  proves  LP_N with all other starts of i deleted infeasible
           => no feasible schedule of N has s_i = t
    both   => N is NO.

The search never has to branch to discover this pair: at a feasible node
the fractional LP solution ranks candidate atoms, and the two sides are
queried directly.  A one-sided answer is still useful: Phi^- forces
s_i=t globally, Phi^+ forbids s_i=t; the node is re-solved with the
shrunk domain.  Only when neither side closes does the algorithm fall
back to v7.1 median branching.

The ranking is the v7.2 UCP heuristic: prefer jobs with exactly two
fractional atoms, then more incident SD cuts, then the heavier atom.  It
is a deterministic cheap surrogate for "which split is most likely to be
a refutation"; the exact LP is the oracle.
"""
import sys, collections
sys.path[:0] = ['exp/v81', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
from qnc import QNC, Budget, farkas_int
from cert import verify


class SplitClosed(Exception):
    pass


class SQR(QNC):
    def __init__(self, inst, h, probe_on=True, probe_cap=4, probe_gate=False,
                 max_candidates=1, **kw):
        super().__init__(inst, h, **kw)
        self.probe_on = probe_on
        self.probe_cap = probe_cap
        self.probe_gate = probe_gate
        self.max_candidates = max_candidates
        self.probes = 0
        self.negative = 0
        self.forced = 0
        self.refuted = 0
        self.split_leaves = []       # (i,t,Phi-,Phi+)
        self.probe_off = False
        self._tried = set()
        self._start_cols = collections.defaultdict(list)
        for c, key in enumerate(self.lp.cols):
            self._start_cols[(key[0], key[-1])].append(c)

    # ------------------------------------------------------------ ranking
    def _cut_degree(self):
        inc = collections.Counter()
        for (i, j, t) in self.lp.cuts:
            inc[i] += 1; inc[j] += 1
        return inc

    def _rank(self, z):
        inc = self._cut_degree()
        supp = collections.defaultdict(list)
        for c, key in enumerate(self.lp.cols):
            if z[c] > 1e-7:
                supp[key[0]].append((float(z[c]), key[-1]))
        cand = []
        for i, atoms in supp.items():
            if len(atoms) < 2:
                continue
            atoms.sort(key=lambda a: (-a[0], a[1]))
            cand.append((len(atoms) != 2, -inc[i], i, atoms))
        cand.sort()
        return cand

    # ------------------------------------------------------------- probes
    def _solve_bounds(self, bounds):
        if self.lp_solves >= self.budget:
            raise Budget
        res = self.lp.solve(bounds)
        self.lp_solves += 1
        self.probes += 1
        return res

    def _probe(self, i, t):
        """Return ('refuted', certs) | ('forced', cert) | ('none', None)."""
        # negative side: delete s_i=t
        b = [(0, 1)] * self.lp.N
        for c in self._start_cols[(i, t)]:
            b[c] = (0, 0)
        res = self._solve_bounds(b)
        if res.status != 2:
            return 'none', None
        cert, slack = farkas_int(self.lp, {(i, t)})
        if cert is None or not verify(self.inst, self.h, cert,
                                      forbid={(i, t)},
                                      elig_aware=self.elig):
            return 'none', None
        self.negative += 1
        # positive side: force s_i=t (delete every other start of i)
        other = {(i, u) for (ii, u) in self._start_cols if ii == i and u != t}
        b2 = [(0, 1)] * self.lp.N
        for key in other:
            for c in self._start_cols[key]:
                b2[c] = (0, 0)
        res2 = self._solve_bounds(b2)
        if res2.status == 2:
            cert2, _ = farkas_int(self.lp, other)
            if cert2 is not None and verify(self.inst, self.h, cert2,
                                            forbid=other,
                                            elig_aware=self.elig):
                self.refuted += 1
                self.split_leaves.append((i, t, cert, cert2, frozenset(other)))
                raise SplitClosed
        # one-sided: force t
        self.forced += 1
        self.leaves.append((frozenset({(i, t)}), frozenset({(i, t)}), cert))
        self.force[i] = frozenset({t}) & self.force.get(i, self.domain(i))
        if not self.force[i]:
            raise SplitClosed
        return 'forced', cert

    # -------------------------------------------------------------- search
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
            if depth == 0 and self.probe_on and not self.probe_off \
                    and self.probes < self.probe_cap:
                acted = False
                for _, _, i, atoms in self._rank(z)[:self.max_candidates]:
                    for mass, t in atoms[:2]:
                        if (i, t) in self._tried or self.probes >= self.probe_cap:
                            continue
                        self._tried.add((i, t))
                        kind, cert = self._probe(i, t)
                        if kind == 'refuted':
                            return False, 'split'
                        if kind == 'forced':
                            acted = True
                            break
                        if kind == 'none' and self.probe_gate:
                            self.probe_off = True
                            break
                    if acted or self.probe_off:
                        break
                if acted:
                    continue
            # v7.1 median branching
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

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        try:
            v, why = self._branch([(0, 1)] * self.lp.base.N, 0, nodecap,
                                  max_rounds, topk)
        except SplitClosed:
            v, why = False, 'split'
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        if why == 'split':
            st['verdict'] = False
        st.update(probes=self.probes, negative=self.negative,
                  forced=self.forced, refuted=self.refuted,
                  splits=len(self.split_leaves),
                  probe_off=self.probe_off)
        return st

    def audit_split(self):
        for i, t, c1, c2, other in self.split_leaves:
            if not verify(self.inst, self.h, c1, forbid={(i, t)},
                          elig_aware=self.elig):
                return False
            if not verify(self.inst, self.h, c2, forbid=other,
                          elig_aware=self.elig):
                return False
        return True
