"""Successive-halving HPO for the PRISM branch policy.

The probe set is the 105 fixed-h obligations actually visited by PRISM on
the 252-instance corpus.  A config is scored by

    (unknown, total LP nodes, total certificate LPs, wall time)

lexicographically.  Successive halving starts on a stratified 32-probe
slice, keeps the better half, doubles the slice, and finishes on all 105.
The final split is evaluated by a 5-fold cross-validation of the selected
config versus the SAGE default.
"""
import json
import sys
import time
import random

sys.path[:0] = ['exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from prism import interval_branch_decide, DEFAULT_POLICY


def build_instances():
    out = {}
    uid = 0
    for tag, rows in (('base', base_corpus()), ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            out[uid] = (inst, known)
            uid += 1
    return out


def load_probes():
    log = json.load(open('exp/v8j/probe_log.json'))
    insts = build_instances()
    probes = []
    for row in log:
        inst, known = insts[row['uid']]
        for p in row['probes']:
            probes.append(dict(uid=row['uid'], corpus=row['corpus'],
                               name=row['name'], idx=row['idx'],
                               inst=inst, h=p['h'], v=p['v']))
    return probes


def configs():
    out = []
    for heur in ('mass', 'frac', 'tail', 'succ'):
        for split in (0.25, 0.35, 0.5, 0.65):
            out.append(dict(heur=heur, split=split, side='left',
                            closure=True))
    for side in ('right', 'mass'):
        out.append(dict(heur='mass', split=0.5, side=side,
                        closure=True))
    for split in (0.35, 0.5):
        out.append(dict(heur='mass', split=split, side='left',
                        closure=False))
    return out


def evaluate(cfg, probes, nodecap=160, depthcap=40):
    tot = dict(unknown=0, nodes=0, cert=0, t=0.0)
    for p in probes:
        r = interval_branch_decide(p['inst'], p['h'], nodecap=nodecap,
                                   depthcap=depthcap, policy=cfg)
        if r['verdict'] is None:
            tot['unknown'] += 1
        elif r['verdict'] is False and not r['proof'].audit_rdf():
            tot['unknown'] += 1
        tot['nodes'] += r['nodes']
        tot['cert'] += r['cert_lp']
        tot['t'] += r['t']
    return tot


def score(tot):
    return (tot['unknown'], tot['nodes'], tot['cert'], round(tot['t'], 3))


def successive_halving(probes, seed=0):
    rng = random.Random(seed)
    pool = configs()
    order = list(range(len(probes)))
    rng.shuffle(order)
    rounds = []
    keep = pool
    size = min(32, len(probes))
    while True:
        subset = [probes[j] for j in order[:size]]
        scored = []
        for cfg in keep:
            tot = evaluate(cfg, subset)
            scored.append((score(tot), cfg, tot))
        scored.sort(key=lambda x: x[0])
        rounds.append(dict(size=size, scored=[
            dict(score=s[0], cfg=s[1], tot=s[2]) for s in scored]))
        print('round size', size)
        for s in scored:
            print(' ', s[0], s[1])
        if size == len(probes):
            break
        keep = [s[1] for s in scored[:max(2, len(scored) // 2)]]
        size = min(len(probes), size * 2)
    return rounds, scored[0][1]


def cv(probes, cfg_a, cfg_b, folds=5):
    """Compare two configs by paired 5-fold totals (same folds)."""
    rng = random.Random(7)
    order = list(range(len(probes)))
    rng.shuffle(order)
    out = []
    for f in range(folds):
        sub = [probes[j] for j in order if j % folds == f]
        a = evaluate(cfg_a, sub, nodecap=160, depthcap=40)
        b = evaluate(cfg_b, sub, nodecap=160, depthcap=40)
        out.append(dict(fold=f, n=len(sub), a=a, b=b))
        print('fold', f, 'A', score(a), 'B', score(b))
    return out


if __name__ == '__main__':
    probes = load_probes()
    print('probes', len(probes), 'YES',
          sum(1 for p in probes if p['v'] == 'YES'))
    rounds, best = successive_halving(probes)
    print('selected', best)
    base = dict(DEFAULT_POLICY)
    cvrows = cv(probes, best, base)
    json.dump(dict(rounds=rounds, selected=best, cv=cvrows),
              open('exp/v8j/hpo_results.json', 'w'), indent=1)
