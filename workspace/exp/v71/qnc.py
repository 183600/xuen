"""v7.1 QNC-ALC: quorum-certified nogoods on top of v6.1 ALC.

A Farkas certificate at a branch node is tied to the node's forbid set F.
Replaying it column by column shows that only a subset E(F) is essential:
every other forbidden column already has non-negative column slack.  The
same integer certificate therefore proves the *larger* region in which
only E is forbidden:

    LP(D \\ E) infeasible        (D = start-time domain of the instance)

So a conflict is a quorum: E is the set of starts the certificate really
needs absent.  Two exact consequences:

  C1  clause:  "not all of E may be forbidden".  Any node whose forbid
      set contains E is NO without an LP.
  C2  force:   if E lives in one job i, every schedule has s_i in E, so
      job i's domain can be shrunk to E for the rest of the search.

C2 is applied *in place* (no root restart): the next sibling inherits the
shrunk domain, and if the sibling's branch region is disjoint from E it
closes with no LP at all.  State (cuts, clauses, forced domains) is
monotone, so the anytime guarantee of v6.1 is preserved; the new progress
measure is the certified domain mass removed by force.
"""
import sys, time
sys.path[:0] = ['exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog
import cert as v60cert
from cert import DENS, verify, _row_meta
from lazy import LazySD


class Budget(Exception):
    pass


def farkas_int(lp, forbid, dens=DENS):
    """Integer Farkas certificate for the LP with columns `forbid` deleted.

    Returns (cert, slack) with slack[c] = (A^T y)_c for every column c.
    """
    A, hi = lp.matrix()
    n_eq, n = lp.n_eq, lp.n
    r = A.shape[0] - n_eq
    present = np.array([cc for cc, key in enumerate(lp.cols)
                        if (key[0], key[-1]) not in forbid], dtype=np.int64)
    if len(present) == 0:
        return None, None
    B = sp.hstack([A[:n_eq].T, A[n_eq:].T]).tocsr()[present]
    c = np.zeros(n_eq + r)
    c[:n_eq] = 1.0
    c[n_eq:] = hi[n_eq:]
    A_eq = np.zeros((1, n_eq + r))
    A_eq[0, n_eq:] = 1.0
    res = linprog(c, A_ub=-B, b_ub=np.zeros(len(present)),
                  A_eq=A_eq, b_eq=[1.0],
                  bounds=[(None, None)] * n_eq + [(0, None)] * r,
                  method='highs')
    if res.status != 0 or res.fun >= 0:
        return None, None
    for D in dens:
        y = np.rint(res.x * D).astype(np.int64)
        s = np.asarray(A.T.dot(y)).ravel()
        bt = int(hi[n:].dot(y[n:])) + int(y[:n].sum())
        if s[present].min() >= 0 and bt < 0:
            meta = _row_meta(lp.base) + [('dom', i, j, t) for (i, j, t) in lp.cuts]
            yb = y[n:]
            cert = dict(
                kind='packing', scale=D,
                beta=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                      if m[0] == 'cap' and yb[k]],
                dom=[(m[1], m[2], m[3], int(yb[k])) for k, m in enumerate(meta)
                     if m[0] == 'dom' and yb[k]],
                exp=[(m[1], m[2], int(yb[k])) for k, m in enumerate(meta)
                     if m[0] == 'exp' and yb[k]],
                alpha=[int(v) for v in y[:n]], obj=bt, farkas=res.fun,
                cuts=[meta[k] for k in range(len(meta)) if yb[k]])
            return cert, s
    return None, None


