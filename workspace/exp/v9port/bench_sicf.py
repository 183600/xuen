"""Benchmark SICF-P on the 252-instance corpus.

Variants:
  scratch       local certified init + ICF lower-first, one instance at a time
  strong        v9.0 PACT init (LP pin + LNS + STAB) + ICF lower-first
  arrival       SICF stream in corpus arrival order
  random        SICF stream in a fixed random order
  sweep         batch two-sided dominance sweep from a cheap seed
  sweep-lower   sweep with a fixed lower-first policy (provenance ablation)
  sweep-upper   sweep with a fixed upper-first policy (provenance ablation)
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v9port', 'exp/v8u', 'exp/v8c', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v60', 'exp/v13', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61']

from sicf import (all_rows, group_rows, instance_key, dominates,
                  run_stream, run_from_scratch, run_strong, run_hybrid,
                  summarize, local_init)
from icf import corpora


def group_stats(rows):
    groups = group_rows(rows)
    out = []
    for key, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        pairs = 0
        strict = 0
        for i, a in enumerate(rs):
            for j, b in enumerate(rs):
                if i == j:
                    continue
                if dominates(a[3], b[3]):
                    pairs += 1
                    if not dominates(b[3], a[3]):
                        strict += 1
        out.append(dict(size=len(rs), n=key[0], m=key[1],
                        pairs=pairs, strict=strict,
                        names=dict(collections.Counter(r[1] for r in rs)),
                        opts=dict(collections.Counter(r[4] for r in rs))))
    return out


def per_group(rows, groups):
    out = {}
    for key, rs in groups.items():
        keys = {(r[0], r[1], r[2]) for r in rs}
        sub = [r for r in rows if (r.get('corpus'), r.get('name'),
                                   r.get('idx')) in keys]
        if not sub:
            continue
        out[str(key)] = summarize(sub)
    return out


def main():
    rows = all_rows()
    groups = group_rows(rows)
    print('instances', len(rows), 'groups', len(groups))
    gs = group_stats(rows)
    for g in gs[:4]:
        print('group', g['n'], g['m'], 'size', g['size'],
              'pairs', g['pairs'], 'strict', g['strict'],
              'names', g['names'], 'opts', g['opts'])

    variants = {}
    caches = {}

    t0 = time.time()
    scratch, wall = run_from_scratch(rows, policy='lower-first')
    variants['scratch'] = scratch
    print('\nscratch', summarize(scratch, wall))

    t0 = time.time()
    strong, wall = run_strong(rows, policy='lower-first')
    variants['strong'] = strong
    print('strong', summarize(strong, wall))

    for order, tag, kwargs in (
            ('arrival', 'arrival', {}),
            ('random', 'random', {'seed': 0}),
            ('sweep', 'sweep', {'seed_rule': 'min_gap'}),
            ('sweep', 'sweep-maxcov', {'seed_rule': 'max_cov'}),
            ('sweep', 'sweep-lower', {'policy_mode': 'lower'}),
            ('sweep', 'sweep-upper', {'policy_mode': 'upper'})):
        t0 = time.time()
        out, cache, wall = run_stream(rows, order=order,
                                      policy_mode=kwargs.pop(
                                          'policy_mode', 'prov'),
                                      **kwargs)
        variants[tag] = out
        caches[tag] = cache
        s = summarize(out, wall)
        s['cache'] = len(cache.entries)
        s['lb_hits'] = cache.lb_hits
        s['ub_hits'] = cache.ub_hits
        s['checks'] = cache.checks
        s['groups'] = per_group(out, groups)
        print(tag, {k: v for k, v in s.items() if k != 'groups'})

    for tag, pm, spm, sr in (
            ('hybrid-upper', 'upper', 'upper', 'min_gap'),
            ('hybrid-lower', 'lower', 'lower', 'min_gap'),
            ('hybrid-prov', 'prov', 'prov', 'min_gap'),
            ('hybrid-mixed', 'upper', 'lower', 'min_gap'),
            ('hybrid-mixed-maxcov', 'upper', 'lower', 'max_cov'),
            ('hybrid-mixed-median', 'upper', 'lower', 'median')):
        t0 = time.time()
        out, cache, wall = run_hybrid(rows, policy_mode=pm,
                                      seed_policy_mode=spm,
                                      seed_rule=sr)
        variants[tag] = out
        caches[tag] = cache
        s = summarize(out, wall)
        s['cache'] = len(cache.entries)
        s['lb_hits'] = cache.lb_hits
        s['ub_hits'] = cache.ub_hits
        s['checks'] = cache.checks
        s['groups'] = per_group(out, groups)
        print(tag, {k: v for k, v in s.items() if k != 'groups'})

    # Reuse ablation on the two large groups only.
    for gi, (key, rs) in enumerate(
            [kv for kv in sorted(groups.items(), key=lambda kv: -len(kv[1]))
             if len(kv[1]) >= 50]):
        print('\n== large group', gi, 'size', len(rs), '==')
        for tag in ('scratch', 'strong', 'arrival', 'random',
                    'sweep', 'sweep-lower', 'sweep-upper',
                    'hybrid-upper', 'hybrid-lower', 'hybrid-prov',
                    'hybrid-mixed', 'hybrid-mixed-maxcov',
                    'hybrid-mixed-median'):
            sub = [r for r in variants[tag]
                   if (r.get('corpus'), r.get('name'), r.get('idx'))
                   in {(x[0], x[1], x[2]) for x in rs}]
            s = summarize(sub)
            print(tag, s)

    # Cache/dominance diagnostics for the sweep.
    sweep = variants['sweep']
    dom_no = sum(1 for r in sweep
                 if r.get('lb_proof') is not None
                 and getattr(r.get('lb_proof'), 'kind', None) == 'dom-no')
    dom_fail = 0
    for r in sweep:
        p = r.get('lb_proof')
        if p is not None and getattr(p, 'kind', None) == 'dom-no':
            if not p.audit_rdf():
                dom_fail += 1
    print('\nsweep dom-no', dom_no, 'dom_fail', dom_fail)

    out = dict(
        instances=len(rows),
        groups=gs,
        variants={k: summarize(v) for k, v in variants.items()},
        sweep_cache=len(caches['sweep'].entries),
        dom_no=dom_no,
        dom_fail=dom_fail,
    )
    with open('exp/v9port/bench_sicf.json', 'w') as f:
        json.dump(out, f, indent=1)
    for tag, v in variants.items():
        with open('exp/v9port/bench_sicf_%s.json' % tag, 'w') as f:
            json.dump([{k: val for k, val in r.items()
                        if k not in ('lb_proof', 'schedule', 'machine')}
                       for r in v], f, indent=1)
    print('\nwrote exp/v9port/bench_sicf.json')


if __name__ == '__main__':
    main()
