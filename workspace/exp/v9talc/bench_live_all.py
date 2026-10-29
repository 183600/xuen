import sys
import json
import time

sys.path[:0] = ['exp/v9talc', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from train import (load_data, samples, build_tree, state_features,
                   FEATURES, action_of)
from loose import rows, init_loose, static_features
from pact import pact_decide
from talc import typed_transition, stream_from_branch
from icf import ICFCertificate


def fold_trees(data, k=5):
    by = [[] for _ in range(k)]
    for i, r in enumerate(data):
        by[i % k].append(r)
    trees = {}
    for f in range(k):
        train = [r for j in range(k) if j != f for r in by[j]]
        X, y, _ = samples(train, actions='three')
        trees[f] = build_tree(X, y, 0)
    return by, trees


def live_one(inst, z, choose, max_probes=64):
    L, U = z['L'], z['U']
    s, m, proof = z['schedule'], z['machine'], z['proof']
    sf = static_features(inst, z['est'], z['q'])
    probes = 0
    lp = z['init_lp']
    unknown = type_bad = audits = 0
    first = True
    t0 = time.time()
    while L < U and probes < max_probes:
        h = choose(sf, z['L'], z['U'], L, U, first)
        first = False
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
    stream_ok = bool(L == U and proof is not None
                     and stream_from_branch(proof).audit_rdf())
    return dict(L=L, U=U, probes=probes, lp=lp, unknown=unknown,
                type_bad=type_bad, audits=audits,
                certified=bool(L == U and final_ok), stream=stream_ok,
                t=round(time.time() - t0, 4))


def fixed(name):
    def choose(sf, L0, U0, L, U, first):
        if name == 'lower-first':
            return L if first else (L + U) // 2
        if name == 'upper-first':
            return U - 1
        if name == 'binary':
            return (L + U) // 2
        if name == 'pact':
            return L if U - L <= 4 else (L + U) // 2
        raise ValueError(name)
    return choose


def learned_factory(tree):
    def choose(sf, L0, U0, L, U, first):
        f = state_features(sf, L0, U0, L, U)
        c = tree.predict([f[k] for k in FEATURES])
        return action_of(L, U, c)
    return choose


def main():
    data = load_data()
    by, trees = fold_trees(data)
    allrows = list(rows())
    out = {}
    for policy in ('lower-first', 'upper-first', 'binary', 'pact',
                   'learned'):
        rs = []
        t0 = time.time()
        for i, (tag, name, idx, inst, known) in enumerate(allrows):
            z = init_loose(inst)
            choose = (learned_factory(trees[i % 5]) if policy == 'learned'
                      else fixed(policy))
            res = live_one(inst, z, choose)
            res.update(corpus=tag, name=name, idx=idx, known=known,
                       L0=z['L'], U0=z['U'])
            res['opt_ok'] = bool(res['L'] == known and res['U'] == known)
            rs.append(res)
        out[policy] = rs
        print(policy, 'cert', sum(r['certified'] for r in rs),
              'opt', sum(r['opt_ok'] for r in rs),
              'probes', sum(r['probes'] for r in rs),
              'lp', sum(r['lp'] for r in rs),
              'unknown', sum(r['unknown'] for r in rs),
              'type_bad', sum(r['type_bad'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2),
              'wall', round(time.time() - t0, 2), flush=True)
    with open('exp/v9talc/live_all.json', 'w') as f:
        json.dump(out, f)


if __name__ == '__main__':
    main()
