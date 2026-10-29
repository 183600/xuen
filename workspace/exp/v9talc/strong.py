import sys

sys.path[:0] = ['exp/v9talc', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide
from talc import cmax
from loose import rows, static_features


def init_strong(inst):
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        return None
    proof = co._ensure_lb_proof(lb)
    if proof is None:
        r = pact_decide(inst, lb - 1, depthcap=None, nodecap=None)
        proof = r['proof'] if r['verdict'] is False else None
    if proof is None:
        return None
    from po import heads_tails
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    return dict(L=int(lb), U=int(ub), schedule=list(sched),
                machine=list(mach), proof=proof,
                init_lp=getattr(co, 'pin_lp', 0), est=est, q=q)


def probe_table(inst, L, U):
    tab = {}
    for h in range(L, U):
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        v = r.get('verdict')
        tab[h] = dict(verdict=(None if v is None else bool(v)),
                      cmax=(cmax(inst, r['schedule'])
                            if v is True else None),
                      lp=int(r.get('lp_solves', 0)),
                      nodes=int(r.get('nodes', 0)),
                      cert_lp=int(r.get('cert_lp', 0)),
                      t=float(r.get('t', 0.0)))
    return tab


def build():
    out = []
    for tag, name, idx, inst, known in rows():
        z = init_strong(inst)
        if z is None:
            out.append(dict(corpus=tag, name=name, idx=idx, known=known,
                            error='init'))
            continue
        sf = static_features(inst, z['est'], z['q'])
        tab = probe_table(inst, z['L'], z['U'])
        out.append(dict(corpus=tag, name=name, idx=idx, known=known,
                        L=z['L'], U=z['U'], init_lp=z['init_lp'],
                        sf=sf,
                        tab={str(h): r for h, r in tab.items()}))
    import json
    with open('exp/v9talc/strong_data.json', 'w') as f:
        json.dump(out, f)
    print('rows', len(out), 'errors', sum('error' in r for r in out),
          'gap0', sum(r.get('L') == r.get('U') for r in out))


if __name__ == '__main__':
    build()
