"""QLS2: clean quorum-local-search split search (prototype).

At a fractional LP node:
  1. delete the support of the current LP vertex and re-solve;
  2. if the deletion LP is infeasible, extract the essential scope E;
  3. if E is a single-job quorum and the current domain does not already
     satisfy it, split into |E| children s_i=t (t in E);
  4. otherwise fall back to the v6.1 median split.

No global force is used inside the split search: the quorum is a case
split, not an unconditional domain restriction.  This keeps siblings
independent and makes the proof tree a pure split tree.
"""
import sys, time
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
from qnc import QNC, Budget
from cert import verify
from qls import farkas_obj


class QLS2(QNC):
    def __init__(self, inst, h, mine=True, split=True, max_depth=64,
                 fallback=True, **kw):
        super().__init__(inst, h, **kw)
        self.mine_on = mine
        self.split_on = split
        self.max_depth = max_depth
        self.fallback = fallback
        self.splits = self.mines = self.mine_fail = 0
        self.split_lits = 0
        self.proofs = []       # (kind, F, E, cert, ok)
        self.split_events = []

    def _mine(self, bounds, z):
        supp = [c for c in range(self.lp.base.N) if z[c] > 1e-7]
        if not supp:
            return None
        b2 = list(bounds)
        for c in supp:
            b2[c] = (0, 0)
        res, z2 = self._solve(b2, 60, 100)
        self.mines += 1
        if res.status != 2:
            self.mine_fail += 1
            return None
        F = self._forbids(b2)
        cert, s = farkas_obj(self.lp, F)
        if cert is None:
            self.mine_fail += 1
            return None
        E = frozenset(key for cc, key in enumerate(self.lp.cols)
                      if key in F and s[cc] < 0)
        ok = verify(self.inst, self.h, cert, forbid=E, elig_aware=self.elig)
        self.proofs.append(('mine', frozenset(F), E, cert, ok))
        if not ok or not E:
            self.mine_fail += 1
            return None
        return E, cert

    def _satisfied(self, bounds, E):
        # clause OR_i (s_i in E_i) satisfied if some job's live domain is
        # entirely inside its literal.
        for i in {i for i, t in E}:
            live = {key[-1] for c, key in enumerate(self.lp.cols)
                    if key[0] == i and bounds[c] != (0, 0)}
            lit = {t for j, t in E if j == i}
            if live and live <= lit:
                return True
        return False

    def _median_children(self, bounds, z):
        frac = [(abs(z[c] - 0.5), c, key[0], key[-1])
                for c, key in enumerate(self.lp.cols)
                if 1e-7 < z[c] < 1 - 1e-7]
        frac.sort()
        _, cc, i, t = frac[0]
        times = sorted(self.domain(i))
        ssum = 0.0
        mid = t
        for tt in times:
            if self.elig:
                ssum += sum(z[self.lp.idx[(i, k, tt)]]
                            for k in self.lp.base.elig[i]
                            if (i, k, tt) in self.lp.idx)
            else:
                ssum += z[self.lp.idx[(i, tt)]]
            if ssum >= 0.5:
                mid = tt
                break
        if mid >= times[-1]:
            mid = times[-1] - 1
        lo = list(bounds); hi2 = list(bounds)
        for tt in times:
            if self.elig:
                for k in self.lp.base.elig[i]:
                    if (i, k, tt) not in self.lp.idx:
                        continue
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
        return lo, hi2

    def _search(self, bounds, depth):
        if self._empty_job(bounds) is not None:
            self.empty_prunes += 1
            return False, 'empty'
        F = self._forbids(bounds)
        for E in self.clauses:
            if E <= F:
                self.prunes += 1
                return False, 'clause'
        self.nodes += 1
        if self.nodes > self.nodecap:
            raise Budget
        if depth > self.max_depth:
            return None, 'depth'
        res, z = self._solve(bounds, 60, 100)
        if res.status == 2:
            cert, s = farkas_obj(self.lp, F)
            if cert is None:
                return None, 'certfail'
            # use the standard essential scope over F
            E = frozenset(key for cc, key in enumerate(self.lp.cols)
                          if key in F and s[cc] < 0)
            ok = verify(self.inst, self.h, cert, forbid=E, elig_aware=self.elig)
            self.proofs.append(('leaf', frozenset(F), E, cert, ok))
            if not ok:
                return None, 'verifyfail'
            return False, 'no'
        if res.status != 0 or z is None:
            return None, 'other'
        frac = [c for c in range(self.lp.base.N)
                if 1e-7 < z[c] < 1 - 1e-7]
        if not frac:
            return True, 'yes'
        if self.mine_on:
            got = self._mine(bounds, z)
            if got is not None:
                E, cert = got
                jobs = {i for i, t in E}
                if self.split_on and len(jobs) == 1 and len(E) <= 12:
                    i = next(iter(jobs))
                    times = sorted(t for j, t in E)
                    self.splits += 1
                    self.split_lits += len(times)
                    self.split_events.append((tuple(sorted(E)), i, tuple(times)))
                    unknown = False
                    for t in times:
                        b2 = list(bounds)
                        for c, key in enumerate(self.lp.cols):
                            if key[0] == i and key[-1] != t:
                                b2[c] = (0, 0)
                        v, why = self._search(b2, depth + 1)
                        if v is True:
                            return True, 'yes'
                        if v is None:
                            unknown = True
                    return (None, 'unknown') if unknown else (False, 'quorum-split')
                # clause satisfied or multi-job: keep as learned clause
                self.clauses.append(E)
        if not self.fallback:
            return None, 'nomine'
        lo, hi2 = self._median_children(bounds, z)
        a, why = self._search(lo, depth + 1)
        if a is True:
            return True, 'yes'
        if a is None:
            return None, 'unknown'
        b, why = self._search(hi2, depth + 1)
        if b is True:
            return True, 'yes'
        if b is None:
            return None, 'unknown'
        return False, 'no'

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        self.nodecap = nodecap
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def audit(self):
        return all(p[4] for p in self.proofs)
