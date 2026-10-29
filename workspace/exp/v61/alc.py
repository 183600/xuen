"""ALC v6.1: Anytime Lazy Certificate on top of v6.0 SD-ECC.

The v6.0 lazy separator already adds valid stochastic-dominance (SD) cuts
one round at a time, but it only reports a verdict.  ALC turns every
infeasible LP into an immediate *integer* Farkas certificate for the
current cut subset, and keeps the cut set / certificate as an anytime
state.  Consequences:

  * a NO answer and its certificate are produced in the same event;
  * the certificate only uses the cuts actually separated so far, so it
    is sparser than the full-SDLP certificate;
  * cuts are monotone: adding more only shrinks the LP, so a NO stays NO;
  * the cut set can be reused across h and across branch nodes.
"""
import sys
sys.path[:0] = ['exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
import cert as v60cert
from cert import integer_certificate_from_lp, verify
from lazy import LazySD
from po import heads_tails


class ALC:
    def __init__(self, inst, h, use_expect=False, elig_aware=None,
                 cert_on=True):
        self.cert_on = cert_on
        self.inst = inst
        self.h = h
        self.n = inst['n']
        if elig_aware is None:
            elig_aware = any(len(set(inst['elig'][i])) < inst['m']
                             for i in range(self.n))
        self.elig_aware = elig_aware
        self.lp = LazySD(inst, h, use_expect=use_expect,
                         elig_aware=elig_aware)
        self.est, self.q = self.lp.est, self.lp.q
        self.events = []
        self.cert = None
        self.cert_ok = False
        self.lp_solves = 0
        self.nodes = 0
        self.cert_t = 0.0
        self.cert_calls = 0

    def _extract(self, bounds=None):
        import time
        t0 = time.time()
        self.cert_calls += 1
        forbid = set()
        if bounds is not None:
            for cc, bd in enumerate(bounds):
                if bd == (0, 0):
                    key = self.lp.cols[cc]
                    forbid.add((key[0], key[-1]))
        if forbid:
            # a branch node needs the forbidden starts inside the LP; the
            # full SDLP builder supports that, while LazySD is column-fixed.
            c = v60cert.integer_certificate(self.inst, self.h,
                                            forbid=forbid,
                                            elig_aware=self.elig_aware)
        else:
            # rebuild the matrix: LazySD.matrix() is authoritative and the
            # cached lp.A may predate cuts added by another branch node.
            self.lp.A, self.lp.hi = self.lp.matrix()
            c = integer_certificate_from_lp(self.lp, self.inst, self.h)
        ok = c is not None and verify(self.inst, self.h, c,
                                      forbid=forbid,
                                      elig_aware=self.elig_aware)
        self.cert_t += time.time() - t0
        return c, ok

    def _solve_rounds(self, bounds, max_rounds, topk):
        last_res = None
        for rnd in range(max_rounds):
            res = self.lp.solve(bounds)
            self.lp_solves += 1
            last_res = res
            ev = dict(kind='lp', node=self.nodes, round=rnd,
                      status=('infeasible' if res.status == 2 else
                              ('feasible' if res.status == 0 else 'other')),
                      cuts=len(self.lp.cuts), lp=self.lp_solves)
            self.events.append(ev)
            if res.status != 0:
                return res, None, rnd
            viol = self.lp.separate(res.x, topk=topk)
            if not viol:
                return res, res.x, rnd
            for _, i, j, t in viol:
                if (i, j, t) not in self.lp.cutset:
                    self.lp.cutset.add((i, j, t))
                    self.lp.cuts.append((i, j, t))
                    self.events.append(dict(kind='cut', node=self.nodes,
                                            cut=(i, j, t),
                                            cuts=len(self.lp.cuts),
                                            lp=self.lp_solves))
        return last_res, None, max_rounds

    def _branch(self, bounds, depth, nodecap, max_rounds, topk):
        self.nodes += 1
        if self.nodes > nodecap:
            return None, 'nodecap'
        res, z, rnd = self._solve_rounds(bounds, max_rounds, topk)
        if res.status == 2:
            if self.cert_on:
                c, ok = self._extract(bounds)
                if c is not None and ok:
                    if self.cert is None:
                        self.cert = c
                        self.cert_ok = True
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
        times = sorted(set(key[-1] for key in self.lp.idx if key[0] == i))
        s = 0.0
        mid = t
        for tt in times:
            if self.elig_aware:
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
        if self.elig_aware:
            for tt in times:
                for k in self.lp.base.elig[i]:
                    if (i, k, tt) in self.lp.idx:
                        c2 = self.lp.idx[(i, k, tt)]
                        if tt > mid:
                            lo[c2] = (0, 0)
                        else:
                            hi2[c2] = (0, 0)
        else:
            for tt in times:
                c2 = self.lp.idx[(i, tt)]
                if tt > mid:
                    lo[c2] = (0, 0)
                else:
                    hi2[c2] = (0, 0)
        a, why = self._branch(lo, depth + 1, nodecap, max_rounds, topk)
        if a is not False:
            return a, why
        b, why = self._branch(hi2, depth + 1, nodecap, max_rounds, topk)
        if b is not False:
            return b, why
        return False, 'no'

    def decide(self, nodecap=5000, max_rounds=60, topk=100, stats=None):
        base = [(0, 1)] * self.lp.base.N
        v, why = self._branch(base, 0, nodecap, max_rounds, topk)
        st = dict(verdict=v, why=why, lp_solves=self.lp_solves,
                  nodes=self.nodes, cuts=len(self.lp.cuts),
                  events=self.events, cert=self.cert,
                  cert_ok=self.cert_ok, cert_t=self.cert_t,
                  cert_calls=self.cert_calls)
        if stats is not None:
            stats.update(st)
        return v, st
