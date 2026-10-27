import sys
import json
import time
import collections

sys.path[:0] = ['exp/v9talc', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from train import (load_data, samples, build_tree, state_features,
                   FEATURES, action_of)
from loose import rows, init_loose
from pact import pact_decide
from talc import (typed_transition, check_bracket, stream_from_branch,
                  cmax)
from icf import ICFCertificate, PartialCertificate


def folds_of(rows, k=5):
    by = [[] for _ in range(k)]
    for i, r in enumerate(rows):
        by[i % k].append(r)
    return by


def live_one(inst, z, tree, max_probes=64):
    L, U = z['L'], z['U']
    s, m, proof = z['schedule'], z['machine'], z['proof']
    sf = None
    from loose import static_features
    sf = static_features(inst, z['est'], z['q'])
    probes = 0
    lp = z['init_lp']
    unknown = 0
    type_bad = 0
    audits = 0
    t0 = time.time()
    while L < U and probes < max_probes:
        f = state_features(sf, z['L'], z['U'], L, U)
        c = tree.predict([f[k] for k in FEATURES])
        h = action_of(L, U, c)
        tried = [h] + [x for x in ((L + U) // 2, U - 1, L) if x != h]
        moved = False
        for hh in tried:
            if not (L <= hh < U):
                continue
            r = pact_decide(inst, hh, depthcap=None, nodecap=None)
            probes += 1
            lp += r.get('lp_solves', 0)
            if r.get('verdict') is None:
                unknown += 1
                continue
            new, why = typed_transition(inst, L, U, s, m, proof, hh, r)
            if new is None:
                type_bad += 1
                continue
            L2, U2, s2, m2, p2 = new
            if L2 == L and U2 == U:
                continue
            L, U, s, m, proof = L2, U2, s2, m2, p2
            moved = True
            audits += 1
            break
        if not moved:
            break
    final = ICFCertificate(inst, U, s, m, proof) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    stream_ok = False
    if L == U and proof is not None:
        stream_ok = stream_from_branch(proof).audit_rdf()
    return dict(L=L, U=U, known=None, probes=probes, lp=lp,
                unknown=unknown, type_bad=type_bad, audits=audits,
                certified=bool(L == U and final_ok),
                stream=stream_ok, t=round(time.time() - t0, 4))


def main():
    data = load_data()
    allrows = list(rows())
    by = folds_of(data)
    out = []
    for k in range(5):
        test = [i for i in range(len(data)) if i % 5 == k]
        train = [r for j, r in enumerate(data) if j % 5 != k]
        X, y, _ = samples(train, actions='three')
        tree = build_tree(X, y, 0)
        for i in test:
            r = data[i]
            tag, name, idx, inst, known = allrows[i]
            z = init_loose(inst)
            if z is None:
                continue
            res = live_one(inst, z, tree)
            res.update(corpus=tag, name=name, idx=idx, known=known,
                       L0=z['L'], U0=z['U'])
            res['ok'] = bool(res['certified'] and res['L'] == known)
            out.append(res)
    with open('exp/v9talc/live_eval.json', 'w') as f:
        json.dump(out, f)
    print('n', len(out), 'cert', sum(r['certified'] for r in out),
          'stream', sum(r['stream'] for r in out),
          'opt', sum(r['L'] == r['known'] for r in out),
          'probes', sum(r['probes'] for r in out),
          'lp', sum(r['lp'] for r in out),
          'unknown', sum(r['unknown'] for r in out),
          'type_bad', sum(r['type_bad'] for r in out),
          't', round(sum(r['t'] for r in out), 2))


if __name__ == '__main__':
    main()
