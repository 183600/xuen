"""Benchmark TAPAS local policy annealing on the 252-instance corpus.

Every probe is mapped to its own corpus row (no (name, idx) collisions).
The baseline is re-run, then SA+tabu searches over branching policies.
The best certificate is re-audited before it is accepted.
"""
import sys
import json
import time

sys.path[:0] = ['exp/v9x', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from pact import pact_decide
from tapas import anneal_policy, _audit_ok, proof_rank


def corpora():
    rid = 0
    for tag, rows in (('base', base_corpus()),
                      ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield rid, tag, name, idx, inst, known
            rid += 1


def main():
    rows = list(corpora())
    yes, no = [], []
    t0 = time.time()
    for rid, tag, name, idx, inst, known in rows:
        r = pact_decide(inst, known, depthcap=None, nodecap=None)
        yes.append(dict(rid=rid, corpus=tag, name=name, idx=idx,
                        h=known, inst=inst, known=known, base=r,
                        base_rank=proof_rank(r)))
        r2 = pact_decide(inst, known - 1, depthcap=None, nodecap=None)
        no.append(dict(rid=rid, corpus=tag, name=name, idx=idx,
                       h=known - 1, inst=inst, known=known, base=r2,
                       base_rank=proof_rank(r2)))
    print('baselines wall', round(time.time() - t0, 2), flush=True)

    yes.sort(key=lambda z: (-z['base']['nodes'], -z['base_rank']))
    hard_yes = yes[:24]
    hard_no = [z for z in no if z['base']['nodes'] > 1]

    out = []
    for j, z in enumerate(hard_yes):
        inst, h = z['inst'], z['h']
        q = anneal_policy(inst, h, budget=30, seed=1000 + 17 * j, lam=2.0)
        b, best = q['baseline'], q['best']
        rec = dict(
            rid=z['rid'], corpus=z['corpus'], name=z['name'], idx=z['idx'],
            label='YES', h=h, known=z['known'],
            base_nodes=b['nodes'], base_rank=proof_rank(b), base_t=b['t'],
            best_nodes=best['nodes'], best_rank=proof_rank(best),
            best_t=best['t'], tune_t=q['t'], evals=q['evals'],
            full=q.get('full'), policy=q['policy'],
            audit_ok=_audit_ok(inst, h, best),
            improved=(best['nodes'], proof_rank(best))
                      < (b['nodes'], proof_rank(b)),
            trace=q['trace'])
        out.append(rec)
        print('YES %2d/%d %-7s %-8s %2d  base %3d/%2d -> best %3d/%2d  '
              'tune %.2fs  audit %s' % (
                  j + 1, len(hard_yes), z['name'], z['idx'], z['idx'],
                  b['nodes'], proof_rank(b), best['nodes'],
                  proof_rank(best), q['t'], rec['audit_ok']), flush=True)

    for j, z in enumerate(hard_no):
        inst, h = z['inst'], z['h']
        q = anneal_policy(inst, h, budget=20, seed=2000 + 17 * j, lam=2.0)
        b, best = q['baseline'], q['best']
        rec = dict(
            rid=z['rid'], corpus=z['corpus'], name=z['name'], idx=z['idx'],
            label='NO', h=h, known=z['known'],
            base_nodes=b['nodes'], base_rank=proof_rank(b), base_t=b['t'],
            best_nodes=best['nodes'], best_rank=proof_rank(best),
            best_t=best['t'], tune_t=q['t'], evals=q['evals'],
            full=q.get('full'), policy=q['policy'],
            audit_ok=_audit_ok(inst, h, best),
            improved=(best['nodes'], proof_rank(best))
                      < (b['nodes'], proof_rank(b)),
            trace=q['trace'])
        out.append(rec)
        print('NO  %2d/%d %-7s %-8s %2d  base %3d/%2d -> best %3d/%2d  '
              'tune %.2fs  audit %s' % (
                  j + 1, len(hard_no), z['name'], z['idx'], z['idx'],
                  b['nodes'], proof_rank(b), best['nodes'],
                  proof_rank(best), q['t'], rec['audit_ok']), flush=True)

    with open('exp/v9x/bench_tapas_local.json', 'w') as f:
        json.dump(out, f, indent=1)
    for lab in ('YES', 'NO'):
        rs = [r for r in out if r['label'] == lab]
        print('\n==', lab, 'n', len(rs),
              'improved', sum(r['improved'] for r in rs),
              'audit', sum(r['audit_ok'] for r in rs),
              'base nodes', sum(r['base_nodes'] for r in rs),
              'best nodes', sum(r['best_nodes'] for r in rs),
              'base rank', sum(r['base_rank'] for r in rs),
              'best rank', sum(r['best_rank'] for r in rs),
              'base t', round(sum(r['base_t'] for r in rs), 2),
              'best t', round(sum(r['best_t'] for r in rs), 2),
              'tune t', round(sum(r['tune_t'] for r in rs), 2))
    print('wall', round(time.time() - t0, 2), 'rows', len(out))


if __name__ == '__main__':
    main()
