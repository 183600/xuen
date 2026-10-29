"""v8.1 CRISP bracket statistics and preprocessing ablation."""
import sys
import json
import time
import statistics

sys.path[:0] = ['exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from chip import (base_corpus, pert_corpus, stress_corpus, base_bounds,
                  order_portfolio, chip_bounds, simulate_queries)
from scale import energy_cert, windows, verify_prep
from cab import _greedy_rank
from rdf import check_schedule


def drop_ub(inst, ub, est, q):
    for _, rank in order_portfolio(inst, est, q, ub):
        g = _greedy_rank(inst, rank)
        if g is not None and g[2] < ub \
                and check_schedule(inst, g[2], g[0], g[1]):
            ub = g[2]
    return ub


def lift_lb(inst, lb, ub):
    h = lb
    lifts, certs, bad = 0, [], 0
    while h < ub:
        cert = energy_cert(inst, h, 64, 20000)
        if cert is None:
            ee, ll, _ = windows(inst, h)
            if not any(ee[i] > ll[i] for i in range(inst['n'])):
                break
            cert = dict(kind='window')
        good = (verify_prep(inst, h, cert) if cert['kind'] == 'energy'
                else any(ee[i] > ll[i] for i in range(inst['n'])))
        if not good:
            bad += 1
            break
        certs.append(dict(h=h, kind=cert['kind']))
        lifts += 1
        h += 1
    return h, lifts, certs, bad


def main():
    out = {}
    for tag, corpus in [('base', base_corpus()),
                        ('pert', pert_corpus()),
                        ('stress', stress_corpus())]:
        rows = []
        t0 = time.time()
        for rec in corpus:
            if tag == 'base':
                name, idx, inst, opt = rec
            elif tag == 'pert':
                name, idx, inst, opt = rec
            else:
                idx, opt, inst = rec
                name = 'stress'
            lb0, ub0, _, _, est, q = base_bounds(inst)
            ub1 = drop_ub(inst, ub0, est, q)
            lb1, lifts, certs, bad = lift_lb(inst, lb0, ub1)
            ub2 = drop_ub(inst, ub0, est, q)
            lb2, _, _, _ = lift_lb(inst, lb0, ub0)
            rows.append(dict(
                name=name, idx=idx, opt=opt,
                lb0=lb0, ub0=ub0, lb=lb1, ub=ub1,
                lb_lift_only=lb2, ub_drop_only=ub2,
                lifts=lifts, drops=int(ub1 < ub0),
                predq0=simulate_queries(lb0, ub0, opt),
                predq=simulate_queries(lb1, ub1, opt),
                predq_lb_only=simulate_queries(lb2, ub0, opt),
                predq_ub_only=simulate_queries(lb0, ub2, opt),
                sound=(lb0 <= lb1 <= opt <= ub1 <= ub0),
                certs=certs, cert_bad=bad,
            ))
        out[tag] = rows
        print(tag, 'time', round(time.time() - t0, 2), flush=True)
    json.dump(out, open('exp/v8c/bench_bounds.json', 'w'), indent=1)
    for tag in ['base', 'pert', 'stress']:
        rs = out[tag]
        print('\n', tag, 'n', len(rs))
        print('span0', sum(r['ub0'] - r['lb0'] for r in rs),
              'span', sum(r['ub'] - r['lb'] for r in rs))
        print('exact0', sum(r['lb0'] == r['ub0'] for r in rs),
              'exact', sum(r['lb'] == r['ub'] for r in rs))
        print('predq0', sum(r['predq0'] for r in rs),
              'predq', sum(r['predq'] for r in rs))
        print('lifts', sum(r['lifts'] for r in rs),
              'drops', sum(r['drops'] for r in rs),
              'bad', sum(r['cert_bad'] for r in rs),
              'sound', sum(r['sound'] for r in rs))
        rb = [r['ub0'] / r['lb0'] for r in rs]
        ra = [r['ub'] / r['lb'] for r in rs]
        print('ratio mean %.4f -> %.4f max %.4f -> %.4f' %
              (statistics.mean(rb), statistics.mean(ra), max(rb), max(ra)))
    print('\n== ablation (all)')
    rs = [r for tag in out for r in out[tag]]
    print('none   span', sum(r['ub0'] - r['lb0'] for r in rs),
          'exact', sum(r['lb0'] == r['ub0'] for r in rs),
          'predq', sum(r['predq0'] for r in rs))
    print('lb     span', sum(r['ub0'] - r['lb_lift_only'] for r in rs),
          'exact', sum(r['lb_lift_only'] == r['ub0'] for r in rs),
          'predq', sum(r['predq_lb_only'] for r in rs))
    print('ub     span', sum(r['ub_drop_only'] - r['lb0'] for r in rs),
          'exact', sum(r['lb0'] == r['ub_drop_only'] for r in rs),
          'predq', sum(r['predq_ub_only'] for r in rs))
    print('both   span', sum(r['ub'] - r['lb'] for r in rs),
          'exact', sum(r['lb'] == r['ub'] for r in rs),
          'predq', sum(r['predq'] for r in rs))


if __name__ == '__main__':
    main()
