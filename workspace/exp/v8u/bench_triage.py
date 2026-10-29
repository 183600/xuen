"""Benchmark TRIAGE-ICF on the 252 corpus and the hard20 corpus.

Run from workspace/:
    .venv/bin/python exp/v8u/bench_triage.py
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8u', 'exp/v9pa', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from triage import run_triage
from icf import corpora


def summarize(rows):
    cert = [r for r in rows if r.get('certified')]
    return dict(
        n=len(rows), certified=len(cert),
        exact=sum(1 for r in cert if r.get('L') == r.get('U')),
        approx=sum(1 for r in cert if r.get('L') != r.get('U')),
        partial=sum(1 for r in rows if not r.get('certified')),
        probes=sum(r.get('probes', 0) for r in rows),
        triage_work=sum(r.get('triage_work', 0) for r in rows),
        tests=sum(r.get('triage_tests', 0) for r in rows),
        t=round(sum(r.get('t', 0) for r in rows), 3),
        triage_t=round(sum(r.get('triage_t', 0) for r in rows), 3),
        ratios=[round((r.get('U', 0) / r.get('L', 1)), 4)
                for r in cert],
    )


def run_corpus(budget=2, init='poly'):
    rows = []
    t0 = time.time()
    for c, name, idx, inst, known in corpora():
        r = run_triage(inst, known, name, idx, budget=budget, init=init)
        r['corpus'] = c
        rows.append(r)
    s = summarize(rows)
    s['wall'] = round(time.time() - t0, 2)
    s['budget'] = budget
    return rows, s


def run_hard20(budget=2, init='poly'):
    d = json.load(open('exp/v9pa/hard20.json'))
    rows = []
    t0 = time.time()
    for c, row in zip(d['cases'], d['rows']):
        r = run_triage(c['inst'], row['opt'], 'h%d' % c['seed'],
                       c['seed'], budget=budget, init=init)
        r['corpus'] = 'hard20'
        r['seed'] = c['seed']
        r['opt'] = row['opt']
        r['exact_baseline_t'] = row['exact_t']
        rows.append(r)
    s = summarize(rows)
    s['wall'] = round(time.time() - t0, 2)
    s['budget'] = budget
    return rows, s


if __name__ == '__main__':
    out = {}
    for budget in (1, 2, 4):
        rows, s = run_corpus(budget=budget)
        out['corpus_b%d' % budget] = dict(summary=s, rows=rows)
        print('corpus b%d' % budget, json.dumps({k: v for k, v in s.items()
                                                 if k != 'ratios'}))
    for budget in (1, 2, 4):
        rows, s = run_hard20(budget=budget)
        out['hard20_b%d' % budget] = dict(summary=s, rows=rows)
        print('hard20 b%d' % budget, json.dumps({k: v for k, v in s.items()
                                                 if k != 'ratios'}))
    json.dump(out, open('exp/v8u/bench_triage.json', 'w'), indent=1)
