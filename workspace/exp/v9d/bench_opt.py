"""v9.0 CAB-MC global-optimum benchmark.

Base 141 YES instances, 60 perturbations, and 51 h5/h47 stress instances.
Every run must return a certified optimum with a replayed schedule and a
replayed NO proof at OPT-1.
"""
import sys
import pickle
import time
import json
import collections

sys.path[:0] = ['exp/v9d', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from cab import CABOpt

FILES = {'holdout': 'exp/v20/holdout_cases50.pkl',
         'synth': 'exp/v28/synth2_45.pkl',
         'large_a': 'exp/v14/large_a.pkl',
         'large_b': 'exp/v14/large_b.pkl',
         'large_het': 'exp/v14/large_het.pkl',
         'hard3': 'exp/v13/hard3.pkl',
         'deep': 'exp/v18/deep.pkl'}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def base_corpus():
    return [(name, idx, inst, opt)
            for name, f in FILES.items()
            for idx, (inst, opt) in enumerate(load(f))]


def pert_corpus():
    d = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    return [(name, k, inst, opt) for (name, k, inst, opt, _, _) in d]


def stress_corpus():
    d = pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))
    return [(r['idx'], r['h'], r['inst']) for r in d]


def run(inst):
    t0 = time.time()
    r = CABOpt(inst).optimize()
    dt = time.time() - t0
    return dict(opt=r['opt'], lb=r['lb'], certified=r['certified'],
                gap=r['gap'], ratio=r['ratio'], q=r['queries'],
                qlb=r['q_lb'], lp=r['lp'], yn=r['yes_nodes'],
                mc=r['mc_evals'], t=round(dt, 3), audit=r['audit'],
                proof=r['proof'], cert_h=r['cert_h'],
                lb0=r['lb0'], ub0=r['ub0'],
                schedule=r['schedule'], machine=r['machine'],
                trace=r['trace'])


def main():
    out = {}
    base = base_corpus()
    rows = []
    t0 = time.time()
    for name, idx, inst, opt in base:
        r = run(inst)
        r.update(name=name, idx=idx, known=opt)
        rows.append(r)
        if not (r['certified'] and r['opt'] == opt and r['audit']
                and r['proof'] and r['cert_h'] == opt - 1):
            print('BAD base', name, idx, r['opt'], opt, flush=True)
    out['base'] = rows
    print('base', len(rows), 'time', round(time.time() - t0, 2), flush=True)

    rows = []
    t0 = time.time()
    for name, idx, inst, opt in pert_corpus():
        r = run(inst)
        r.update(name=name, idx=idx, known=opt)
        rows.append(r)
        if not (r['certified'] and r['opt'] == opt and r['audit']
                and r['proof'] and r['cert_h'] == opt - 1):
            print('BAD pert', name, idx, r['opt'], opt, flush=True)
    out['pert'] = rows
    print('pert', len(rows), 'time', round(time.time() - t0, 2), flush=True)

    rows = []
    t0 = time.time()
    for idx, h, inst in stress_corpus():
        r = run(inst)
        r.update(idx=idx, h=h)
        rows.append(r)
        if not (r['certified'] and r['opt'] == h + 1 and r['audit']
                and r['proof'] and r['cert_h'] == h):
            print('BAD stress', idx, h, r['opt'], flush=True)
    out['stress'] = rows
    print('stress', len(rows), 'time', round(time.time() - t0, 2), flush=True)

    json.dump(out, open('exp/v9d/bench_opt.json', 'w'), default=str)
    for tag in ['base', 'pert', 'stress']:
        rs = out[tag]
        agg = dict(n=len(rs), cert=sum(r['certified'] for r in rs),
                   audit=sum(r['audit'] for r in rs),
                   proof=sum(r['proof'] for r in rs),
                   q=sum(r['q'] for r in rs),
                   lp=sum(r['lp'] for r in rs),
                   yn=sum(r['yn'] for r in rs),
                   mc=sum(r['mc'] for r in rs),
                   t=round(sum(r['t'] for r in rs), 2),
                   qdist=dict(collections.Counter(r['q'] for r in rs)))
        print(tag, agg)
    base_lp = sum(r['lp'] for r in out['base'])
    print('base oracle LP 1247, ratio', round(base_lp / 1247, 4))
    print('base oracle queries 282, ratio',
          round(sum(r['q'] for r in out['base']) / 282, 4))
    cum = [(k, sum(r['q'] <= k for r in out['base'])) for k in [1, 2, 3]]
    print('base anytime certified', cum)


if __name__ == '__main__':
    main()
