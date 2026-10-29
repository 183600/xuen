"""v8.0 QUP: quorum clauses as a CSP with unit propagation and clause-loss
branching.

v7.1 learned a clause "some job's start lies in E" from every certified
leaf, but only used single-job clauses (as a global force) and the
subset test E subset F (which never fired).  A clause is a disjunction, so
the complete inference is unit propagation:

    if all but one literal are false in the current subcube,
    restrict the last job's domain to its literal.

That is node-local and strictly stronger than both v7.1 mechanisms: it
subsumes the subset test (all literals false = conflict) and generalises
single-job force to the case where the branch decisions, not the root,
falsified the other literals.  Domains shrunk by propagation are also fed
to the Farkas extractor, so the learned scopes shrink too.

Branching is a one-step heuristic search in split space.  The loss of a
subcube is

    L(D) = sum_{active clauses C} 2^{-r_C(D)},

where r_C is the number of literals of C still live (intersecting the
domain but not implied).  L is small when clauses are close to becoming
unit or conflicting.  For each clause literal we generate the two splits
that put the literal's allowed set entirely on one side; we propagate
each child symbolically and choose the split minimising the expected
loss (a conflict child has loss -1).  With no clauses this degenerates to
v6.1's most-fractional median branch.
"""
import sys
import numpy as np
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC, Budget


