"""Benchmark PACE-PACT on the 252 corpus and the 80 synthetic large-gap set."""
import sys
import json
import time
import collections

sys.path[:0] = ['exp/v9pa', 'exp/v8b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, run_icf
from pace import run_pace


def load_synth(path='exp/v9i/synthetic.json'):
    d = json.load(open(path))
    out = []
    for r in d['rows']:
        out.append((r['seed'], r['inst'], r['opt']))
    return out


def summarize(rows, label):
    n = len(rows)
    cert = sum(bool(r.get('certified')) for r in rows)
    exact = sum(bool(r.get('L') == r.get('U')) for r in rows)
    approx = sum(bool(r.get('L') is not None and r.get('U') is not None
                      and r.get('U') <= (1.0 + r.get('eps', 0.1))
                      * r.get('L') + 1e-12) for r in rows)
    known = sum(bool(r.get('U') == r.get('known')) for r in rows)
    fail = sum(r.get('partial_fail', 0) for r in rows)
    probes = sum(r.get('probes', 0) for r in rows)
    lp = sum(r.get('lp_solves', 0) for r in rows)
    t = sum(r.get('t', 0.0) for r in rows)
    stages = collections.Counter(r.get('stage') for r in rows)
    regimes = collections.Counter(r.get('regime') for r in rows)
    print(label, 'n', n, 'cert', cert, 'exact', exact, 'approx', approx,
          'known', known, 'probes', probes, 'lp', lp,
          'audit_fail', fail, 't', round(t, 2))
    print('  stages', dict(stages))
    print('  regimes', dict(regimes))
    return dict(n=n, cert=cert, exact=exact, approx=approx, known=known,
                probes=probes, lp=lp, audit_fail=fail, t=round(t, 2),
                stages=dict(stages), regimes=dict(regimes))


def run_corpus(mode, eps, policy='lower-first', init='poly'):
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = run_pace(inst, known, name, idx, eps=eps, mode=mode,
                     policy=policy, init=init)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    print('\n== 252', mode, 'eps', eps, 'policy', policy, 'init', init, 'wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        summarize(rs, c)
    summarize(rows, 'ALL')
    path = 'exp/v9pa/bench_%s_%s_eps%s.json' % (mode, init, str(eps).replace('.', 'p'))
    json.dump(rows, open(path, 'w'), indent=1)
    return rows


def run_synth(mode, eps, policy='lower-first', init='poly'):
    rows = []
    t0 = time.time()
    for seed, inst, known in load_synth():
        r = run_pace(inst, known, 'synth%d' % seed, seed, eps=eps,
                     mode=mode, policy=policy, init=init)
        r['corpus'] = 'synth'
        rows.append(r)
    wall = round(time.time() - t0, 2)
    print('\n== S80', mode, 'eps', eps, 'policy', policy, 'init', init, 'wall', wall)
    summarize(rows, 'S80')
    path = 'exp/v9pa/synth_%s_%s_eps%s.json' % (mode, init, str(eps).replace('.', 'p'))
    json.dump(rows, open(path, 'w'), indent=1)
    return rows


def run_icf_baseline():
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = run_icf(inst, known, name, idx, policy='lower-first')
        r['corpus'] = corpus
        rows.append(r)
    print('\n== ICF baseline wall', round(time.time() - t0, 2))
    summarize(rows, 'ICF-252')
    json.dump(rows, open('exp/v9pa/icf_252.json', 'w'), indent=1)
    return rows


def run_icf_synth():
    rows = []
    t0 = time.time()
    for seed, inst, known in load_synth():
        r = run_icf(inst, known, 'synth%d' % seed, seed,
                    policy='lower-first')
        r['corpus'] = 'synth'
        rows.append(r)
    print('\n== ICF synth wall', round(time.time() - t0, 2))
    summarize(rows, 'ICF-S80')
    json.dump(rows, open('exp/v9pa/icf_synth.json', 'w'), indent=1)
    return rows


if __name__ == '__main__':
    for eps in (0.01, 0.05, 0.1, 0.15, 0.2):
        run_corpus('approx', eps, init='poly')
    run_corpus('exact', 0.1, init='poly')
    for eps in (0.05, 0.1, 0.2):
        run_corpus('approx', eps, init='pact')
    run_corpus('exact', 0.1, init='pact')
    for eps in (0.01, 0.05, 0.1, 0.2, 0.3, 0.5):
        run_synth('approx', eps, init='poly')
    run_synth('exact', 0.1, init='poly')
    for eps in (0.05, 0.1, 0.2):
        run_synth('approx', eps, init='pact')
    run_synth('exact', 0.1, init='pact')
    run_icf_baseline()
    run_icf_synth()
