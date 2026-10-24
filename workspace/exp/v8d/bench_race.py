"""Benchmark the v8.2 RACE oracle inside the CRISP bracket."""
import sys, json, time
sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from cab import CABOpt
from chip import CRISP, base_corpus, pert_corpus, stress_corpus
from chd import CHD
from race import RACE


class BaseCRISP(CRISP):
    def __init__(self, *a, variant='chd', **kw):
        self.variant = variant
        super().__init__(*a, **kw)

    def _decide(self, h):
        if self.variant == 'chd':
            rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
                      hull_disc=4, hull_on=True)
        elif self.variant == 'nofirst16':
            rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
                      hull_disc=4, hull_on=True,
                      small_budget=16, small_nodes=400)
        elif self.variant == 'nofirst20':
            rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
                      hull_disc=4, hull_on=True,
                      small_budget=20, small_nodes=400)
        elif self.variant == 'nofirst24':
            rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
                      hull_disc=4, hull_on=True,
                      small_budget=24, small_nodes=400)
        elif self.variant == 'nofirst32':
            rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
                      hull_disc=4, hull_on=True,
                      small_budget=32, small_nodes=800)
        elif self.variant == 'race':
            rdf = RACE(self.inst, h, yes_scan=True, cheap_disc=2,
                       hull_disc=4, hull_on=True)
        else:
            raise ValueError(self.variant)
        try:
            v, st = rdf.decide(budget=self.per_query_lp,
                               nodecap=self.per_query_nodes)
        except Exception:
            v, st = None, rdf._stats('exception')
        self.last_oracle = rdf
        return v, st, rdf


def run(corpus, variant):
    rows = []
    for name, idx, inst, opt in corpus:
        t0 = time.time()
        co = BaseCRISP(inst, variant=variant)
        r = co.optimize()
        dt = time.time() - t0
        rows.append(dict(name=name, idx=idx, known=opt, t=round(dt, 4),
                         q=r['queries'], lp=r['lp'], yn=r['yes_nodes'],
                         mc=r['mc_evals'], certified=r['certified'],
                         opt=r['opt'], audit=r['audit'], proof=r['proof'],
                         cert_h=r['cert_h'], unknown=r['unknown']))
    return rows


def agg(rows):
    return dict(n=len(rows), cert=sum(r['certified'] for r in rows),
                q=sum(r['q'] for r in rows), lp=sum(r['lp'] for r in rows),
                yn=sum(r['yn'] for r in rows), mc=sum(r['mc'] for r in rows),
                t=round(sum(r['t'] for r in rows), 3),
                ok=sum(bool(r['certified'] and r['audit'] and r['proof']
                            and r['cert_h'] == r['known'] - 1
                            and r['opt'] == r['known']) for r in rows))


if __name__ == '__main__':
    corp = list(base_corpus()) + list(pert_corpus()) + \
           [('stress', i, inst, opt)
            for i, (idx, opt, inst) in enumerate(stress_corpus())]
    out = {}
    for variant in ['chd', 'nofirst16', 'nofirst20', 'nofirst24']:
        rows = run(corp, variant)
        out[variant] = rows
        print(variant, agg(rows), flush=True)
    json.dump(out, open('exp/v8d/bench_race.json', 'w'))
