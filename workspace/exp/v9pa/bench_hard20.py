"""Hard n=20, m=3 corpus selected by a large polynomial-bound gap.

The generator and seeds are fixed.  For each instance we run
  * PACE exact (poly init, lower-first, max_probes=64);
  * PACE A-only (max_probes=0) at eps in {0.1, 0.2, 0.3};
  * PACE approximate with the exact fallback at eps=0.2.
The exact run is the reference; it is also the slow case that motivates
the A-gate.  No known OPT is needed by any production field.
"""
import sys
import json
import time
import random

sys.path[:0] = ['exp/v9pa', 'exp/v8b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from chip import chip_bounds
from pace import run_pace


def gen(n, m, seed, pe, peel):
    rng = random.Random(seed)
    perm = list(range(n))
    rng.shuffle(perm)
    rank = {v: i for i, v in enumerate(perm)}
    p = [rng.randint(1, 9) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if rank[i] < rank[j] and rng.random() < pe:
                pred[j].append(i)
    succ = [[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]:
            succ[i].append(j)
    elig = []
    for i in range(n):
        if rng.random() < peel:
            k = rng.randint(1, m)
            elig.append(sorted(rng.sample(range(m), k)))
        else:
            elig.append(list(range(m)))
    return {'n': n, 'm': m, 'p': p, 'pred': pred, 'succ': succ,
            'elig': elig}


def build():
    out = []
    for seed in range(120):
        inst = gen(20, 3, seed, 0.18, 0.3)
        b = chip_bounds(inst)
        if b['ub'] is None:
            continue
        if b['ub'] - b['lb'] < 3:
            continue
        out.append(dict(seed=seed, inst=inst, chip_lb=b['lb'],
                        chip_ub=b['ub'], chip_gap=b['ub'] - b['lb']))
        if len(out) >= 20:
            break
    return out


def main():
    cases = build()
    rows = []
    t0 = time.time()
    for c in cases:
        inst = c['inst']
        exact = run_pace(inst, None, 'h%d' % c['seed'], c['seed'],
                         eps=0.2, mode='exact', max_probes=64,
                         init='poly')
        opt = exact.get('U') if exact.get('L') == exact.get('U') else None
        row = dict(seed=c['seed'], n=inst['n'], m=inst['m'],
                   chip_lb=c['chip_lb'], chip_ub=c['chip_ub'],
                   chip_gap=c['chip_gap'], opt=opt,
                   exact_stage=exact.get('stage'),
                   exact_probes=exact.get('probes'),
                   exact_cert=exact.get('certified'),
                   exact_t=exact.get('t'))
        for eps in (0.1, 0.2, 0.3):
            r = run_pace(inst, opt, 'h%d' % c['seed'], c['seed'],
                         eps=eps, mode='approx', max_probes=0,
                         init='poly')
            row['pa_eps%s' % str(eps).replace('.', 'p')] = dict(
                stage=r.get('stage'), L=r.get('L'), U=r.get('U'),
                ratio=(r.get('U') / r.get('L')
                       if r.get('L') else None),
                cert=r.get('certified'), t=r.get('t'))
        r = run_pace(inst, opt, 'h%d' % c['seed'], c['seed'],
                     eps=0.2, mode='approx', max_probes=64, init='poly')
        row['a_fallback'] = dict(stage=r.get('stage'), L=r.get('L'),
                                 U=r.get('U'), probes=r.get('probes'),
                                 ratio=(r.get('U') / r.get('L')
                                        if r.get('L') else None),
                                 cert=r.get('certified'), t=r.get('t'))
        rows.append(row)
        print(c['seed'], 'opt', opt, 'exact_t', exact.get('t'),
              'exact_probes', exact.get('probes'),
              'A0.2', row['pa_eps0p2']['stage'],
              'A0.2_t', row['pa_eps0p2']['t'], flush=True)
    out = dict(cases=[dict(seed=c['seed'], inst=c['inst'],
                           chip_lb=c['chip_lb'], chip_ub=c['chip_ub'],
                           chip_gap=c['chip_gap']) for c in cases],
               rows=rows, wall=round(time.time() - t0, 2))
    json.dump(out, open('exp/v9pa/hard20.json', 'w'), indent=1)
    print('wrote hard20.json wall', out['wall'])
    for eps in ('0p1', '0p2', '0p3'):
        key = 'pa_eps' + eps
        closed = sum(r[key]['stage'] not in ('open', 'partial')
                     for r in rows)
        exact = sum(r[key]['L'] == r[key]['U'] for r in rows)
        cert = sum(bool(r[key]['cert']) for r in rows)
        tt = sum(r[key]['t'] for r in rows)
        print('A-only eps', eps, 'closed', closed, 'exact', exact,
              'cert', cert, 't', round(tt, 2))
    print('exact probes', sum(r['exact_probes'] for r in rows),
          'exact cert', sum(bool(r['exact_cert']) for r in rows),
          'exact t', round(sum(r['exact_t'] for r in rows), 2))
    print('A0.2 fallback probes',
          sum(r['a_fallback']['probes'] for r in rows),
          'cert', sum(bool(r['a_fallback']['cert']) for r in rows),
          't', round(sum(r['a_fallback']['t'] for r in rows), 2))


if __name__ == '__main__':
    main()
