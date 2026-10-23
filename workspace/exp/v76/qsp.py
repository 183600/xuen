"""v7.3 QSP-ALC: quorum support portfolio.

QSP unifies the two certified probes of the preceding rounds:

  * singleton probe (v7.2): delete (i,t); infeasible => s_i = t;
  * support probe (this round): delete the whole support S_i(z); the
    essential scope E of the Farkas certificate is a quorum, and when E
    lives on one job it is a *set* force (every feasible schedule has
    s_i in E_i).

The portfolio chooses which probe to run from the current fractional LP:

  1. two-point span jobs (S_i = D_i, |S_i| = 2) -> singleton probes,
     the shape of the seven v7.2 root traps;
  2. non-span jobs (S_i proper subset of D_i) -> support probes, which
     can return a proper multi-point quorum that no singleton probe sees;
  3. remaining span jobs -> singleton probes in span-first order.

A force triggers a re-solve (force recursion); a unit trap, a cross-job
consensus or two disjoint set forces close the node.  If the portfolio is
exhausted, QSP falls back to the v7.1 median split exactly like QNC.
"""
import sys

sys.path[:0] = ['exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from qnc import Budget
from quc import QUC, _del_bounds
from smc import SMC, _support
from cert import verify


class QSP(QUC, SMC):
    def __init__(self, inst, h, probe_on=True, order='2dom',
                 probe_budget=24, node_budget=2, use_clause=True,
                 unit_probe=True, portfolio='units_first', root_only=False,
                 internal_budget=0, **kw):
        QUC.__init__(self, inst, h, **kw)
        self.probe_on = probe_on
        self.order = order
        self.portfolio = portfolio
        self.root_only = root_only
        self.internal_budget = (node_budget if internal_budget is None
                                else internal_budget)
        self.probe_budget = probe_budget
        self.node_budget = node_budget
        self.use_clause = use_clause
        self.unit_probe_on = unit_probe
        self.mine = True
        self.mine_budget = probe_budget
        self.mine_probes = 0
        self.mine_hits = 0
        self.mine_fail = 0
        self.force_events = []
        self.force_depths = []
        self.force_log = {}
        self.conflict = None
        self.mine_clauses = 0
        self.probes_total = 0
        self.re_solves = 0

    # ------------------------------------------------------------- actions
    def _actions(self, S, bounds):
        """Return an ordered list of ('unit', i, t) / ('set', i, S_i)."""
        span2, sets, rest = [], [], []
        for i, mass in S.items():
            supp = set(mass)
            live = self._live(i, bounds)
            if not live:
                continue
            span = (min(supp) == min(live) and max(supp) == max(live))
            slack = len(live) - len(supp)
            mm = max(mass.values())
            ts = sorted(supp)
            if span and len(ts) == 2:
                span2.append((0, -mm, i, ts))
            elif not span:
                sets.append((len(ts) != 2, -slack, len(ts), -mm, i, ts))
            else:
                rest.append((len(ts), -mm, i, ts))
        span2.sort()
        sets.sort()
        rest.sort()
        acts_u = []
        for _, _, i, ts in span2:
            acts_u.extend(('unit', i, t) for t in ts)
        acts_s = []
        for _, _, _, _, i, ts in sets:
            acts_s.append(('set', i, ts))
            acts_s.extend(('unit', i, t)
                          for t in [ts[0], ts[-1]] + ts[1:-1])
        acts_r = []
        for _, _, i, ts in rest:
            acts_r.extend(('unit', i, t)
                          for t in [ts[0], ts[-1]] + ts[1:-1])
        if self.portfolio == 'sets_first':
            return acts_s + acts_u + acts_r
        if self.portfolio == 'mixed':
            out = []
            for k in range(max(len(acts_u), len(acts_s))):
                if k < len(acts_s):
                    out.append(acts_s[k])
                if k < len(acts_u):
                    out.append(acts_u[k])
            return out + acts_r
        return acts_u + acts_s + acts_r

    # -------------------------------------------------------------- probes
    def _do_unit(self, i, t):
        ok, cert = self._probe_unit(i, t)
        self.probes_total += 1
        if not ok:
            return None
        self.unit_certs[(i, t)] = cert
        self.units.append((i, t, cert))
        self.leaves.append((frozenset({(i, t)}), frozenset({(i, t)}), cert))
        if self.cert is None:
            self.cert, self.cert_ok = cert, True
        cur = self.force.get(i, self.domain(i))
        new = frozenset({t}) & cur
        if new != cur:
            self.force[i] = new
            self.force_events.append((i, new, frozenset({(i, t)}), cert))
            self.force_depths.append(getattr(self, '_cur_depth', 0))
            self.force_log.setdefault(i, []).append(
                (new, frozenset({(i, t)}), cert))
        con = self._unit_conflict()
        if con is not None:
            if con[0] == 'trap':
                self.trap = (con[1], con[2], con[3])
                return 'trap'
            self.cross = con
            return 'cross'
        return 'force' if new != cur else None

    def _do_set(self, i, supp, bounds):
        got = self._probe_support(i, supp, bounds)
        self.probes_total += 1
        if got is None:
            return None
        E, cert = got
        jobs = {j for (j, t) in E}
        if len(jobs) == 1:
            j = next(iter(jobs))
            E_j = frozenset(t for (jj, t) in E if jj == j)
            kind = self._apply_mined_force(j, E_j, E, cert)
            if kind == 'conflict':
                return 'conflict'
            if kind == 'force':
                return 'force'
        elif self.use_clause:
            if E not in self.clauses:
                self.clauses.append(E)
                self.mine_clauses += 1
        return None

    def _portfolio(self, bounds, z):
        S = _support(self.lp, z)
        start = self.probes_total
        limit = self.node_budget if getattr(self, '_cur_depth', 0) == 0 \
            else self.internal_budget
        for act in self._actions(S, bounds):
            if self.probes_total >= self.probe_budget:
                break
            if self.probes_total - start >= limit:
                break
            if act[0] == 'unit':
                if not self.unit_probe_on:
                    continue
                kind = self._do_unit(act[1], act[2])
            else:
                kind = self._do_set(act[1], set(act[2]), bounds)
            if kind is not None:
                return kind
        return None

    # -------------------------------------------------------------- search
    def _search(self, base, depth):
        self._cur_depth = depth
        loop = 0
        while True:
            bounds, _ = self._apply_force(base)
            i0 = self._empty_job(bounds) if self.use_empty else None
            if i0 is not None:
                self.empty_prunes += 1
                return False, 'empty'
            F = self._forbids(bounds)
            for E in self.clauses:
                if E <= F:
                    self.prunes += 1
                    return False, 'clause'
            if loop == 0:
                self.nodes += 1
                if self.nodes > self.nodecap:
                    raise Budget
            res, z = self._solve(bounds, 60, 100)
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
            if depth == 0:
                self.root_frac = True
            if self.probe_on and self.probes_total < self.probe_budget \
                    and (not self.root_only or depth == 0):
                kind = self._portfolio(bounds, z)
                if kind in ('trap', 'cross', 'conflict'):
                    return False, 'probe-' + kind
                if kind == 'force':
                    self.re_solves += 1
                    loop += 1
                    continue
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
            a, why = self._search(lo, depth + 1)
            if a is not False:
                return a, why
            return self._search(hi2, depth + 1)

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        self.nodecap = nodecap
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(probes_total=self.probes_total,
                  mine_probes=self.mine_probes,
                  mine_fail=self.mine_fail,
                  mine_clauses=self.mine_clauses,
                  mine_conflict=self.conflict is not None,
                  force_events=[(i, sorted(a)) for i, a, _, _ in
                                self.force_events],
                  force_depths=list(self.force_depths),
                  re_solves=self.re_solves,
                  probe_budget=self.probe_budget)
        if self.trap is not None or self.cross is not None:
            st['verdict'] = False
        return st

    def audit_qsp(self):
        if not self.audit():
            return False
        for i, t, c in self.units:
            if not verify(self.inst, self.h, c, forbid={(i, t)},
                          elig_aware=self.elig):
                return False
        if self.trap is not None:
            i, t, u = self.trap
            if t == u or (i, t) not in self.unit_certs \
                    or (i, u) not in self.unit_certs:
                return False
        if self.cross is not None:
            if self.cross[0] == 'cap':
                _, tau, c, m = self.cross
                U = {i: t for (i, t) in self.unit_certs}
                cnt = sum(1 for j, u in U.items()
                          if u <= tau < u + self.inst['p'][j])
                if cnt != c or cnt <= m:
                    return False
            else:
                # v7.2's audit_quc used cross[:4] here, which drops the
                # kind tag and shifts every field; fixed in v7.3.
                _, i, t, j, u = self.cross[:5]
                if (i, t) not in self.unit_certs \
                        or (j, u) not in self.unit_certs:
                    return False
                if j not in self.inst['succ'][i] \
                        or not (u < t + self.inst['p'][i]):
                    return False
        return self.audit_smc()
