"""v8.4 CCB benchmark: v8.1 CRISP, v8.3 Hybrid, CCB, CCBHybrid."""
import sys
import json
import time

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import (base_corpus, pert_corpus, stress_corpus,
                  corpus_rows, run)
from chip import CRISP
from hybrid_crisp import HybridCRISP
from ccb import CCB, CCBHybrid


def corpus():
    return [('base', base_corpus()), ('pert', pert_corpus()),
            ('stress', stress_corpus())]


def run_one(cls, inst, known, name, idx):
    t0 = time.time()
    co = cls(inst)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    r['lifts'] = b.get('lifts')
    r['drops'] = b.get('drops')
    r['cert_bad'] = b.get('cert_bad')
    r['cache_hits'] = getattr(co, 'cache_hits', 0)
    r['proof_kind'] = getattr(co, 'lb_proof', None)
    r['proof_kind'] = type(r['proof_kind']).__name__ if r['proof_kind'] else None
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    r['proof_kind'] = r['proof_kind']
    return r


def agg(rows):
    return dict(n=len(rows),
                cert=sum(bool(r['certified']) for r in rows),
                ok=sum(bool(r['ok']) for r in rows),
                q=sum(r['queries'] for r in rows),
                hits=sum(r.get('cache_hits') or 0 for r in rows),
                lp=sum(r['lp'] for r in rows),
                yn=sum(r['yes_nodes'] for r in rows),
                mc=sum(r['mc_evals'] for r in rows),
                t=round(sum(r['t'] for r in rows), 3),
                bound=sum(r.get('proof_kind') == 'BoundProof' for r in rows),
                energy=sum(r.get('proof_kind') == 'PrepProof' for r in rows),
                rdf=sum(r.get('proof_kind') not in ('BoundProof', 'PrepProof')
                        for r in rows))


def main():
    methods = [('crisp', CRISP), ('hybrid', HybridCRISP),
               ('ccb', CCB), ('ccbhybrid', CCBHybrid)]
    out = {}
    for tag, rows in corpus():
        for name, cls in methods:
            print(tag, name, flush=True)
            t0 = time.time()
            rs = []
            for rec in rows:
                if tag in ('base', 'pert'):
                    nm, idx, inst, known = rec
                else:
                    idx, known, inst = rec
                    nm = 'stress'
                rs.append(run_one(cls, inst, known, nm, idx))
            out.setdefault(name, {})[tag] = rs
            print(' ', name, agg(rs), 'wall', round(time.time() - t0, 2),
                  flush=True)
    json.dump(out, open('exp/v8d/bench_ccb.json', 'w'), indent=1)
    print('\n== total')
    for name, _ in methods:
        rs = [r for tag in ('base', 'pert', 'stress')
              for r in out[name][tag]]
        print(name, agg(rs))


if __name__ == '__main__':
    main()
