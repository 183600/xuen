"""Microbenchmarks for the two heavy-tail instances."""
import sys
import json
import time

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import stress_corpus, base_corpus, chip_bounds
from chd import CHD
from hsc import HSC


def one(cls, inst, h, kw):
    rdf = cls(inst, h, yes_scan=True, cheap_disc=2, hull_disc=4,
              hull_on=True, **kw)
    t0 = time.time()
    v, st = rdf.decide(budget=80, nodecap=5000)
    dt = time.time() - t0
    return dict(v=v, phase=st.get('phase'), lp=st.get('lp_solves'),
                yn=st.get('yes_nodes'), lds=st.get('lds_nodes'),
                tt_states=st.get('tt_states'),
                tt_hits=st.get('tt_hits'), t=round(dt, 4))


def main():
    out = {}
    corp = stress_corpus()
    idx, known, inst = corp[28]
    out['stress47'] = dict(
        h=known - 1, known=known,
        chd=one(CHD, inst, known - 1, {}),
        hsc=one(HSC, inst, known - 1,
                dict(random_fallback=False)),
    )
    for name, i, ins, opt in base_corpus():
        if (name, i) == ('large_het', 7):
            b = chip_bounds(ins)
            h = (b['lb'] + b['ub']) // 2
            out['large_het7'] = dict(
                h=h, known=opt,
                chd=one(CHD, ins, h, {}),
                hsc=one(HSC, ins, h, dict(random_fallback=False)),
            )
    print(json.dumps(out, indent=1))
    json.dump(out, open('exp/v8d/bench_micro.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