class QUP(QNC):
    def __init__(self, inst, h, cert_on=True, use_quorum=True,
                 use_empty=True, use_up=True, use_loss=True,
                 cut_budget=None, branch_mode='med'):
        super().__init__(inst, h, cert_on=cert_on, use_quorum=use_quorum,
                         use_empty=use_empty)
        self.use_up = use_up
        self.use_loss = use_loss
        self.cut_budget = cut_budget
        self.branch_mode = branch_mode
        self.global_conflict = False
        self.clause_groups = []
        self.prop_conflicts = 0
        self.prop_nodes = 0
        self.prop_shrink = 0
        self.split_conflicts = 0
        self.branch_sources = {'base': 0, 'clause': 0}
        self.prop_events = []

    # ---------- clause representation ----------
    @staticmethod
    def _group(E):
        g = {}
        for i, t in E:
            g.setdefault(i, set()).add(t)
        return tuple((i, frozenset(S)) for i, S in sorted(g.items()))

    def _learn(self, F):
        n0 = len(self.clauses)
        cert, E = super()._learn(F)
        if len(self.clauses) > n0:
            self.clause_groups.append(self._group(E))
        return cert, E

    # ---------- domains / propagation ----------
    def _doms(self, bounds):
        dom = {i: set() for i in range(self.n)}
        for cc, key in enumerate(self.lp.cols):
            if bounds[cc] != (0, 0):
                dom[key[0]].add(key[-1])
        return dom

    def _forbid_times(self, bounds, i, allowed):
        """Forbid all starts of job i outside `allowed` (in place)."""
        changed = False
        for key, cc in self.lp.idx.items():
            if key[0] == i and key[-1] not in allowed and bounds[cc] != (0, 0):
                bounds[cc] = (0, 0)
                changed = True
        return changed

    def _up_once(self, dom):
        """One pass of unit propagation; returns (changed, conflict)."""
        changed = False
        for groups in self.clause_groups:
            if any(not dom[i] for i, _ in groups):
                return changed, True
            sat = False
            live = []
            for i, S in groups:
                inter = dom[i] & S
                if not inter:
                    continue
                if dom[i] <= S:
                    sat = True
                    break
                live.append((i, S))
            if sat:
                continue
            if not live:
                return changed, True
            if len(live) == 1:
                i, S = live[0]
                new = dom[i] & S
                if new != dom[i]:
                    dom[i] = new
                    changed = True
                    if not new:
                        return changed, True
        return changed, False

    def _propagate(self, bounds):
        """Apply global force then clause unit propagation to a fixpoint."""
        bounds, _ = self._apply_force(bounds)
        dom = self._doms(bounds)
        shrink0 = sum(len(s) for s in dom.values())
        conflict = False
        if self.use_up and self.clause_groups:
            while True:
                changed, conflict = self._up_once(dom)
                if conflict or not changed:
                    break
        if conflict:
            return bounds, True, shrink0
        for i, S in dom.items():
            self._forbid_times(bounds, i, S)
        shrink = shrink0 - sum(len(s) for s in dom.values())
        return bounds, False, shrink

    def _stats_up(self, dom):
        """Clause loss and count of live/units for a propagated domain."""
        loss = 0.0
        units = 0
        for groups in self.clause_groups:
            sat = False
            live = 0
            for i, S in groups:
                inter = dom[i] & S
                if not inter:
                    continue
                if dom[i] <= S:
                    sat = True
                    break
                live += 1
            if sat:
                continue
            if live == 0:
                return -1.0, 1
            if live == 1:
                units += 1
            loss += 2.0 ** (-live)
        return loss, units

    # ---------- split construction ----------
    def _split(self, bounds, i, mid):
        lo = list(bounds)
        hi = list(bounds)
        for key, cc in self.lp.idx.items():
            if key[0] != i:
                continue
            if key[-1] > mid:
                lo[cc] = (0, 0)
            else:
                hi[cc] = (0, 0)
        return lo, hi

    def _baseline_mid(self, z, i, times):
        q = {'med': 0.5, 'q25': 0.25, 'q75': 0.75}.get(self.branch_mode, 0.5)
        if self.branch_mode == 'hi':
            return times[-1] - 1
        if self.branch_mode == 'lo':
            return times[0]
        s = 0.0
        mid = times[0]
        for tt in times:
            if self.elig:
                s += sum(z[self.lp.idx[(i, k, tt)]]
                         for k in self.lp.base.elig[i]
                         if (i, k, tt) in self.lp.idx)
            else:
                s += z[self.lp.idx[(i, tt)]]
            if s >= q:
                mid = tt
                break
        if mid >= times[-1]:
            mid = times[-1] - 1
        return mid

    def _frac_mass(self, z):
        out = {i: 0.0 for i in range(self.n)}
        for cc, key in enumerate(self.lp.cols):
            v = z[cc]
            if 1e-7 < v < 1 - 1e-7:
                out[key[0]] += min(v, 1 - v)
        return out

    def _choose_branch(self, bounds, z, dom):
        # baseline: v6.1 most-fractional column + median split
        frac = []
        for cc, key in enumerate(self.lp.cols):
            if 1e-7 < z[cc] < 1 - 1e-7:
                frac.append((abs(z[cc] - 0.5), cc, key[0], key[-1]))
        frac.sort()
        _, _, i0, t0 = frac[0]
        times0 = sorted(dom[i0])
        mid0 = self._baseline_mid(z, i0, times0)
        cands = [(i0, mid0, 'base')]
        if self.use_loss and self.clause_groups:
            seen = {(i0, mid0)}
            # only clauses that are active (not satisfied, not conflict)
            scored = []
            for groups in self.clause_groups:
                sat = False
                live = []
                for i, S in groups:
                    inter = dom[i] & S
                    if not inter:
                        continue
                    if dom[i] <= S:
                        sat = True
                        break
                    live.append((i, S))
                if sat or not live:
                    continue
                r = len(live)
                w = 4.0 ** (2 - min(r, 4))
                scored.append((w, live))
            scored.sort(key=lambda x: -x[0])
            for _, live in scored[:16]:
                for i, S in live:
                    ts = sorted(dom[i])
                    lo_t, hi_t = ts[0], ts[-1]
                    if max(S) < hi_t:
                        mid = max(S)
                        if (i, mid) not in seen and lo_t <= mid < hi_t:
                            seen.add((i, mid)); cands.append((i, mid, 'clause'))
                    if min(S) > lo_t:
                        mid = min(S) - 1
                        if (i, mid) not in seen and lo_t <= mid < hi_t:
                            seen.add((i, mid)); cands.append((i, mid, 'clause'))
        fm = self._frac_mass(z)
        best = None
        for i, mid, src in cands:
            if i not in dom or len(dom[i]) < 2:
                continue
            ts = sorted(dom[i])
            if not (ts[0] <= mid < ts[-1]):
                continue
            lo, hi = self._split(bounds, i, mid)
            lo2, lc, _ = self._propagate(lo)
            hi2, hc, _ = self._propagate(hi)
            if lc and hc:
                key = (-2, 0, -1.0, 0.0, 0.0, 0.0)
            else:
                dlo = self._doms(lo2) if not lc else None
                dhi = self._doms(hi2) if not hc else None
                llo, ulo = (-1.0, 0) if lc else self._stats_up(dlo)
                lhi, uhi = (-1.0, 0) if hc else self._stats_up(dhi)
                slo = 0 if dlo is None else sum(len(s) for s in dlo.values())
                shi = 0 if dhi is None else sum(len(s) for s in dhi.values())
                # domain sizes after propagation (smaller = closer to close)
                b = (min(slo, shi) + 1.0) / (max(slo, shi) + 1.0)
                key = (-(int(lc) + int(hc)), -(ulo + uhi), llo + lhi,
                       -(slo + shi), -b, -fm.get(i, 0.0))
            if best is None or key < best[0]:
                best = (key, i, mid, src, lo2, hi2, lc, hc)
        if best is None:
            return None
        return best

    # ---------- cut-budget LP ----------
    def _solve(self, bounds, max_rounds, topk):
        """Normal lazy separation, or a cut-budgeted relaxation.

        With cut_budget=None this is exactly v6.1/v7.1.  With an integer
        k, a fractional node may branch after at most k new dominance cuts;
        an integral node must add every violated cut before it can be YES,
        so a weak LP can never produce a false YES.
        """
        if self.cut_budget is None:
            return super()._solve(bounds, max_rounds, topk)
        res = None
        added = 0
        for _ in range(max_rounds):
            if self.lp_solves >= self.budget:
                raise Budget
            res = self.lp.solve(bounds)
            self.lp_solves += 1
            if res.status != 0:
                return res, None
            z = res.x
            viol = self.lp.separate(z, topk=max(1, topk))
            if not viol:
                return res, z
            frac = any(1e-7 < v < 1 - 1e-7 for v in z)
            if frac and added >= self.cut_budget:
                return res, z
            for _, i, j, t in viol:
                if (i, j, t) not in self.lp.cutset:
                    self.lp.cutset.add((i, j, t))
                    self.lp.cuts.append((i, j, t))
                    added += 1
        if res is not None and res.status == 0:
            if any(1e-7 < v < 1 - 1e-7 for v in res.x):
                return res, res.x
            return res, None          # integral but cuts unresolved
        return res, None

    def _root_conflict(self):
        """Unit-propagate all clauses from the root domain."""
        N = self.lp.base.N
        bounds, _, _ = self._propagate([(0, 1)] * N)
        dom = self._doms(bounds)
        if any(not s for s in dom.values()):
            return True
        while True:
            changed, conflict = self._up_once(dom)
            if conflict:
                return True
            if not changed:
                return False

    # ---------- DFS ----------
    def _branch(self, bounds, depth, nodecap, max_rounds, topk):
        if self.global_conflict:
            return False, 'global'
        bounds, conflict, _ = self._propagate(bounds)
        if conflict:
            self.prop_conflicts += 1
            self.nodes += 1
            return False, 'prop'
        if self.use_empty and self._empty_job(bounds) is not None:
            self.empty_prunes += 1
            self.nodes += 1
            return False, 'empty'
        self.nodes += 1
        if self.nodes > nodecap:
            raise Budget
        res, z = self._solve(bounds, max_rounds, topk)
        if res.status == 2:
            self._learn(self._forbids(bounds))
            if self.use_up and self.clause_groups and self._root_conflict():
                self.global_conflict = True
                return False, 'global'
            return False, 'no'
        if z is None:
            return None, 'roundcap'
        frac = [cc for cc, v in enumerate(z) if 1e-7 < v < 1 - 1e-7]
        if not frac:
            return True, 'yes'
        dom = self._doms(bounds)
        got = self._choose_branch(bounds, z, dom)
        if got is None:
            i, mid = self._fallback(bounds, z, dom)
            lo, hi = self._split(bounds, i, mid)
            lc = hc = False
            src = 'base'
        else:
            _, i, mid, src, lo, hi, lc, hc = got
        self.branch_sources[src] += 1
        if lc and hc:
            self.split_conflicts += 1
            return False, 'split'
        a, wa = (False, 'prop') if lc else self._branch(
            lo, depth + 1, nodecap, max_rounds, topk)
        if a is not False:
            return a, wa
        b, wb = (False, 'prop') if hc else self._branch(
            hi, depth + 1, nodecap, max_rounds, topk)
        if b is not False:
            return b, wb
        return False, 'no'

    def _fallback(self, bounds, z, dom):
        frac = []
        for cc, key in enumerate(self.lp.cols):
            if 1e-7 < z[cc] < 1 - 1e-7:
                frac.append((abs(z[cc] - 0.5), cc, key[0]))
        frac.sort()
        i = frac[0][2]
        ts = sorted(dom[i])
        return i, self._baseline_mid(z, i, ts)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(prop_conflicts=self.prop_conflicts,
                  split_conflicts=self.split_conflicts,
                  global_conflict=self.global_conflict,
                  prop_shrink=self.prop_shrink,
                  branch_sources=dict(self.branch_sources),
                  clause_groups=len(self.clause_groups))
        return st

