"""Collect singleton-backdoor labels and evaluate PIVOT-1's LOO ranker."""
import json
import sys
import time

sys.path[:0] = ['exp/v8q', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np

from chip import base_corpus, pert_corpus, stress_corpus
from pact import pact_decide
from pivot import PivotRanker, root_features


def corpora():
    for tag, fn in (('base', base_corpus), ('pert', pert_corpus),
                    ('stress', stress_corpus)):
        for row in fn():
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known


def collect():
    groups_x, groups_y, meta = [], [], []
    t0 = time.time()
    uid = 0
    for tag, name, idx, inst, known in corpora():
        uid += 1
        h = known - 1
        X, lp, res = root_features(inst, h)
        if X is None:
            continue
        full = pact_decide(inst, h, depthcap=None, nodecap=None)
        if full['verdict'] is not False or full['leaves'] <= 1:
            continue
        y = []
        good = []
        for i in range(inst['n']):
            r = pact_decide(inst, h, depthcap=None, nodecap=None,
                            branch_jobs=[i])
            y.append(1.0 if r['verdict'] is False else 0.0)
            if r['verdict'] is False:
                good.append(i)
        groups_x.append(X)
        groups_y.append(np.asarray(y))
        meta.append(dict(uid=uid, tag=tag, name=name, idx=idx, n=inst['n'],
                         b_full=len(set(x[0] for x in full['branch_jobs'])),
                         good=good, full_nodes=full['nodes'],
                         full_lp=full['lp_solves'],
                         full_cert=full['cert_lp']))
    print('hard groups', len(groups_x), 'time', round(time.time() - t0, 2))
    return groups_x, groups_y, meta


def loo(groups_x, groups_y):
    hits = {k: 0 for k in range(1, 6)}
    firsts = []
    for gi in range(len(groups_x)):
        tr_x = [groups_x[j] for j in range(len(groups_x)) if j != gi]
        tr_y = [groups_y[j] for j in range(len(groups_y)) if j != gi]
        ranker = PivotRanker.fit_groups(tr_x, tr_y)
        order = ranker.order(groups_x[gi])
        good = set(np.where(groups_y[gi] > 0)[0])
        first = next((k + 1 for k, i in enumerate(order) if i in good),
                     999)
        firsts.append(first)
        for k in hits:
            hits[k] += first <= k
    return hits, firsts


if __name__ == '__main__':
    gx, gy, meta = collect()
    hits, firsts = loo(gx, gy)
    print('LOO', hits, 'avg first', round(sum(firsts) / len(firsts), 3))
    ranker = PivotRanker.fit_groups(gx, gy)
    json.dump(ranker.to_json(), open('exp/v8q/pivot_weights.json', 'w'),
              indent=1)
    json.dump(dict(hits=hits, firsts=firsts, meta=meta),
              open('exp/v8q/pivot_loo.json', 'w'), indent=1)
    print('weights saved')
