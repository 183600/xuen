"""Ablation: hill climbing vs tabu-only vs SA-only vs SA+tabu."""
import sys
import json
import time

sys.path[:0] = ['exp/v9x', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus
from tapas import anneal_policy, proof_rank


def main():
    local = json.load(open('exp/v9x/bench_tapas_local.json'))
    hard = [r for r in local if r['label'] == 'YES'][:6]
    by = {}
    for row in base_corpus():
        if len(row) == 4:
            name, idx, inst, known = row
        else:
            idx, known, inst = row
            name = 'base'
        by[(name, idx)] = (inst, known)
    variants = [('hc', False, False), ('tabu', False, True),
                ('sa', True, False), ('sa_tabu', True, True)]
    out = []
    t0 = time.time()
    for j, z in enumerate(hard):
        inst, known = by[(z['name'], z['idx'])]
        for name, sa, tabu in variants:
            r = anneal_policy(inst, z['h'], budget=20, seed=300 + j,
                              use_sa=sa, use_tabu=tabu,
                              restart_every=0)
            b, q = r['baseline'], r['best']
            rec = dict(name=z['name'], idx=z['idx'], variant=name,
                       base_nodes=b['nodes'], base_rank=proof_rank(b),
                       nodes=q['nodes'], rank=proof_rank(q),
                       tune_t=r['t'], evals=r['evals'],
                       policy=r['policy'])
            out.append(rec)
            print('%-9s %-8s %2d  %3d/%2d -> %3d/%2d  %.2fs' % (
                name, z['name'], z['idx'], b['nodes'], proof_rank(b),
                q['nodes'], proof_rank(q), r['t']), flush=True)
    with open('exp/v9x/bench_tapas_ablation.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('wall', round(time.time() - t0, 2))
    for name, _, _ in variants:
        rs = [r for r in out if r['variant'] == name]
        print(name, 'nodes', sum(r['base_nodes'] for r in rs), '->',
              sum(r['nodes'] for r in rs), 'rank',
              sum(r['base_rank'] for r in rs), '->',
              sum(r['rank'] for r in rs), 'tune',
              round(sum(r['tune_t'] for r in rs), 2))


if __name__ == '__main__':
    main()
