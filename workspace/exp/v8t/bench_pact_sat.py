"""Benchmark PACT-SAT against PACT in one process.

Outputs (under exp/v8t/):
  bench_pact_sat.json     -- 252 PACTSAT rows, two repetitions, per-instance time
  bench_ab_pact_sat.json  -- paired PACT/PACTSAT rows (same process, alternating)
  bench_sat_probes.json   -- SAT vs PACT on every outer-bracket probe

Run: .venv/bin/python exp/v8t/bench_pact_sat.py
"""
import json
import random
import sys
import time
import collections

sys.path[:0] = ['exp/v8t', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from pact import PACT
from pact_sat import PACTSAT, SATWitness


def corpora():
    for tag, rows in (('base', base_corpus()),
                      ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known


def ok_of(r, co, known):
    return bool(r['certified'] and r['opt'] == known
                and r['audit'] and r['proof'] and r['total_audit']
                and r['cert_h'] == known - 1)


def run_ab(reps=2):
    insts = list(corpora())
    rng = random.Random(20261025)
    ab = []
    for rep in range(reps):
        for tag, name, idx, inst, known in insts:
            order = [0, 1]
            rng.shuffle(order)
            for which in order:
                t0 = time.perf_counter()
                if which == 0:
                    co = PACT(inst, pact_depth=3)
                    r = co.optimize()
                else:
                    co = PACTSAT(inst, pact_depth=3)
                    r = co.optimize()
                dt = time.perf_counter() - t0
                ab.append(dict(rep=rep, tag=tag, name=name, idx=idx,
                               which=which, t=dt, ok=ok_of(r, co, known),
                               total=r['total_audit'],
                               pact_lp=getattr(co, 'pact_lp', 0),
                               pact_nodes=getattr(co, 'pact_nodes', 0),
                               sat=getattr(getattr(co, 'sat', None),
                                           'calls', 0),
                               sat_yes=getattr(getattr(co, 'sat', None),
                                               'yes', 0),
                               sat_unknown=getattr(getattr(co, 'sat', None),
                                                   'unknown', 0)))
    with open('exp/v8t/bench_ab_pact_sat.json', 'w') as f:
        json.dump(ab, f, indent=1)
    for rep in range(reps):
        for which, label in ((0, 'PACT'), (1, 'PACTSAT')):
            rs = [r for r in ab if r['rep'] == rep and r['which'] == which]
            print('rep', rep, label, 'wall', round(sum(r['t'] for r in rs), 3),
                  'ok', sum(r['ok'] for r in rs),
                  'total', sum(r['total'] for r in rs),
                  'lp', sum(r['pact_lp'] for r in rs),
                  'nodes', sum(r['pact_nodes'] for r in rs),
                  'sat', sum(r['sat'] for r in rs),
                  'sat_yes', sum(r['sat_yes'] for r in rs))
        for c in ('base', 'pert', 'stress'):
            for which, label in ((0, 'PACT'), (1, 'PACTSAT')):
                rs = [r for r in ab if r['rep'] == rep
                      and r['which'] == which and r['tag'] == c]
                print(' ', c, label, round(sum(r['t'] for r in rs), 3))
    return ab


def run_main(reps=2):
    insts = list(corpora())
    out = []
    for rep in range(reps):
        for tag, name, idx, inst, known in insts:
            t0 = time.perf_counter()
            co = PACTSAT(inst, pact_depth=3)
            r = co.optimize()
            dt = time.perf_counter() - t0
            r.update(name=name, idx=idx, known=known, t=round(dt, 4))
            r['ok'] = ok_of(r, co, known)
            r['corpus'] = tag
            r['rep'] = rep
            r['sat_calls'] = co.sat.calls
            r['sat_yes'] = co.sat.yes
            r['sat_unknown'] = co.sat.unknown
            r['sat_t'] = round(co.sat.time, 4)
            r['pact_nodes'] = co.pact_nodes
            r['pact_lp'] = co.pact_lp
            r['pin_lp'] = getattr(co, 'pin_lp', 0)
            r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
            r['stats2'] = getattr(co, 'stats', {})
            r['steps'] = [(s['h'], s['v'], s.get('engine'))
                          for s in co.steps]
            out.append(r)
    with open('exp/v8t/bench_pact_sat.json', 'w') as f:
        json.dump(out, f, indent=1)
    for rep in range(reps):
        rs = [r for r in out if r['rep'] == rep]
        print('main rep', rep, 'wall', round(sum(r['t'] for r in rs), 3),
              'ok', sum(r['ok'] for r in rs),
              'total', sum(r['total_audit'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'pact_lp', sum(r['pact_lp'] for r in rs),
              'sat', sum(r['sat_calls'] for r in rs),
              'sat_yes', sum(r['sat_yes'] for r in rs),
              'sat_unknown', sum(r['sat_unknown'] for r in rs),
              'sat_t', round(sum(r['sat_t'] for r in rs), 2))
    return out


def run_probes():
    insts = {(tag, name, idx): (known, inst)
             for tag, name, idx, inst, known in corpora()}
    probes = []
    for tag, name, idx, inst, known in corpora():
        co = PACT(inst, pact_depth=3)
        co.optimize()
        for s in co.steps:
            h = s['h']
            label = s['v']
            # time PACT's decision on this probe is not separable here;
            # record the SAT side and the h/label pair.
            w = SATWitness(inst)
            t0 = time.perf_counter()
            got = w.solve(h)
            dt = time.perf_counter() - t0
            probes.append(dict(tag=tag, name=name, idx=idx, h=h,
                               label=label, sat_yes=got is not None,
                               sat_t=round(dt, 5),
                               calls=w.calls, yes=w.yes,
                               unknown=w.unknown,
                               schedule_ok=(got is not None)))
    with open('exp/v8t/bench_sat_probes.json', 'w') as f:
        json.dump(probes, f, indent=1)
    match = sum((p['label'] is True) == p['sat_yes'] for p in probes)
    print('probes', len(probes), 'match', match,
          'sat_yes', sum(p['sat_yes'] for p in probes),
          'sat_t', round(sum(p['sat_t'] for p in probes), 2))
    return probes


if __name__ == '__main__':
    run_ab(reps=2)
    run_main(reps=2)
    run_probes()
