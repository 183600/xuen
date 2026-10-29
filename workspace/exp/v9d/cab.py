"""v9.0 CAB-MC: certified anytime bracketing + archive/Markov constructor.

Downward side: v8.0 BRC-ALC unchanged (QSP probes, verified Farkas
certificates, row-core recovery, fail-stop splits).

Upward side has two layers.  The archive constructor draws priority
vectors, scores each with a cheap greedy SGS, and spends DFS nodes only
on the best few.  The Markov-chain backstop is a full-support
Metropolis chain over the same priority product; it is only entered if
the archive phase fails.  Every accepted schedule passes check_schedule.

Outer layer: a certified bracket turns the fixed-h decision oracle into
an exact makespan optimizer.  A NO answer at h raises LB to h+1; a YES
answer lowers UB to the replayed makespan.  LB == UB is a global
optimality certificate: schedule at UB plus NO proof at UB-1.
"""
import sys
import math
import random

sys.path[:0] = ['exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

import numpy as np

from rdf import RDF, check_schedule, _insert, _earliest
from qnc import Budget
from po import heads_tails


def _greedy_rank(inst, rank, latest=None):
    """Serial SGS with a fixed priority; completes unless the DAG is cyclic."""
    n, m, p = inst['n'], inst['m'], inst['p']
    starts = [None] * n
    machs = [None] * n
    busy = [[] for _ in range(m)]
    rem = [len(inst['pred'][i]) for i in range(n)]
    predfin = [0] * n
    done = [False] * n
    for _ in range(n):
        av = [i for i in range(n) if not done[i] and rem[i] == 0]
        if not av:
            return None
        av.sort(key=lambda i: (rank[i], i))
        i = av[0]
        base = predfin[i]
        best = None
        for k in inst['elig'][i]:
            tt = _earliest(busy[k], base, p[i])
            if latest is not None and tt > latest[i]:
                continue
            cand = (tt, tt + p[i], k)
            if best is None or cand < best:
                best = cand
        if best is None:
            return None
        tt, ft, k = best
        starts[i] = tt
        machs[i] = k
        done[i] = True
        _insert(busy, k, tt, ft)
        for j in inst['succ'][i]:
            predfin[j] = max(predfin[j], ft)
            rem[j] -= 1
    return starts, machs, max(starts[i] + p[i] for i in range(n))


def greedy_schedule(inst):
    n = inst['n']
    est, _ = heads_tails(inst, 0, [0] * n)
    rank = {i: est[i] + 1e-6 * i for i in range(n)}
    return _greedy_rank(inst, rank)


class CAB(RDF):
    def __init__(self, inst, h, cand_steps1=100, cand_steps2=600,
                 uniform=0.10, archive=8, slack=2, mc_on=True,
                 mc_fallback=True, mc_steps3=1200, mc_nodecap3=4000,
                 mc_eps=0.15, mc_temp0=2.0, mc_temp1=0.10, seed0=0, **kw):
        super().__init__(inst, h, yes_trials1=cand_steps1,
                         yes_trials2=cand_steps2, **kw)
        self.cand_steps1 = cand_steps1
        self.cand_steps2 = cand_steps2
        self.uniform = uniform
        self.archive = archive
        self.slack = slack
        self.mc_on = mc_on
        self.mc_fallback = mc_fallback
        self.mc_steps3 = mc_steps3
        self.mc_nodecap3 = mc_nodecap3
        self.mc_eps = mc_eps
        self.mc_temp0 = mc_temp0
        self.mc_temp1 = mc_temp1
        self.seed0 = seed0
        self.cand_pool = []
        self.mc_evals = 0
        self.mc_accept = 0
        self.mc_steps_used = 0
        self.mc_best = None
        self.mc_used = False

    # -------------------------------------------------------- candidates
    def _sample_priority(self, dist, rng, domains, uniform):
        rank = {}
        for i, d in dist.items():
            if rng.random() < uniform:
                t = rng.choice(domains[i])
            else:
                t = self._sample_from(dist, i, rng)
            rank[i] = t + rng.random() * 1e-6
        return rank

    @staticmethod
    def _sample_from(dist, i, rng):
        d = dist[i]
        u = rng.random()
        acc = 0.0
        t = d[-1][0]
        for tt, v in d:
            acc += v
            if u <= acc:
                t = tt
                break
        return t

    def _domains(self):
        return {i: sorted({key[-1] for key in self.lp.cols if key[0] == i})
                for i in range(self.inst['n'])}

    def _add_pool(self, cost, rank):
        self.cand_pool.append((cost, dict(rank)))
        if len(self.cand_pool) > 4096:
            self.cand_pool.sort(key=lambda x: (x[0], tuple(
                x[1][i] for i in range(self.inst['n']))))
            self.cand_pool = self.cand_pool[:self.archive * 8]

    def _top_pool(self):
        self.cand_pool.sort(key=lambda x: (x[0], tuple(
            x[1][i] for i in range(self.inst['n']))))
        out = []
        seen = set()
        for c, r in self.cand_pool:
            key = tuple(round(r[i], 7) for i in range(self.inst['n']))
            if key in seen:
                continue
            seen.add(key)
            out.append((c, r))
            if len(out) >= self.archive:
                break
        return out

    def _settle(self, top, nodecap):
        for c, rank in top:
            if c > self.h + self.slack:
                continue
            rem = self.yes_node_budget - self.yes_nodes
            if rem <= 0:
                return False
            got = self._sgs_dfs(rank, min(nodecap, rem))
            if got is not None:
                self.schedule, self.machine = got
                self.yes_ok = True
                return True
        return False

    def _archive_construct(self, z, steps, nodecap):
        self.yes_calls += 1
        dist = self._lp_distribution(z)
        domains = self._domains()
        rng = random.Random(20261024 + self.seed0 * 100003
                            + self.yes_calls * 7919)
        for _ in range(steps):
            rank = self._sample_priority(dist, rng, domains, self.uniform)
            g = _greedy_rank(self.inst, rank)
            self.mc_evals += 1
            c = 10 ** 9 if g is None else g[2]
            self._add_pool(c, rank)
            if self.mc_best is None or c < self.mc_best:
                self.mc_best = c
        self.yes_trials_used += steps
        return self._settle(self._top_pool(), nodecap)

    # -------------------------------------------------------- MC backstop
    def _mc_chain(self, z, steps, nodecap):
        self.mc_used = True
        self.yes_calls += 1
        dist = self._lp_distribution(z)
        domains = self._domains()
        n = self.inst['n']
        rng = random.Random(20261024 + self.seed0 * 100003
                            + self.yes_calls * 7919)
        if self.cand_pool:
            start = min(self.cand_pool, key=lambda x: x[0])
            rank = dict(start[1])
            cur = start[0]
        else:
            rank = self._sample_priority(dist, rng, domains, self.uniform)
            g = _greedy_rank(self.inst, rank)
            cur = 10 ** 9 if g is None else g[2]
        best = (cur, dict(rank))
        for s in range(steps):
            frac = s / max(1, steps - 1)
            temp = max(self.mc_temp1,
                       self.mc_temp0 * (self.mc_temp1 / self.mc_temp0) ** frac)
            prop = dict(rank)
            i = rng.randrange(n)
            if rng.random() < self.mc_eps:
                t = rng.choice(domains[i])
            else:
                t = self._sample_from(dist, i, rng)
            prop[i] = t + rng.random() * 1e-6
            g = _greedy_rank(self.inst, prop)
            self.mc_evals += 1
            self.mc_steps_used += 1
            c = 10 ** 9 if g is None else g[2]
            self._add_pool(c, prop)
            if c < best[0]:
                best = (c, dict(prop))
            if c <= cur or rng.random() < math.exp(-(c - cur) / temp):
                rank = prop
                cur = c
                self.mc_accept += 1
        self.mc_best = best[0] if self.mc_best is None else min(
            self.mc_best, best[0])
        self.yes_trials_used += steps
        return self._settle(self._top_pool(), nodecap)

    def _yes_construct(self, z, trials, nodecap):
        if not self.mc_on:
            return super()._yes_construct(z, trials, nodecap)
        return self._archive_construct(z, trials, nodecap)

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        if not self.yes_scan:
            return super().decide(budget=budget, nodecap=nodecap,
                                  max_rounds=max_rounds, topk=topk)
        self.budget = min(budget, self.small_budget)
        self.nodecap = min(nodecap, self.small_nodes)
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Budget:
            v, why = None, 'budget-small'
        if v is None and self.root_z is None:
            res = self.lp.solve([(0, 1)] * self.lp.base.N)
            self.lp_solves += 1
            if res.status == 2:
                v, why = False, 'root-core'
            elif res.status == 0:
                self.root_z = np.array(res.x, copy=True)
        if v is None and self.root_z is not None:
            if self._yes_construct(self.root_z, self.cand_steps1,
                                   self.yes_nodecap1):
                v, why = True, 'yes-archive-small'
        if v is None and self.root_z is not None \
                and self.yes_nodes < self.yes_node_budget:
            if self._yes_construct(self.root_z, self.cand_steps2,
                                   self.yes_nodecap2):
                v, why = True, 'yes-archive'
        if v is None and self.root_z is not None and self.mc_fallback \
                and self.yes_nodes < self.yes_node_budget:
            if self._mc_chain(self.root_z, self.mc_steps3,
                              self.mc_nodecap3):
                v, why = True, 'yes-mc'
        if v is None:
            self.budget = budget
            self.nodecap = self.nodes + nodecap
            try:
                v, why = self._search([(0, 1)] * self.lp.base.N, 0)
            except Budget:
                v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(mc_on=self.mc_on, mc_evals=self.mc_evals,
                  mc_accept=self.mc_accept, mc_steps=self.mc_steps_used,
                  mc_best=self.mc_best, mc_used=self.mc_used,
                  cand_pool=len(self.cand_pool))
        return st


class CABOpt:
    """Exact makespan optimizer with a replayable optimality certificate."""

    def __init__(self, inst, cab_kw=None, per_query_lp=80,
                 per_query_nodes=5000, max_queries=40, unknown_retries=2):
        self.inst = inst
        self.cab_kw = dict(cab_kw or {})
        self.per_query_lp = per_query_lp
        self.per_query_nodes = per_query_nodes
        self.max_queries = max_queries
        self.unknown_retries = unknown_retries
        self.trace = []
        self.lp_total = 0
        self.yes_nodes_total = 0
        self.mc_evals_total = 0
        self.unknown = 0
        self.schedule = None
        self.machine = None
        self.opt = None
        self.lb = None
        self.lb_proof = None
        self.no_states = {}
        self.lb0 = self.ub0 = None
        self.queries = 0
        self.certified = False

    def initial_bounds(self):
        inst = self.inst
        n, m, p = inst['n'], inst['m'], inst['p']
        est, q = heads_tails(inst, 0, [0] * n)
        lb = max(est[i] + p[i] + q[i] for i in range(n))
        elig = inst['elig']
        for mask in range(1, 1 << m):
            jobs = [i for i in range(n)
                    if all((mask >> k) & 1 for k in elig[i])]
            load = sum(p[i] for i in jobs)
            lb = max(lb, (load + bin(mask).count('1') - 1)
                     // bin(mask).count('1'))
        g = greedy_schedule(inst)
        if g is None:
            return lb, None, None, None
        starts, machs, ub = g
        if not check_schedule(inst, ub, starts, machs):
            return lb, None, None, None
        return lb, ub, starts, machs

    def _decide(self, h):
        rdf = CAB(self.inst, h, yes_scan=True, **self.cab_kw)
        try:
            v, st = rdf.decide(budget=self.per_query_lp,
                               nodecap=self.per_query_nodes)
        except Budget:
            v, st = None, rdf._stats('budget')
        return v, st, rdf

    def optimize(self):
        lb, ub, starts, machs = self.initial_bounds()
        self.lb0, self.ub0 = lb, ub
        self.lb = lb
        if ub is not None:
            self.schedule, self.machine, self.opt = starts, machs, ub
        while self.lb < self.opt and self.queries < self.max_queries:
            h = (self.lb + self.opt) // 2
            v, st, rdf = self._decide(h)
            self.queries += 1
            self._absorb(st)
            self._record(h, v, st)
            if v is True:
                cmax = max(rdf.schedule[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                if cmax < self.opt:
                    self.opt = cmax
                    self.schedule = list(rdf.schedule)
                    self.machine = list(rdf.machine)
            elif v is False:
                self.lb = max(self.lb, h + 1)
                self.no_states[h] = rdf
                self.lb_proof = rdf
            else:
                self.unknown += 1
                self._recover_unknown(h)
        self.certified = (self.lb == self.opt and self.opt is not None)
        if self.certified and (self.opt - 1) not in self.no_states:
            v, st, rdf = self._decide(self.opt - 1)
            self.queries += 1
            self._absorb(st)
            self._record(self.opt - 1, v, st)
            if v is False:
                self.no_states[self.opt - 1] = rdf
                self.lb_proof = rdf
            else:
                self.certified = False
        return self._result()

    def _absorb(self, st):
        self.lp_total += st['lp_solves']
        self.yes_nodes_total += st.get('yes_nodes', 0)
        self.mc_evals_total += st.get('mc_evals', 0)

    def _recover_unknown(self, h):
        for r in range(self.unknown_retries):
            probe = h if r % 2 == 0 else max(self.lb, h - 1)
            v, st, rdf = self._decide(probe)
            self.queries += 1
            self._absorb(st)
            self._record(probe, v, st)
            if v is True:
                cmax = max(rdf.schedule[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                if cmax < self.opt:
                    self.opt = cmax
                    self.schedule = list(rdf.schedule)
                    self.machine = list(rdf.machine)
                return
            if v is False:
                self.lb = max(self.lb, probe + 1)
                self.no_states[probe] = rdf
                self.lb_proof = rdf
                return

    def _record(self, h, v, st):
        self.trace.append(dict(h=h, v=v, lb=self.lb, ub=self.opt,
                               lp=st.get('lp_solves', 0),
                               nodes=st.get('nodes', 0),
                               yes_nodes=st.get('yes_nodes', 0),
                               mc_evals=st.get('mc_evals', 0)))

    def _result(self):
        gap = None if self.opt is None else self.opt - self.lb
        ratio = (None if self.opt is None or self.lb <= 0
                 else self.opt / self.lb)
        span = None if self.ub0 is None else self.ub0 - self.lb0
        q_lb = (None if span is None or span <= 0
                else int(math.ceil(math.log2(span + 1))))
        audit = False
        proof = False
        cert_h = None
        if self.lb_proof is not None:
            cert_h = self.lb_proof.h
            audit = bool(self.lb_proof.audit_rdf())
            proof = bool(self.lb_proof.proof_complete())
        if self.schedule is not None:
            audit = audit and check_schedule(self.inst, self.opt,
                                             self.schedule, self.machine)
        return dict(opt=self.opt, lb=self.lb, certified=self.certified,
                    gap=gap, ratio=ratio, queries=self.queries,
                    lb0=self.lb0, ub0=self.ub0, q_lb=q_lb,
                    lp=self.lp_total, yes_nodes=self.yes_nodes_total,
                    mc_evals=self.mc_evals_total, unknown=self.unknown,
                    audit=audit, proof=proof, cert_h=cert_h,
                    schedule=self.schedule, machine=self.machine,
                    trace=self.trace)
