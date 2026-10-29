"""Reproduce the live finite-horizon frontier experiments.

Part 1: find the weak instances whose depth-0 root oracle is UNKNOWN at
h = OPT-1, then close them with the round-synchronous frontier.  The
known OPT is used only to select the decision horizon for this
certificate experiment; it is not used by frontier_decide.

Part 2: plug the frontier oracle into the outer DFR loop on the first
20 weak instances and compare with the complete pact_decide oracle.
"""
import collections
import json
import sys
import time

sys.path[:0] = ['exp/v9dfr', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from dfr import run_dfr
from frontier_round import frontier_decide
from hap import weak_rows
from pact import pact_decide


def part1():
    rows = list(weak_rows(4))
    out = []
    for corpus, name, idx, inst, known, initial in rows:
        h = known - 1
        r0 = pact_decide(inst, h, depthcap=0, nodecap=None)
        if r0['verdict'] is not None:
            continue
        rf = frontier_decide(inst, h, max_rounds=32, max_leaves=512)
        rc = pact_decide(inst, h, depthcap=None, nodecap=None)
        out.append(dict(
            corpus=corpus, name=name, idx=idx, h=h, opt=known,
            fver=rf['verdict'], fok=rf['proof_ok'], R=rf['rounds'],
            leaves=rf['leaves'], splits=rf['splits'], no=rf['no'],
            yes=rf['yes'], unk=rf['unknown'], flp=rf['lp'],
            fnodes=rf['nodes'], cver=rc['verdict'],
            clp=rc['lp_solves'], cnodes=rc['nodes'],
            cdepth=rc.get('depth')))
    json.dump(out, open('exp/v9dfr/frontier52.json', 'w'), indent=1)
    print('frontier decision: n=%d closed_no=%d proof_ok=%d '
          'rounds=%s leaves=%d splits=%d lp=%d vs complete lp=%d'
          % (len(out), sum(r['fver'] is False for r in out),
             sum(bool(r['fok']) for r in out),
             dict(sorted(collections.Counter(r['R'] for r in out).items())),
             sum(r['no'] for r in out), sum(r['splits'] for r in out),
             sum(r['flp'] for r in out), sum(r['clp'] for r in out)))


def part2():
    rows = list(weak_rows(4))[:20]
    for oracle in ('pact', 'frontier'):
        t0 = time.time()
        out = []
        for corpus, name, idx, inst, known, initial in rows:
            r = run_dfr(inst, known, name, idx, policy='seq-binary',
                        initial=initial, oracle=oracle,
                        frontier_kwargs=dict(max_rounds=16,
                                             max_leaves=256))
            out.append(r)
        json.dump(out, open('exp/v9dfr/bench_weak20_%s.json' % oracle,
                            'w'), indent=1)
        print('outer %s: ok=%d cert=%d probes=%d rounds=%d innerR=%d '
              'lp=%d nodes=%d pf=%d t=%.2f'
              % (oracle, sum(r['ok'] for r in out),
                 sum(r['certified'] for r in out),
                 sum(r['probes'] for r in out),
                 sum(r['rounds'] for r in out),
                 sum(r.get('inner_rounds', 0) for r in out),
                 sum(r['pact_lp'] for r in out),
                 sum(r['pact_nodes'] for r in out),
                 sum(r['partial_fail'] for r in out),
                 time.time() - t0))


if __name__ == '__main__':
    part1()
    part2()
