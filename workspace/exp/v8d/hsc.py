"""v8.2 HSC-ALC: hash-shared canonical search for the upward reduction.

The fixed-h oracle of v8.1 is unchanged on the NO side.  This module
replaces the LDS tree of CHD by a canonical state DAG:

  * state = (done-set, predecessor-finish profile, machine calendars);
  * identical states are hash-consed, so commuting job orders collapse;
  * machines with identical eligibility profiles are interchangeable, so
    their calendars are sorted before hashing (symmetry pruning);
  * a budget-aware transposition table stores, for each state, the largest
    remaining discrepancy already proven insufficient.  A state reached
    with no more budget is pruned; a state reached with more budget is
    re-explored.  The table never prunes a state that could still contain
    a schedule within the current LDS budget.

The TT is local to one `_lds` call because the discrepancy cost model is
rank-dependent.  Every accepted schedule still passes check_schedule.
"""
import sys

sys.path[:0] = ['exp/v9b', 'exp/v9d', 'exp/v9c', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from chd import CHD
from rdf import _heads_latest, _insert, _earliest


class HSC(CHD):
    def __init__(self, inst, h, tt_cap=400000, tt_start=1500,
                 canon_mach=True, dominance=False, **kw):
        super().__init__(inst, h, **kw)
        self.tt_cap = tt_cap
        self.tt_start = tt_start
        self.canon_mach = canon_mach
        self.dominance = dominance
        self.tt_states = 0
        self.tt_hits = 0
        self.tt_pruned = 0
        self.tt_dom = 0
        self._groups = self._machine_groups(inst)

    @staticmethod
    def _machine_groups(inst):
        m = inst['m']
        prof = [frozenset(i for i in range(inst['n'])
                          if k in inst['elig'][i]) for k in range(m)]
        groups = {}
        for k in range(m):
            groups.setdefault(prof[k], []).append(k)
        return list(groups.values())

    def _canon(self, busy):
        if not self.canon_mach:
            return tuple(tuple(sorted(b)) for b in busy)
        out = []
        for g in self._groups:
            out.extend(sorted(tuple(sorted(busy[k])) for k in g))
        return tuple(out)

    def _lds(self, rank, nodecap, max_disc, lower=None, upper=None):
        inst, h = self.inst, self.h
        n, m, p = inst['n'], inst['m'], inst['p']
        est, qt, latest = _heads_latest(inst, h)
        if lower is not None:
            est = [max(est[i], lower[i]) for i in range(n)]
        if upper is not None:
            latest = [min(latest[i], upper[i]) for i in range(n)]
        full = (1 << n) - 1
        fail = {}
        tt_on = [False]
        self.tt_hits = 0
        self.tt_states = 0
        self.tt_pruned = 0
        self.tt_dom = 0
        dom = {}

        def one_run(dmax):
            starts = [None] * n
            machs = [None] * n
            busy = [[] for _ in range(m)]
            rem = [len(inst['pred'][i]) for i in range(n)]
            predfin = [0] * n
            done = [False] * n
            dmask = [0]
            nodes = [0]

            def rec(d):
                if dmask[0] == full:
                    return True
                if not tt_on[0] and nodes[0] >= self.tt_start:
                    tt_on[0] = True
                key = None
                old = None
                if tt_on[0]:
                    key = (dmask[0], tuple(predfin), self._canon(busy))
                    old = fail.get(key)
                    if old is not None and d <= old:
                        self.tt_hits += 1
                        return False
                    if self.dominance:
                        dk = (dmask[0], key[2])
                        pf = tuple(predfin)
                        lst = dom.get(dk, ())
                        if any(all(a <= b for a, b in zip(q, pf))
                               and dd >= d for q, dd in lst):
                            self.tt_dom += 1
                            return False
                if nodes[0] >= nodecap:
                    return None
                nodes[0] += 1
                av = [i for i in range(n) if not done[i] and rem[i] == 0]
                if not av:
                    if key is not None and (old is None or d > old):
                        fail[key] = d
                        self.tt_states += 1
                    return False
                av.sort(key=lambda i: (rank[i], i))
                for oi, i in enumerate(av):
                    cost = 0 if oi == 0 else 1
                    if cost > d:
                        continue
                    base = max(est[i], predfin[i])
                    opts = []
                    for k in inst['elig'][i]:
                        tt = _earliest(busy[k], base, p[i])
                        if tt <= latest[i]:
                            opts.append((tt, k))
                    opts.sort()
                    for mi, (tt, k) in enumerate(opts):
                        c2 = cost + (0 if mi == 0 else 1)
                        if c2 > d:
                            continue
                        starts[i] = tt
                        machs[i] = k
                        done[i] = True
                        dmask[0] |= 1 << i
                        _insert(busy, k, tt, tt + p[i])
                        oldv = [(j, predfin[j]) for j in inst['succ'][i]]
                        for j in inst['succ'][i]:
                            predfin[j] = max(predfin[j], tt + p[i])
                            rem[j] -= 1
                        r = rec(d - c2)
                        if r is True:
                            return True
                        if r is None:
                            return None
                        for j, v in oldv:
                            predfin[j] = v
                            rem[j] += 1
                        busy[k].remove((tt, tt + p[i]))
                        done[i] = False
                        dmask[0] &= ~(1 << i)
                        starts[i] = None
                        machs[i] = None
                if key is not None and (old is None or d > old):
                    fail[key] = d
                    self.tt_states += 1
                    if self.dominance:
                        dk = (dmask[0], key[2])
                        dom.setdefault(dk, []).append((tuple(predfin), d))
                if len(fail) > self.tt_cap:
                    fail.clear()
                    dom.clear()
                return False

            r = rec(dmax)
            return r, nodes[0], starts, machs

        used = 0
        last = 0
        for d in range(max_disc + 1):
            last = d
            r, nd, starts, machs = one_run(d)
            used += nd
            if r is True and self._accept_sched(starts, machs):
                return (starts, machs), used, d
            if r is None:
                return None, used, d
            if used > nodecap:
                return None, used, d
        return None, used, last

    def _accept_sched(self, starts, machs):
        from rdf import check_schedule
        return check_schedule(self.inst, self.h, starts, machs)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(tt_states=self.tt_states, tt_hits=self.tt_hits,
                  tt_pruned=self.tt_pruned, tt_dom=self.tt_dom)
        return st
