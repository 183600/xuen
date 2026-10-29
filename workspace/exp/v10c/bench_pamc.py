"""Benchmark PAMC on the 252-instance corpus and the weak-bracket suite.

Strong corpus: PACT APEX/PACT initialization (LP pin + LNS + STAB).
Weak corpus: only critical-path / eligibility-load bounds and a greedy
schedule (chip.base_bounds), so initial gaps are 4..13 instead of 0/1/5.
Both methods receive the same certified initial state on the weak suite.

Strong protocol:
  lower-first  : v9.0 ICF-PACT
  ptb-q0       : PAMC with q=0, 48 primal samples (PTB-ICF baseline)
  pamc         : PAMC portfolio: LP-pinned initial state -> first probe
                 at L with 48 samples, then q=4/5 with alpha=8 credit.
  q4/5-48      : fixed q=4/5, 48 samples, no amortized budget

Weak protocol:
  lower-first, binary : v9.0 ICF-PACT policies with the same weak init
  ptb-q0              : q=0, 48 samples
  pamc                : q=4/5, alpha=8, cumulative credit
  q4/5-48             : q=4/5, 48 samples, no budget

Additional sweeps:
  q in {0,1/3,1/2,2/3,4/5,9/10} with 48 samples (Pareto frontier)
  alpha in {4,8,16,32,inf} at q=4/5 (sample/LP tradeoff)
  seeds 0,1,2 for the default PAMC on the weak suite.
"""
import json
import sys
import time
import collections
import statistics

