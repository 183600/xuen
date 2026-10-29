import sys, json, time
sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']
from icf import corpora
from hap import weak_rows
from ubf import run_ubf


def main(which='weak', n=None, out=None, iters=400, rtime=1.0,
         stall=120, policy='lower-first', seed0=0):
    if which == 'weak':
        rows = weak_rows(4)
        items = [(c, name, idx, inst, known, initial)
                 for c, name, idx, inst, known, initial in rows]
    else:
        rows = corpora()
        items = [(c, name, idx, inst, known, None)
                 for c, name, idx, inst, known in rows]
    if n:
        items = items[:n]
    res = []
    t0 = time.time()
    for j, (c, name, idx, inst, known, initial) in enumerate(items):
        row = run_ubf(inst, known, name, idx, repair_iters=iters,
                      repair_time=rtime, repair_stall=stall, seed=seed0 + j,
                      initial=initial, policy=policy)
        row['corpus'] = c
        res.append(row)
        if (j + 1) % 20 == 0:
            print(j + 1, 'elapsed', round(time.time() - t0, 1), flush=True)
    summ = dict(rows=len(res), t=round(time.time() - t0, 3),
                ok=sum(bool(r.get('ok')) for r in res),
                certified=sum(bool(r.get('certified')) for r in res),
                probes=sum(r.get('probes', 0) for r in res),
                pact_lp=sum(r.get('pact_lp', 0) for r in res),
                cert_lp=sum(r.get('pact_cert_lp', 0) for r in res),
                repair_t=round(sum(r.get('repair_t', 0) for r in res), 3),
                repair_iters=sum(r.get('repair_iters', 0) for r in res),
                ub_improved=sum(r.get('ub_after_repair', 0) <
                                r.get('ub0', 0) for r in res),
                gap0=sum(r.get('opt') == r.get('known') for r in res),
                partial_fail=sum(r.get('partial_fail', 0) for r in res),
                unknown=sum(r.get('unknown', 0) for r in res))
    data = dict(kind=which, policy=policy, summary=summ, rows=res)
    if out:
        with open(out, 'w') as f:
            json.dump(data, f, indent=1)
    print(json.dumps(summ, indent=1))
    return data


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--which', default='weak')
    ap.add_argument('--n', type=int, default=None)
    ap.add_argument('--out', default=None)
    ap.add_argument('--iters', type=int, default=400)
    ap.add_argument('--rtime', type=float, default=1.0)
    ap.add_argument('--stall', type=int, default=120)
    ap.add_argument('--policy', default='lower-first')
    ap.add_argument('--seed0', type=int, default=0)
    a = ap.parse_args()
    main(a.which, a.n, a.out, a.iters, a.rtime, a.stall, a.policy,
         a.seed0)
