"""Perturb the 58 fractional-core instances and test K0 sufficiency.

For each source instance we add +/-1 to one random processing time,
recompute OPT, and run decide_core at h=OPT-1.  The core search is
allowed to return UNKNOWN; in that case decide_core falls back to the
full oracle.  We record both the core outcome and the final outcome.
"""
import sys, json, time, random, collections
sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']
from core_icf import decide_core
from icf import corpora
from pact import PACT, pact_decide


def opt_of(inst):
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, s, m = co.initial_bounds()
    if ub is None:
        return None
    L, U = int(lb), int(ub)
    while L < U:
        mid = (L + U) // 2
        r = pact_decide(inst, mid, depthcap=None, nodecap=None)
        if r['verdict'] is True:
            c = max(r['schedule'][i] + inst['p'][i]
                    for i in range(inst['n']))
            U = min(U, c)
        elif r['verdict'] is False:
            L = mid + 1
        else:
            return None
    return L


def main(seeds_per=3, out='exp/v8u/core_perturb.json'):
    rows = list(corpora())
    probe = json.load(open('exp/v8u/corefirst_probe.json'))
    hard = []
    for (c, name, idx, inst, known), p in zip(rows, probe):
        if p.get('kind') == 'core':
            hard.append((c, name, idx, inst, known))
    print('hard', len(hard))
    out_rows = []
    t0 = time.time()
    for j, (c, name, idx, inst0, known) in enumerate(hard):
        for seed in range(seeds_per):
            rng = random.Random(1000 * j + seed)
            inst = {k: (list(v) if isinstance(v, list)
                        else dict(v) if isinstance(v, dict) else v)
                    for k, v in inst0.items()}
            i = rng.randrange(inst['n'])
            delta = rng.choice([-1, 1])
            if inst['p'][i] + delta <= 0:
                delta = 1
            inst['p'][i] += delta
            opt = opt_of(inst)
            if opt is None:
                out_rows.append(dict(source=[c, name, idx], seed=seed,
                                     i=i, delta=delta, opt=None,
                                     ok=False, error='unknown-opt'))
                continue
            r, root, fb = decide_core(inst, opt - 1)
            out_rows.append(dict(
                source=[c, name, idx], seed=seed, i=i, delta=delta,
                opt=opt, root_status=root['status'], K=root['K'],
                k=len(root['K']), core_verdict=r['verdict'],
                fallback=bool(fb),
                core_lp_wasted=r.get('core_lp_wasted', 0),
                total_lp=(1 + r.get('lp_solves', 0) +
                          r.get('cert_lp', 0)),
                cert_lp=r.get('cert_lp', 0),
                nodes=r.get('nodes', 0),
                t=round(time.time() - t0, 3)))
        if j % 10 == 0:
            print(f'{j+1}/{len(hard)} {c}/{name}/{idx} '
                  f'fb={out_rows[-1].get("fallback")} '
                  f'k={out_rows[-1].get("k")}', flush=True)
    json.dump(out_rows, open(out, 'w'))
    print('wrote', out, 'rows', len(out_rows))
    print('root status', collections.Counter(r.get('root_status')
                                              for r in out_rows))
    print('core verdict', collections.Counter(r.get('core_verdict')
                                               for r in out_rows))
    print('fallback', collections.Counter(r.get('fallback')
                                           for r in out_rows))
    print('k', collections.Counter(r.get('k') for r in out_rows))
    print('wall', round(time.time() - t0, 2))
    return out_rows


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
