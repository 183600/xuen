"""v8.4 CCB ablations.

  base   : CCBHybrid (proof cache + UB-1 probe + HSC oracle)
  nocache: same, but the proof cache is disabled (only the oracle)
  tri*   : unconditional NO-first triage with a pure-NO probe of p LP

The triage rows are a negative result: on this corpus the pure-NO probe
costs more LP/wall time than it saves, because the HSC path already
avoids the randomized YES fallback.
"""
import sys
import json
import time

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

import numpy as np

from chip import (base_corpus, pert_corpus, stress_corpus,
                  corpus_rows)
from ccb import CCBHybrid
from hsc import HSC


class NoCache(CCBHybrid):
    def initial_bounds(self):
        lb, ub, starts, machs = super().initial_bounds()
        self.no_states.clear()
        return lb, ub, starts, machs

    def _cached_no(self, h):
        return None


class TriageHSC(HSC):
    def __init__(self, *a, probe_lp=16, probe_nodes=100, **kw):
        super().__init__(*a, **kw)
        self.probe_lp = probe_lp
        self.probe_nodes = probe_nodes

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        if not self.yes_scan:
            return super().decide(budget, nodecap, max_rounds, topk)
        self.budget = min(budget, self.probe_lp)
        self.nodecap = self.probe_nodes
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Exception:
            v, why = None, 'probe-budget'
        if v is not None:
            self.phase = 'P'
            return v, self._stats(why)
        if self.root_z is None:
            res = self.lp.solve([(0, 1)] * self.lp.base.N)
            self.lp_solves += 1
            if res.status == 2:
                self.phase = 'P'
                return False, self._stats('root-core')
            if res.status == 0:
                self.root_z = np.array(res.x, copy=True)
        if self.root_z is not None and self.cheap_disc >= 0:
            if self._cheap_lds():
                return True, self._stats('yes-cheap')
        if self.root_z is not None and self.hull_on:
            self.budget = max(self.lp_solves + self.inst['n'], budget)
            if self._hull_lds():
                return True, self._stats('yes-hull')
        self.budget = budget
        self.nodecap = self.nodes + nodecap
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Exception:
            v, why = None, 'budget'
        self.phase = 'C'
        return v, self._stats(why)


class TriageCCB(CCBHybrid):
    probe_lp = 16

    def _decide(self, h):
        rdf = TriageHSC(self.inst, h, yes_scan=True, cheap_disc=2,
                        hull_disc=4, hull_on=True, random_fallback=False,
                        probe_lp=self.probe_lp, probe_nodes=100)
        rdf.lp.cuts = list(self.cut_pool)
        rdf.lp.cutset = set(self.cut_pool)
        try:
            v, st = rdf.decide(budget=self.per_query_lp,
                               nodecap=self.per_query_nodes)
        except Exception:
            v, st = None, rdf._stats('exception')
        self.cut_pool |= rdf.lp.cutset
        self.last_oracle = rdf
        return v, st, rdf


def run_one(cls, inst, known, name, idx):
    t0 = time.time()
    co = cls(inst)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    r['cache_hits'] = getattr(co, 'cache_hits', 0)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r


def run_all(cls):
    t0 = time.time()
    rows = []
    for tag, corpus in [('base', base_corpus()), ('pert', pert_corpus()),
                        ('stress', stress_corpus())]:
        for rec in corpus:
            if tag in ('base', 'pert'):
                nm, idx, inst, known = rec
            else:
                idx, known, inst = rec
                nm = 'stress'
            rows.append(run_one(cls, inst, known, nm, idx))
    c = corpus_rows(rows)
    c['hits'] = sum(r['cache_hits'] for r in rows)
    c['t'] = round(sum(r['t'] for r in rows), 3)
    print(cls.__name__, c, 'wall', round(time.time() - t0, 2), flush=True)
    return rows


def main():
    out = {'base': run_all(CCBHybrid)}
    out['nocache'] = run_all(NoCache)
    for p in [8, 16, 24]:
        TriageCCB.probe_lp = p
        out['tri%d' % p] = run_all(TriageCCB)
    json.dump(out, open('exp/v8d/bench_ccb_ablate.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