sys.path[:0] = ['exp/v10c', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, run_icf
from bench_ptb import init_weak as _init_weak_import, run_base
from pamc import run_pamc, init_weak, init_strong


def _clean(r):
    r = dict(r)
    r.pop('steps', None)
    r.pop('success_samples', None)
    return r


def summarize(rows, label):
    print('\n==', label, 'n', len(rows))
    for key in ('ok', 'certified', 'audit', 'partial_fail',
                'archive_audit', 'probes', 'primal_calls', 'primal_lp',
                'pact_lp', 'pact_cert_lp', 'total_lp', 'primal_yes',
                'primal_no_root', 'primal_fail', 'primal_samples',
                'archive_drops', 't'):
        if any(key in r for r in rows):
            vals = [r.get(key, 0) or 0 for r in rows]
            print('  %-17s sum=%-8s mean=%.3f' %
                  (key, sum(vals), statistics.mean(vals)))
    print('  gap hist', dict(sorted(collections.Counter(
        r['ub0'] - r['lb0'] for r in rows).items())))


def run_strong():
    out = {}
    cases = list(corpora())
    configs = [
        ('lower-first', None),
        ('ptb-q0', dict(q=0.0, alpha=1e9, credit_mode='reset')),
        ('q4/5-48', dict(q=0.8, alpha=1e9, credit_mode='reset')),
        ('pamc', dict(q=0.8, alpha=8.0, credit_mode='cumulative',
                      q_first=0.0, k_first=48)),
    ]
    for label, kw in configs:
        t0 = time.time()
        rows = []
        if label == 'lower-first':
            for corpus, name, idx, inst, known in cases:
                r = run_icf(inst, known, name, idx,
                            policy='lower-first')
                r['corpus'] = corpus
                rows.append(r)
        else:
            for corpus, name, idx, inst, known in cases:
                initial = init_strong(inst)
                pin = initial[5] if initial else 0
                kw2 = dict(kw)
                if label == 'pamc' and pin <= 0:
                    kw2['q_first'] = None
                    kw2['k_first'] = None
                r = run_pamc(inst, known, name, idx,
                             initial=initial, **kw2)
                r['corpus'] = corpus
                rows.append(r)
        out[label] = [_clean(r) for r in rows]
        print('\nSTRONG', label, 'wall', round(time.time() - t0, 2))
        summarize(out[label], 'strong/' + label)
    return out


def weak_cases():
    cases = []
    for corpus, name, idx, inst, known in corpora():
        initial = init_weak(inst)
        if initial is not None and initial[1] - initial[0] >= 4:
            cases.append((corpus, name, idx, inst, known, initial))
    return cases


def run_weak_config(label, cases, kw, seed=0, initial_fn=None):
    t0 = time.time()
    rows = []
    for corpus, name, idx, inst, known, initial in cases:
        if initial_fn is not None:
            ini = initial_fn(inst, initial)
        else:
            ini = initial
        r = run_pamc(inst, known, name, idx, initial=ini,
                     seed=seed, **kw)
        r['corpus'] = corpus
        rows.append(r)
    print('\nWEAK', label, 'seed', seed, 'wall',
          round(time.time() - t0, 2))
    summarize(rows, 'weak/' + label)
    return rows


def run_weak():
    cases = weak_cases()
    print('weak cases', len(cases))
    out = dict(pareto={}, budget={}, seeds={})

    # v9.0 baselines on the same initial state.
    for pol in ('lower-first', 'binary'):
        rows = []
        for corpus, name, idx, inst, known, initial in cases:
            r = run_base(inst, known, name, idx, initial[:5], pol,
                         escape=True)
            r['corpus'] = corpus
            rows.append(r)
        out[pol] = [_clean(r) for r in rows]
        summarize(out[pol], 'weak/' + pol)

    # PTB and PAMC defaults.
    out['ptb-q0'] = [_clean(r) for r in run_weak_config(
        'ptb-q0', cases,
        dict(q=0.0, alpha=1e9, credit_mode='reset'))]
    out['q4/5-48'] = [_clean(r) for r in run_weak_config(
        'q4/5-48', cases,
        dict(q=0.8, alpha=1e9, credit_mode='reset'))]
    out['pamc'] = [_clean(r) for r in run_weak_config(
        'pamc', cases,
        dict(q=0.8, alpha=8.0, credit_mode='cumulative'))]

    # q Pareto sweep, fixed 48 samples.
    for q in (0.0, 1.0 / 3.0, 0.5, 2.0 / 3.0, 0.8, 0.9):
        label = 'q=%.4f' % q
        out['pareto'][label] = [_clean(r) for r in run_weak_config(
            label, cases,
            dict(q=q, alpha=1e9, credit_mode='reset'))]

    # Amortized sample budget ablation at q=4/5.
    for alpha in (4.0, 8.0, 16.0, 32.0, 1e9):
        label = 'alpha=%.1f' % alpha
        out['budget'][label] = [_clean(r) for r in run_weak_config(
            label, cases,
            dict(q=0.8, alpha=alpha,
                 credit_mode='reset' if alpha >= 1e8
                 else 'cumulative'))]

    # Seed robustness of the default.
    for seed in (0, 1, 2):
        out['seeds']['seed=%d' % seed] = [_clean(r) for r in
            run_weak_config('pamc', cases,
                            dict(q=0.8, alpha=8.0,
                                 credit_mode='cumulative'),
                            seed=seed)]
    return out


def pareto_stats(rows):
    lp = sum(r['total_lp'] for r in rows)
    pr = sum(r['probes'] for r in rows)
    sm = sum(r.get('primal_samples', 0) for r in rows)
    return dict(n=len(rows), probes=pr, total_lp=lp,
                samples=sm, ok=sum(bool(r['ok']) for r in rows),
                partial_fail=sum(r.get('partial_fail', 0) for r in rows))


def split_stats(rows, train=True):
    rs = []
    for i, r in enumerate(rows):
        if (i % 2 == 0) == train:
            rs.append(r)
    return pareto_stats(rs)


def main():
    strong = run_strong()
    weak = run_weak()

    out = dict(strong=strong, weak=weak)
    with open('exp/v10c/bench_pamc.json', 'w') as f:
        json.dump(out, f, indent=1)

    print('\n== PARETO frontier (weak, fixed 48) ==')
    frontier = []
    for label, rows in sorted(weak['pareto'].items()):
        s = pareto_stats(rows)
        frontier.append((label, s['probes'], s['total_lp'],
                         s['samples'], s['ok']))
        print(label, s)
    print('\n== TRAIN/TEST split of q sweep ==')
    for label, rows in sorted(weak['pareto'].items()):
        print(label, 'train', split_stats(rows, True),
              'test', split_stats(rows, False))
    print('\n== AMORTIZED budget (weak, q=4/5) ==')
    for label, rows in sorted(weak['budget'].items()):
        print(label, pareto_stats(rows))
    print('\n== SEEDS ==')
    for label, rows in sorted(weak['seeds'].items()):
        print(label, pareto_stats(rows))


if __name__ == '__main__':
    main()
