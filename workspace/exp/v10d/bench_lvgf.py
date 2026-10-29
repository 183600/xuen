"""Benchmark LV-GF on the 252 corpus and the 80-instance large-gap corpus.

Examples (from workspace/):
  .venv/bin/python exp/v10d/bench_lvgf.py synth
  .venv/bin/python exp/v10d/bench_lvgf.py corpus
  .venv/bin/python exp/v10d/bench_lvgf.py synth-seeds
"""
import sys
import json
import time
import argparse
import collections

sys.path[:0] = ['exp/v10d']
from lvgf import run_lvgf, synthetic_corpus, corpora


def summarize(rows):
    return dict(
        n=len(rows),
        ok=sum(bool(r['ok']) for r in rows),
        certified=sum(bool(r['certified']) for r in rows),
        exact=sum(bool(r['exact']) for r in rows),
        probes=sum(r['probes'] for r in rows),
        lp=sum(r['lp'] for r in rows),
        cert_lp=sum(r['cert_lp'] for r in rows),
        pin_lp=sum(r['pin_lp'] for r in rows),
        total_lp=sum(r['total_lp'] for r in rows),
        splits=sum(r['splits'] for r in rows),
        leaves=sum(r['leaves'] for r in rows),
        max_leaves=max((r['leaves'] for r in rows), default=0),
        lv_trials=sum(r['lv_trials'] for r in rows),
        lv_hits=sum(r['lv_hits'] for r in rows),
        lv_global_hits=sum(r['lv_global_hits'] for r in rows),
        unknown=sum(r['unknown'] for r in rows),
        rank_fail=sum(r['rank_fail'] for r in rows),
        state_fail=sum(r['state_fail'] for r in rows),
        t=round(sum(r['t'] for r in rows), 3),
        reasons=dict(collections.Counter(r['stop_reason'] for r in rows)),
    )


def run_one(rows, tag, cfg):
    out = []
    t0 = time.time()
    for corpus, name, idx, inst, known in rows:
        r = run_lvgf(inst, known, name, idx, **cfg)
        r['corpus'] = corpus
        out.append(r)
    s = summarize(out)
    s['wall'] = round(time.time() - t0, 2)
    s['tag'] = tag
    print(tag, json.dumps(s, sort_keys=True))
    return out, s


SYNTH_CONFIGS = [
    ('single-geo', dict(eps=0.1, cap=None, mode='weak', lv=False,
                        audit_every=1)),
    ('single-geo-lv', dict(eps=0.1, cap=None, mode='weak', lv=True,
                           audit_every=1)),
    ('frontier-cap0', dict(eps=0.1, cap=0, mode='weak', lv=False,
                           audit_every=1)),
    ('frontier-cap0-lv', dict(eps=0.1, cap=0, mode='weak', lv=True,
                              audit_every=1)),
    ('frontier-cap1-lv', dict(eps=0.1, cap=1, mode='weak', lv=True,
                              audit_every=1)),
    ('frontier-cap2-lv', dict(eps=0.1, cap=2, mode='weak', lv=True,
                              audit_every=1)),
    ('cap0-rand-split', dict(eps=0.1, cap=0, mode='weak', lv=False,
                             randomized_split=True, audit_every=1)),
    ('cap0-rand-leaf', dict(eps=0.1, cap=0, mode='weak', lv=False,
                            randomized_leaf=True, audit_every=1)),
    ('cap0-lv-rand-split', dict(eps=0.1, cap=0, mode='weak', lv=True,
                                randomized_split=True, audit_every=1)),
    ('cap0-lv-rand-leaf', dict(eps=0.1, cap=0, mode='weak', lv=True,
                               randomized_leaf=True, audit_every=1)),
]

EPS_CONFIGS = [
    ('eps005', dict(eps=0.05, cap=0, mode='weak', lv=True,
                    audit_every=0)),
    ('eps010', dict(eps=0.10, cap=0, mode='weak', lv=True,
                    audit_every=0)),
    ('eps020', dict(eps=0.20, cap=0, mode='weak', lv=True,
                    audit_every=0)),
    ('eps030', dict(eps=0.30, cap=0, mode='weak', lv=True,
                    audit_every=0)),
]

CORPUS_CONFIGS = [
    ('corpus-single-geo', dict(eps=0.1, cap=None, mode='pact', lv=False,
                               audit_every=1)),
    ('corpus-single-geo-lv', dict(eps=0.1, cap=None, mode='pact', lv=True,
                                  audit_every=1)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('what', choices=('synth', 'eps', 'corpus',
                                     'synth-seeds', 'corpus-cap0'))
    ap.add_argument('--seeds', type=int, default=3)
    args = ap.parse_args()
    if args.what == 'synth':
        rows = list(synthetic_corpus())
        allrows = {}
        summary = {}
        for tag, cfg in SYNTH_CONFIGS:
            out, s = run_one(rows, tag, cfg)
            allrows[tag] = out
            summary[tag] = s
        with open('exp/v10d/bench_lvgf_synth.json', 'w') as f:
            json.dump(dict(summary=summary, rows=allrows), f, indent=1)
    elif args.what == 'eps':
        rows = list(synthetic_corpus())
        allrows = {}
        summary = {}
        for tag, cfg in EPS_CONFIGS:
            out, s = run_one(rows, tag, cfg)
            allrows[tag] = out
            summary[tag] = s
        with open('exp/v10d/bench_lvgf_eps.json', 'w') as f:
            json.dump(dict(summary=summary, rows=allrows), f, indent=1)
    elif args.what == 'corpus':
        rows = list(corpora())
        allrows = {}
        summary = {}
        for tag, cfg in CORPUS_CONFIGS:
            out, s = run_one(rows, tag, cfg)
            allrows[tag] = out
            summary[tag] = s
        with open('exp/v10d/bench_lvgf_corpus.json', 'w') as f:
            json.dump(dict(summary=summary, rows=allrows), f, indent=1)
    elif args.what == 'corpus-cap0':
        rows = list(corpora())
        cfg = dict(eps=0.1, cap=0, mode='pact', lv=True, audit_every=1)
        out, s = run_one(rows, 'corpus-cap0-lv', cfg)
        with open('exp/v10d/bench_lvgf_corpus_cap0.json', 'w') as f:
            json.dump(dict(summary={'corpus-cap0-lv': s}, rows=out),
                      f, indent=1)
    elif args.what == 'synth-seeds':
        rows = list(synthetic_corpus())
        cfg = dict(eps=0.1, cap=0, mode='weak', lv=True, audit_every=0)
        allrows = {}
        summary = {}
        for sd in range(1, args.seeds + 1):
            c = dict(cfg, seed=20261026 + 101 * sd)
            out, s = run_one(rows, 'seed%d' % sd, c)
            allrows['seed%d' % sd] = out
            summary['seed%d' % sd] = s
        with open('exp/v10d/bench_lvgf_seeds.json', 'w') as f:
            json.dump(dict(summary=summary, rows=allrows), f, indent=1)


if __name__ == '__main__':
    main()
