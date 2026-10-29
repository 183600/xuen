"""Scale processing times by s and compare Core-ICF with the full ICF loop.

Scaling p by s scales OPT by s (all durations are multiplied).  The
horizon T grows by s, so the LP has s times more time points.  This is
the cleanest way to test whether the exponential/core part or the
P-time LP dominates the runtime.
"""
import sys, json, time
sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']
from core_icf import run_core_icf
from icf import run_icf, corpora


def scaled(inst, s):
    out = {k: (list(v) if isinstance(v, list)
               else dict(v) if isinstance(v, dict) else v)
           for k, v in inst.items()}
    out['p'] = [x * s for x in inst['p']]
    return out


def main(positions=(5, 47, 147, 201), scales=(1, 2, 4, 8)):
    rows = list(corpora())
    out = []
    t0 = time.time()
    for pos in positions:
        c, name, idx, inst0, known = rows[pos]
        for s in scales:
            inst = scaled(inst0, s)
            for kind, fn in (('core', run_core_icf), ('full', run_icf)):
                t = time.time()
                r = fn(inst, known * s, name, idx)
                r.update(pos=pos, corpus=c, name=name, idx=idx,
                         scale=s, T=int(max(inst['p'])),
                         kind=kind, wall=round(time.time() - t, 3))
                out.append(r)
                print(f'{pos} {c}/{name}/{idx} s={s} {kind} '
                      f'ok={r.get("ok")} lp={r.get("total_lp", (r.get("pact_lp", 0) or 0) + (r.get("pact_cert_lp", 0) or 0))} '
                      f'k={r.get("core_k")} fb={r.get("fallbacks")} '
                      f't={r["wall"]}', flush=True)
    json.dump(out, open('exp/v8u/core_scaling.json', 'w'))
    print('wrote exp/v8u/core_scaling.json rows', len(out),
          'wall', round(time.time() - t0, 2))
    return out


if __name__ == '__main__':
    main()
