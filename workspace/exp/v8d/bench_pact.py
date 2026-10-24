"""v8.2 PACT benchmark: CRISP v8.1, CCB, PACT-K32, PACT-K64.

All methods use the same corpus and the same CHD oracle.  The only
differences are (a) whether preprocessing NO proofs are first-class and
(b) whether the UB drop includes K random orders.
"""
import sys
import json
import time
import statistics

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import (CRISP, base_corpus, pert_corpus, stress_corpus,
                  simulate_queries)
from ccb import CCB
from pact import PACT, potential_trace, simulate_bracket
from rdf import check_schedule


def corpus():
    return [('base', base_corpus()), ('pert', pert_corpus()),
            ('stress', stress_corpus())]


def run_one(cls, inst, known, name, idx, **kw):
    t0 = time.time()
    co = cls(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    b = getattr(co, 'chip', None) or {}
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    r['orig_lb0'] = b.get('lb0')
    r['orig_ub0'] = b.get('ub0')
    r['orig_span'] = (None if b.get('lb0') is None or b.get('ub0') is None
                      else b['ub0'] - b['lb0'])
    r['pre_lb'] = b.get('lb')
    r['pre_ub'] = b.get('ub')
    r['pre_span'] = (None if b.get('lb') is None or b.get('ub') is None
                     else b['ub'] - b['lb'])
    r['pre_exact'] = bool(b.get('lb') is not None
                          and b.get('lb') == b.get('ub'))
    r['lifts'] = b.get('lifts')
    r['drops'] = b.get('drops')
    r['rand_drops'] = b.get('rand_drops')
    r['cert_bad'] = b.get('cert_bad')
    r['lb_max'] = b.get('lb_max')
    r['n_certs'] = len(b.get('certs_all', b.get('certs', [])))
    r['span'] = (None if r['opt'] is None or r['lb'] is None
                 else r['opt'] - r['lb'])
    r['cache_hits'] = getattr(co, 'cache_hits', 0)
    r['proof_kind'] = (type(co.lb_proof).__name__
                       if getattr(co, 'lb_proof', None) is not None else None)
    r['prep_proofs'] = len(getattr(co, 'prep_proofs', {}))
    r['proofs_ok'] = all(p.audit_rdf()
                         for p in getattr(co, 'prep_proofs', {}).values())
    r['potential_ok'] = potential_trace(r['trace'], r['opt'])
    r['invariant_ok'] = bool(
        r['lb'] is not None and r['opt'] is not None
        and r['lb'] <= known <= r['opt']
        and r['lb'] <= r['opt'])
    r['schedule_ok'] = bool(r['schedule'] is not None
                            and check_schedule(inst, r['opt'],
                                               r['schedule'], r['machine']))
    r['ok_base'] = bool(r['certified'] and r['opt'] == known
                        and r['audit'] and r['proof']
                        and r['cert_h'] == known - 1
                        and r['invariant_ok'] and r['schedule_ok']
                        and r['proofs_ok'])
    r['ok'] = bool(r['ok_base'] and r['potential_ok'])
    return r


def agg(rows):
    return dict(
        n=len(rows),
        cert=sum(bool(r['certified']) for r in rows),
        ok=sum(bool(r['ok']) for r in rows),
        ok_base=sum(bool(r.get('ok_base')) for r in rows),
        q=sum(r['queries'] for r in rows),
        lp=sum(r['lp'] for r in rows),
        yn=sum(r['yes_nodes'] for r in rows),
        mc=sum(r['mc_evals'] for r in rows),
        t=round(sum(r['t'] for r in rows), 3),
        hits=sum(r.get('cache_hits') or 0 for r in rows),
        drops=sum(r.get('drops') or 0 for r in rows),
        rand_drops=sum(r.get('rand_drops') or 0 for r in rows),
        lifts=sum(r.get('lifts') or 0 for r in rows),
        bad=sum(r.get('cert_bad') or 0 for r in rows),
        span_orig=sum((r.get('orig_span') or 0) for r in rows),
        span=sum((r.get('pre_span') or 0) for r in rows),
        pre_exact=sum(bool(r.get('pre_exact')) for r in rows),
        unknown=sum(r.get('unknown') or 0 for r in rows),
        proofs=sum(r.get('prep_proofs') or 0 for r in rows),
        bound=sum(r.get('proof_kind') == 'BoundProof' for r in rows),
        energy=sum(r.get('proof_kind') == 'PrepProof' for r in rows),
        rdf=sum(r.get('proof_kind') not in ('BoundProof', 'PrepProof')
                for r in rows),
        inv=sum(bool(r.get('invariant_ok')) for r in rows),
        sched=sum(bool(r.get('schedule_ok')) for r in rows),
        pok=sum(bool(r.get('proofs_ok')) for r in rows),
        pot=sum(bool(r.get('potential_ok')) for r in rows),
    )


def main():
    methods = [
        ('crisp', CRISP, {}),
        ('ccb', CCB, {}),
        ('pact32', PACT, dict(K=32, seed=20261024)),
        ('pact64', PACT, dict(K=64, seed=20261024)),
    ]
    out = {}
    for tag, rows in corpus():
        for name, cls, kw in methods:
            print(tag, name, flush=True)
            t0 = time.time()
            rs = []
            for rec in rows:
                if tag in ('base', 'pert'):
                    nm, idx, inst, known = rec
                else:
                    idx, known, inst = rec
                    nm = 'stress'
                rs.append(run_one(cls, inst, known, nm, idx, **kw))
            out.setdefault(name, {})[tag] = rs
            print(' ', agg(rs), 'wall', round(time.time() - t0, 2),
                  flush=True)
    json.dump(out, open('exp/v8d/bench_pact.json', 'w'), indent=1)

    print('\n== total')
    for name, _, _ in methods:
        rs = [r for tag in ('base', 'pert', 'stress')
              for r in out[name][tag]]
        print(name, agg(rs))
    print('\n== per corpus')
    for name, _, _ in methods:
        for tag in ('base', 'pert', 'stress'):
            print(name, tag, agg(out[name][tag]))


if __name__ == '__main__':
    main()