class QNC:
    def __init__(self, inst, h, cert_on=True, use_quorum=True, use_empty=True):
        self.inst = inst
        self.h = h
        self.n = inst['n']
        self.elig = any(len(set(inst['elig'][i])) < inst['m']
                        for i in range(self.n))
        self.lp = LazySD(inst, h, elig_aware=self.elig)
        self.force = {}            # job -> frozenset of allowed starts
        self.clauses = []          # frozenset of columns (quorum clauses)
        self.leaves = []           # certified NO leaves: (F, E, cert)
        self.cert_on = cert_on
        self.use_quorum = use_quorum
        self.use_empty = use_empty
        self.lp_solves = self.nodes = self.prunes = self.empty_prunes = 0
        self.cert_calls = self.cert_fail = 0
        self.cert_t = 0.0
        self.cert = None
        self.cert_ok = False
        self._dom = {}
        for key in self.lp.cols:
            self._dom.setdefault(key[0], set()).add(key[-1])

    def domain(self, i):
        return frozenset(self._dom[i])

    def _apply_force(self, bounds):
        b = list(bounds)
        changed = False
        for i, S in self.force.items():
            for key, cc in self.lp.idx.items():
                if key[0] == i and key[-1] not in S and b[cc] != (0, 0):
                    b[cc] = (0, 0)
                    changed = True
        return b, changed

    def _forbids(self, bounds):
        return {(key[0], key[-1]) for cc, key in enumerate(self.lp.cols)
                if bounds[cc] == (0, 0)}

    def _empty_job(self, bounds):
        for i in range(self.n):
            any_open = False
            for key, cc in self.lp.idx.items():
                if key[0] == i and bounds[cc] != (0, 0):
                    any_open = True
                    break
            if not any_open:
                return i
        return None

    def _solve(self, bounds, max_rounds, topk):
        res = None
        for rnd in range(max_rounds):
            if self.lp_solves >= self.budget:
                raise Budget
            res = self.lp.solve(bounds)
            self.lp_solves += 1
            if res.status != 0:
                return res, None
            viol = self.lp.separate(res.x, topk=topk)
            if not viol:
                return res, res.x
            for _, i, j, t in viol:
                if (i, j, t) not in self.lp.cutset:
                    self.lp.cutset.add((i, j, t))
                    self.lp.cuts.append((i, j, t))
        return res, (res.x if res is not None and res.status == 0 else None)

    def _analyse(self, F):
        t0 = time.time()
        self.cert_calls += 1
        cert, s = farkas_int(self.lp, F)
        self.cert_t += time.time() - t0
        if cert is None:
            self.cert_fail += 1
            return None
        E = frozenset(key for cc, key in enumerate(self.lp.cols)
                      if key in F and s[cc] < 0)
        # when E == F the certificate was already validated by the exact
        # integer replay inside farkas_int; a smaller E needs the extra
        # replay that re-admits the columns in F \ E.
        if E != frozenset(F) and not verify(self.inst, self.h, cert, forbid=E,
                                            elig_aware=self.elig):
            E = frozenset(F)          # numerical fallback: keep full scope
        return cert, E

    def _learn(self, F):
        got = self._analyse(F)
        if got is None:
            return None, None
        cert, E = got
        self.leaves.append((frozenset(F), E, cert))
        if self.cert is None and self.cert_on:
            self.cert, self.cert_ok = cert, True
        if E and self.use_quorum:
            self.clauses.append(E)
            jobs = {i for (i, t) in E}
            if len(jobs) == 1:
                i = next(iter(jobs))
                times = frozenset(t for (_, t) in E)
                new = times & self.force.get(i, self.domain(i))
                if new != self.force.get(i):
                    self.force[i] = new
        return cert, E

    def _branch(self, bounds, depth, nodecap, max_rounds, topk):
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
        frac = []
        for cc, key in enumerate(self.lp.cols):
            if 1e-7 < z[cc] < 1 - 1e-7:
                frac.append((abs(z[cc] - 0.5), cc, key[0], key[-1]))
        if not frac:
            return True, 'yes'
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

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        try:
            v, why = self._branch([(0, 1)] * self.lp.base.N, 0, nodecap,
                                  max_rounds, topk)
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        return dict(verdict=None if why in ('budget', 'roundcap') else why,
                    why=why, lp_solves=self.lp_solves, nodes=self.nodes,
                    prunes=self.prunes, empty_prunes=self.empty_prunes,
                    cert_calls=self.cert_calls, cert_fail=self.cert_fail,
                    cert_t=self.cert_t, cert=self.cert, cert_ok=self.cert_ok,
                    clauses=len(self.clauses),
                    leaf_sizes=[(len(F), len(E)) for F, E, _ in self.leaves],
                    force={i: sorted(S) for i, S in self.force.items()},
                    leaves=len(self.leaves))

    def audit(self):
        """Replay every leaf certificate at its essential scope."""
        for F, E, c in self.leaves:
            if not E <= F:
                return False
            if not verify(self.inst, self.h, c, forbid=E, elig_aware=self.elig):
                return False
        return True
