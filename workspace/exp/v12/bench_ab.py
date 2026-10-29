"""Benchmark AB-MATCH on the 252 corpus and the 29 wide-gap cases.

Usage:
    python exp/v12/bench_ab.py            # cap=5 + pure MATCH-SPLIT ablation
    python exp/v12/bench_ab.py --sweep    # also sweep kappa in 3..8

The 252 baseline is exp/v8u/bench_icf_lower-first.json.
The 29-case baseline is exp/v9mec/bench_gap.json (policy lower-first).
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v12', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

import icf
from icf import run_icf, corpora
from ab_match import ab_decide, match_decide

GAP_PATH = 'exp/v10c/gap_cases.json'
BASE252 = 'exp/v8u/bench_icf_lower-first.json'
BASEGAP = 'exp/v9mec/bench_gap.json'


def _rows252(decider):
    icf.pact_decide = decider
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = run_icf(inst, known, name, idx, policy='lower-first')
        r['corpus'] = corpus
        rows.append(r)
    return rows, round(time.time() - t0, 2)


def _rowsgap(decider):
    icf.pact_decide = decider
    cases = json.load(open(GAP_PATH))
    rows = []
    t0 = time.time()
    for d in cases:
        r = run_icf(d['inst'], int(d['opt']), d['case'], d.get('idx', 0),
                    policy='lower-first')
        r['case'] = d['case']
        rows.append(r)
    return rows, round(time.time() - t0, 2)


def total(rows):
    return dict(
        n=len(rows), certified=sum(r['certified'] for r in rows),
        ok=sum(r['ok'] for r in rows),
        partial_fail=sum(r['partial_fail'] for r in rows),
        probes=sum(r['queries'] for r in rows),
        search=sum(r['pact_lp'] for r in rows),
        cert=sum(r['pact_cert_lp'] for r in rows),
        pin=sum(r['pin_lp'] for r in rows),
        total=sum(r['pact_lp'] + r['pact_cert_lp'] + r['pin_lp']
                  for r in rows),
        t=round(sum(r['t'] for r in rows), 2))


def show(label, s):
    print('%-22s n=%d cert=%d q=%d search=%d certlp=%d pin=%d total=%d t=%.2fs'
          % (label, s['n'], s['certified'], s['probes'], s['search'],
             s['cert'], s['pin'], s['total'], s['t']))


def main():
    sweep = '--sweep' in sys.argv
    out = {}

    base252 = json.load(open(BASE252))
    basegap = [r for r in json.load(open(BASEGAP))
               if r['policy'] == 'lower-first']
    print('== 252 corpus ==')
    show('baseline lower-first', total(base252))
    pure252, wall = _rows252(match_decide)
    print(' pure wall', wall)
    show('pure MATCH-SPLIT', total(pure252))

    print('== 29 wide-gap cases ==')
    show('baseline lower-first', total(basegap))
    puregap, wall = _rowsgap(match_decide)
    print(' pure wall', wall)
    show('pure MATCH-SPLIT', total(puregap))

    caps = (3, 4, 5, 6, 8) if sweep else (5,)
    cap_rows = {}
    for cap in caps:
        def dec(inst, h, cap=cap, **kw):
            return ab_decide(inst, h, cap=cap, **kw)
        rows252, w252 = _rows252(dec)
        rowsgap, wgap = _rowsgap(dec)
        s252, sgap = total(rows252), total(rowsgap)
        print('-- cap', cap, '252 wall', w252, 'gap wall', wgap)
        show(' AB-MATCH 252', s252)
        show(' AB-MATCH gap', sgap)
        cap_rows[str(cap)] = dict(cap=cap, rows252=rows252,
                                  rowsgap=rowsgap, s252=s252, sgap=sgap,
                                  wall252=w252, wallgap=wgap)

    best = cap_rows[str(caps[-1])] if not sweep else cap_rows['5']
    json.dump(base252, open('exp/v12/base_252.json', 'w'), indent=1)
    json.dump(basegap, open('exp/v12/base_gap.json', 'w'), indent=1)
    json.dump(pure252, open('exp/v12/pure_252.json', 'w'), indent=1)
    json.dump(puregap, open('exp/v12/pure_gap.json', 'w'), indent=1)
    json.dump(best['rows252'], open('exp/v12/bench_ab_252.json', 'w'),
              indent=1)
    json.dump(best['rowsgap'], open('exp/v12/bench_ab_gap.json', 'w'),
              indent=1)
    if sweep:
        json.dump({k: dict(cap=v['cap'], s252=v['s252'], sgap=v['sgap'],
                           wall252=v['wall252'], wallgap=v['wallgap'])
                   for k, v in cap_rows.items()},
                  open('exp/v12/cap_sweep.json', 'w'), indent=1)
    print('wrote exp/v12/{bench_ab_252,bench_ab_gap,...}.json')


if __name__ == '__main__':
    main()
