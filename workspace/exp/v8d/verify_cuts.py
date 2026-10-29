"""Replay every pooled lazy cut against the accepted schedule.

For an edge (i,j), the lazy cut is
    sum_{s<=t+p_i} z[j,s] - sum_{s<=t} z[i,s] <= 0.
Every feasible schedule satisfies it: if s_j <= t+p_i and s_i > t then
s_j < s_i+p_i, violating precedence.  This script checks the structural
edge and the schedule inequality for every cut collected on 252 cases.
"""
import sys
import json
import time

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from hybrid_crisp import HybridCRISP


def main():
    bad = 0
    total = 0
    t0 = time.time()
    for tag, corpus in [('base', base_corpus()),
                        ('pert', pert_corpus()),
                        ('stress', stress_corpus())]:
        for rec in corpus:
            if tag in ('base', 'pert'):
                name, idx, inst, known = rec
            else:
                idx, known, inst = rec
                name = 'stress'
            co = HybridCRISP(inst)
            r = co.optimize()
            s = r['schedule']
            for (i, j, t) in co.cut_pool:
                total += 1
                if j not in inst['succ'][i]:
                    bad += 1
                    print('BAD EDGE', tag, name, idx, i, j, t)
                    continue
                if s is not None:
                    lhs = (1 if s[j] <= t + inst['p'][i] else 0) \
                        - (1 if s[i] <= t else 0)
                    if lhs > 0:
                        bad += 1
                        print('BAD CUT', tag, name, idx, i, j, t,
                              s[i], s[j])
    print('cuts', total, 'bad', bad, 'time', round(time.time() - t0, 1))


if __name__ == '__main__':
    main()
