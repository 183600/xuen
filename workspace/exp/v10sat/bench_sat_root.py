"""SAT re-certification of the fixed-h decisions on the corpus.

For each instance:
  NO  at h = known - 1 : SAT refutation + RUP audit
  YES at h = known     : SAT model + check_schedule
Results are written to exp/v10sat/bench_sat_root.json.
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v10sat', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora
from satproof import sat_decide


def run(conf_budget=20000, proof_cap=60000, out=None):
    rows = []
    t0 = time.time()
    for z, (corpus, name, idx, inst, known) in enumerate(corpora()):
        row = dict(corpus=corpus, name=name, idx=idx, known=known,
                   n=inst['n'], m=inst['m'])
        t1 = time.time()
        no = sat_decide(inst, known - 1, conf_budget=conf_budget,
                        proof_cap=proof_cap)
        row['no_t'] = round(time.time() - t1, 4)
        row['no_verdict'] = no['verdict']
        row['no_reason'] = no['stats']['reason']
        row['no_lines'] = no['stats']['proof_lines']
        row['no_sat_t'] = no['stats']['sat_t']
        row['no_rup_t'] = no['stats']['rup_t']
        row['no_cnf_v'] = no['stats']['cnf_vars']
        row['no_cnf_c'] = no['stats']['cnf_clauses']
        row['no_audit'] = bool(no['proof'] is not None
                               and no['proof'].audit_rdf())
        t2 = time.time()
        yes = sat_decide(inst, known, conf_budget=conf_budget,
                         proof_cap=proof_cap)
        row['yes_t'] = round(time.time() - t2, 4)
        row['yes_verdict'] = yes['verdict']
        row['yes_reason'] = yes['stats']['reason']
        row['yes_sat_t'] = yes['stats']['sat_t']
        row['yes_cnf_v'] = yes['stats']['cnf_vars']
        row['yes_cnf_c'] = yes['stats']['cnf_clauses']
        if yes['verdict'] is True:
            row['yes_cmax'] = yes['cmax']
        rows.append(row)
        print(z, corpus, name, idx, 'NO', row['no_verdict'],
              row['no_reason'], row['no_lines'],
              'YES', row['yes_verdict'], row['yes_reason'],
              't', round(row['no_t'] + row['yes_t'], 2), flush=True)
    wall = round(time.time() - t0, 2)
    path = out or 'exp/v10sat/bench_sat_root.json'
    with open(path, 'w') as f:
        json.dump(rows, f, indent=1)
    print('wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs),
              'no', sum(r['no_verdict'] is False for r in rs),
              'no_audit', sum(r['no_audit'] for r in rs),
              'yes', sum(r['yes_verdict'] is True for r in rs),
              'lines', sum(r['no_lines'] for r in rs),
              'sat_t', round(sum(r['no_sat_t'] + r['yes_sat_t']
                                 for r in rs), 2),
              'rup_t', round(sum(r['no_rup_t'] for r in rs), 2),
              't', round(sum(r['no_t'] + r['yes_t'] for r in rs), 2))
    print('all', dict(n=len(rows),
                      no=sum(r['no_verdict'] is False for r in rows),
                      no_audit=sum(r['no_audit'] for r in rows),
                      yes=sum(r['yes_verdict'] is True for r in rows),
                      lines=sum(r['no_lines'] for r in rows),
                      sat_t=round(sum(r['no_sat_t'] + r['yes_sat_t']
                                      for r in rows), 2),
                      rup_t=round(sum(r['no_rup_t'] for r in rows), 2),
                      t=round(sum(r['no_t'] + r['yes_t']
                                  for r in rows), 2)))
    print('no reasons', dict(collections.Counter(r['no_reason']
                                                  for r in rows)))
    print('yes reasons', dict(collections.Counter(r['yes_reason']
                                                   for r in rows)))
    return rows


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget', type=int, default=20000)
    ap.add_argument('--cap', type=int, default=60000)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    run(a.budget, a.cap, a.out)
