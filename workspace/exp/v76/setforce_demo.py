"""Witness for strict multi-point set forces (v7.3 support probe).

A strict event is a support probe that returns a single-job quorum E_i
with |E_i| >= 2, E_i properly inside the current domain, and at that same
search node deleting any single (i,t), t in E_i, keeps the LP feasible.
So no singleton probe can produce that force: the set probe is strictly
stronger locally.

The subclass also replays the membership/singleton LPs separately from
the algorithm counters.
"""
import sys, pickle, json

sys.path[:0] = ['exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']
from qsp import QSP
from quc import QUC


class StrictQSP(QSP):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.strict_events = []
        self.demo_lps = 0

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
            cur = self.force.get(j, self.domain(j))
            new = E_j & cur
            if len(new) >= 2 and new != cur:
                sing = []
                for t in sorted(new):
                    b2 = list(bounds)
                    for cc, key in enumerate(self.lp.cols):
                        if key[0] == j and key[-1] == t \
                                and b2[cc] != (0, 0):
                            b2[cc] = (0, 0)
                    res = self.lp.solve(b2)
                    self.demo_lps += 1
                    sing.append([t, res.status == 2])
                if all(not s for _, s in sing):
                    self.strict_events.append(dict(
                        job=j, allowed=sorted(new), E=sorted(E),
                        singletons=sing, E_size=len(E),
                        depth=getattr(self, '_cur_depth', 0)))
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


def main():
    stress = pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))
    out = dict(stress=[], base=[])
    manifest = [('stress', n, r['inst'], r['h'])
                for n, r in enumerate(stress)]
    for name, f, nbase in [('holdout50', 'exp/v20/holdout_cases50.pkl', 50)]:
        for idx, x in enumerate(pickle.load(open(f, 'rb'))):
            inst, opt = (x[0], x[1]) if isinstance(x, tuple) \
                else (x['inst'], x['opt'])
            manifest.append(('base', f'{name}:{idx}', inst, opt - 1))
    for portfolio in ('sets_first', 'units_first'):
        rows = []
        for sec, idx, inst, h in manifest:
            q = StrictQSP(inst, h, probe_budget=24, node_budget=4,
                          internal_budget=1, portfolio=portfolio)
            v, st = q.decide()
            if q.strict_events:
                qq = QUC(inst, h, unit_budget=6)
                vq, sq = qq.decide()
                rows.append(dict(sec=sec, idx=str(idx),
                                 strict=q.strict_events,
                                 qsp_lp=st['lp_solves'],
                                 qsp_nodes=st['nodes'],
                                 quc_lp=sq['lp_solves'],
                                 quc_nodes=sq['nodes']))
        out[portfolio] = rows
        print(portfolio, 'cases with strict events', len(rows),
              'events', sum(len(r['strict']) for r in rows), flush=True)
    for k in ('sets_first', 'units_first'):
        for r in out[k][:5]:
            print(k, r['sec'], r['idx'], 'qsp', r['qsp_lp'],
                  r['qsp_nodes'], 'quc', r['quc_lp'], r['quc_nodes'],
                  r['strict'][:2], flush=True)
    json.dump(out, open('exp/v76/setforce_demo.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
