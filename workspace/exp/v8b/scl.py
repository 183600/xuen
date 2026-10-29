"""v8.1 SCL-ALC: streaming cross-entropy loss-guided ALC.

Downward side: v8.0 BRC-ALC unchanged (QSP probes, verified Farkas
certificates, row-core recovery, fail-stop splits).

Upward side: the root LP distribution is the proposal.  A stream of
priority vectors is sampled from it, each is scored by the greedy
makespan loss

    L(rank) = Cmax(greedy(rank))          (or +inf if no schedule)

and a bounded archive keeps the best-loss ranks.  A prior reservoir
keeps the first P samples unchanged, so the v8.0 stream is a prefix of
the new stream.  At checkpoints a bounded DFS is run on the reservoir
and the archive; every accepted schedule is replayed by check_schedule.

The optional CE update (scl_alpha > 0) updates a factorized distribution
toward the elite samples; the ablation shows it is not needed on this
corpus, so it is off by default.  The stream is one pass with bounded
memory: only the proposal (O(n|D|)), the archive (O(Bn)) and the
incumbent (O(n)) are kept.  No LP is re-solved by the constructor.
"""
import sys
import math
import random

sys.path[:0] = ['exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

import numpy as np

from rdf import RDF, check_schedule, _heads_latest, _insert, _earliest
from qnc import Budget


def sgs_greedy(inst, rank):
    """Serial SGS with earliest start; returns (start, machine, Cmax)."""
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


class SCL(RDF):
    def __init__(self, inst, h, scl_on=True, scl_floor=0.0,
                 scl_alpha=0.0, scl_elite=0.30, scl_k=8,
                 scl_dfs_every=8, scl_seed=0, scl_prior_mix=0.5,
                 scl_archive=8, scl_dfs_top=4, scl_evals1=64,
                 scl_evals2=384, scl_prior_n=8, scl_prior_pool=8,
                 scl_fallback=True, **kw):
        super().__init__(inst, h, **kw)
        self.scl_on = scl_on
        self.scl_floor = scl_floor
        self.scl_alpha = scl_alpha
        self.scl_elite = scl_elite
        self.scl_k = scl_k
        self.scl_dfs_every = scl_dfs_every
        self.scl_seed = scl_seed
        self.scl_prior_mix = scl_prior_mix
        self.scl_archive = scl_archive
        self.scl_dfs_top = scl_dfs_top
        self.scl_evals1 = scl_evals1
        self.scl_evals2 = scl_evals2
        self.scl_prior_n = scl_prior_n
        self.scl_prior_pool = scl_prior_pool
        self.scl_fallback = scl_fallback
        # counters
        self.scl_evals = 0
        self.scl_rounds = 0
        self.scl_updates = 0
        self.scl_best_loss = None
        self.scl_dfs_calls = 0
        self.scl_lp_nodes = 0
        self.scl_elite_losses = []
        self.scl_used = False
        self._scl_ready = False
        self._scl_q = None
        self._scl_prior = None
        self._scl_dom = None
        self._scl_best = None
        self._scl_archive_pool = []
        self._scl_prior_ranks = []
        self._scl_prior_rng = None
        self._scl_rng = None
        self._scl_z_id = None

    # ---------------------------------------------------------- setup
    def _scl_setup(self, z):
        if self._scl_ready:
            return
        n = self.inst['n']
        self._scl_dom = {}
        for i in range(n):
            ts = sorted({key[-1] for key in self.lp.cols if key[0] == i})
            if not ts:
                ts = sorted(self.domain(i))
            self._scl_dom[i] = ts
        base = self._lp_distribution(z)
        self._scl_prior = {}
        self._scl_q = {}
        for i in range(n):
            bd = dict(base[i])
            dom = self._scl_dom[i]
            u = self.scl_floor / len(dom)
            p = {t: bd.get(t, 0.0) * (1.0 - self.scl_floor) + u
                 for t in dom}
            s = sum(p.values())
            p = {t: v / s for t, v in p.items()}
            self._scl_prior[i] = dict(p)
            self._scl_q[i] = dict(p)
        self._scl_rng = random.Random(20261024 + self.scl_seed * 100003)
        self._scl_prior_rng = random.Random(20261023 + self.yes_calls * 7919)
        self._scl_ready = True

    def _scl_sample_rank_from(self, rng, table):
        rank = {}
        for i, dom in self._scl_dom.items():
            u = rng.random()
            acc = 0.0
            t = dom[-1]
            q = table[i]
            for tt in dom:
                acc += q[tt]
                if u <= acc:
                    t = tt
                    break
            rank[i] = t + rng.random() * 1e-6
        return rank

    def _scl_sample_rank(self):
        return self._scl_sample_rank_from(self._scl_rng, self._scl_q)

    def _scl_update(self, elite):
        """Streaming KL / cross-entropy update toward elite samples."""
        n = self.inst['n']
        for i in range(n):
            dom = self._scl_dom[i]
            cnt = {t: 0.0 for t in dom}
            for _, rank in elite:
                t = min(dom, key=lambda tt: abs(tt - rank[i]))
                cnt[t] += 1.0
            tot = sum(cnt.values())
            q = self._scl_q[i]
            prior = self._scl_prior[i]
            for t in dom:
                emp = cnt[t] / tot if tot else prior[t]
                mix = (self.scl_prior_mix * prior[t]
                       + (1.0 - self.scl_prior_mix) * emp)
                q[t] = ((1.0 - self.scl_alpha) * q[t]
                        + self.scl_alpha * mix)
            s = sum(q.values())
            for t in dom:
                q[t] /= s
        self.scl_updates += 1

    # ---------------------------------------------------------- archive
    def _scl_add_archive(self, loss, rank):
        key = tuple(round(rank[i], 7) for i in range(self.inst['n']))
        for l, r, k in self._scl_archive_pool:
            if k == key:
                if loss < l:
                    self._scl_archive_pool.remove((l, r, k))
                    self._scl_archive_pool.append((loss, dict(rank), key))
                    self._scl_archive_pool.sort(key=lambda x: (x[0], x[2]))
                return
        self._scl_archive_pool.append((loss, dict(rank), key))
        self._scl_archive_pool.sort(key=lambda x: (x[0], x[2]))
        if len(self._scl_archive_pool) > self.scl_archive:
            self._scl_archive_pool.pop()

    def _scl_settle(self, nodecap, top):
        ranks = list(self._scl_prior_ranks)
        ranks += [r for l, r, k in self._scl_archive_pool[:top]]
        if not ranks:
            return False
        for rank in ranks:
            rem = self.yes_node_budget - self.yes_nodes
            if rem <= 0:
                return False
            self.scl_dfs_calls += 1
            got = self._sgs_dfs(rank, min(nodecap, rem),
                                seed=self.scl_dfs_calls)
            if got is not None:
                self.schedule, self.machine = got
                self.yes_ok = True
                return True
        return False

    def _scl_run(self, evals, nodecap):
        self.scl_used = True
        K = max(1, self.scl_k)
        rounds = max(1, int(math.ceil(evals / K)))
        produced = 0
        for r in range(rounds):
            batch = []
            for _ in range(K):
                if produced >= evals:
                    break
                if self.yes_node_budget - self.yes_nodes <= 0:
                    return False
                if len(self._scl_prior_ranks) < self.scl_prior_n:
                    rank = self._scl_sample_rank_from(
                        self._scl_prior_rng, self._scl_prior)
                    if len(self._scl_prior_ranks) < self.scl_prior_pool:
                        self._scl_prior_ranks.append(dict(rank))
                else:
                    rank = self._scl_sample_rank()
                g = sgs_greedy(self.inst, rank)
                produced += 1
                self.scl_evals += 1
                self.yes_trials_used += 1
                if g is None:
                    loss = 10 ** 9
                else:
                    starts, machs, cmax = g
                    loss = cmax
                    if cmax <= self.h:
                        if check_schedule(self.inst, self.h, starts, machs):
                            self.schedule, self.machine = starts, machs
                            self.yes_ok = True
                            return True
                batch.append((loss, dict(rank)))
                self._scl_add_archive(loss, rank)
                if self.scl_best_loss is None or loss < self.scl_best_loss:
                    self.scl_best_loss = loss
            self.scl_rounds += 1
            if batch:
                batch.sort(key=lambda x: (x[0], tuple(
                    x[1][i] for i in range(self.inst['n']))))
                ne = max(1, int(len(batch) * self.scl_elite))
                elite = batch[:ne]
                self.scl_elite_losses.append(elite[0][0])
                self._scl_update(elite)
            if r % self.scl_dfs_every == self.scl_dfs_every - 1 \
                    or r == rounds - 1:
                if self._scl_settle(nodecap, self.scl_dfs_top):
                    return True
        return False

    # -------------------------------------------------------- constructor
    def _yes_construct(self, z, trials, nodecap):
        if not self.scl_on:
            return super()._yes_construct(z, trials, nodecap)
        self.yes_calls += 1
        self._scl_setup(z)
        return self._scl_run(trials, nodecap)

    # ------------------------------------------------------------ decide
    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        if not self.scl_on or not self.yes_scan:
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
            self.yes_calls += 1
            self._scl_setup(self.root_z)
            if self._scl_run(self.scl_evals1, self.yes_nodecap1):
                v, why = True, 'yes-scl-small'
        if v is None and self.root_z is not None \
                and self.yes_nodes < self.yes_node_budget:
            self.yes_calls += 1
            if self._scl_run(self.scl_evals2, self.yes_nodecap2):
                v, why = True, 'yes-scl'
        if v is None and self.root_z is not None and self.scl_fallback \
                and self.yes_nodes < self.yes_node_budget:
            if RDF._yes_construct(self, self.root_z, self.yes_trials2,
                                  self.yes_nodecap2):
                v, why = True, 'yes-brc-fallback'
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
        st.update(scl_on=self.scl_on, scl_evals=self.scl_evals,
                  scl_rounds=self.scl_rounds,
                  scl_updates=self.scl_updates,
                  scl_best_loss=self.scl_best_loss,
                  scl_dfs_calls=self.scl_dfs_calls,
                  scl_elite_last=(self.scl_elite_losses[-1]
                                  if self.scl_elite_losses else None))
        return st
