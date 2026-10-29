"""Supervised probe advisor for TALC-PACT on the loose-start corpus.

The label at a state (a,b) is the cheapest first action among

    probe a, probe (a+b)//2, probe b-1

with optimal continuation, computed from a precomputed probe table.  A
small CART is trained per fold; at test time it only sees bracket/static
features, never the probe table.  The learned advice changes order, not
soundness.
"""
import sys
import json
import math
import random
import collections

sys.path[:0] = ['exp/v9talc']
from loose import dp_table, state_features

FEATURES = ['gap', 'a_minus_L0', 'U0_minus_b', 'a', 'b',
            'a_over_cp', 'b_over_cp', 'L0_over_cp', 'U0_over_cp',
            'work_over_mb', 'lower_slack', 'upper_slack', 'gap_over_L',
            'n', 'm', 'cp', 'work', 'maxp', 'meanp', 'edges',
            'edge_density', 'elig_frac', 'work_over_cp',
            'work_over_mcp']


def load_data(path='exp/v9talc/loose_data.json'):
    with open(path) as f:
        rows = json.load(f)
    for r in rows:
        r['tab'] = {int(h): v for h, v in r['tab'].items()}
    return [r for r in rows if 'error' not in r]


def label_of(a, b, h):
    if h == a:
        return 0
    if h == b - 1:
        return 2
    return 1


def action_of(a, b, c):
    return (a, (a + b) // 2, b - 1)[c]


def samples(rows, actions='three'):
    X, y, groups = [], [], []
    for gi, r in enumerate(rows):
        L, U = r['L'], r['U']
        dp = dp_table(r['tab'], L, U, actions=actions)
        for a in range(L, U + 1):
            for b in range(a, U + 1):
                if a == b:
                    continue
                v = dp.get((a, b))
                if v is None or v[1] is None:
                    continue
                h = v[1]
                f = state_features(r['sf'], L, U, a, b)
                X.append([f[k] for k in FEATURES])
                y.append(label_of(a, b, h))
                groups.append(gi)
    return X, y, groups


class Node:
    def __init__(self, counts, feature=None, threshold=None,
                 left=None, right=None):
        self.counts = counts
        self.feature = feature
        self.threshold = threshold
        self.left = left
        self.right = right

    def predict(self, x):
        if self.feature is None:
            return max(range(len(self.counts)),
                       key=lambda k: self.counts[k])
        if x[self.feature] <= self.threshold:
            return self.left.predict(x)
        return self.right.predict(x)


def gini(counts):
    n = sum(counts)
    if n == 0:
        return 0.0
    return 1.0 - sum((c / n) ** 2 for c in counts)


def leaf(counts):
    return Node(counts)


def build_tree(X, y, depth, max_depth=5, min_leaf=16, k=3):
    counts = [0] * k
    for c in y:
        counts[c] += 1
    if depth >= max_depth or len(y) < 2 * min_leaf or max(counts) == len(y):
        return leaf(counts)
    base = gini(counts) * len(y)
    best = None
    nfeat = len(X[0])
    for f in range(nfeat):
        vals = sorted(set(row[f] for row in X))
        if len(vals) <= 1:
            continue
        if len(vals) > 24:
            idx = [int((i + 0.5) * len(vals) / 24)
                   for i in range(24)]
            ths = []
            for i in idx:
                i = min(max(i, 0), len(vals) - 2)
                ths.append((vals[i] + vals[i + 1]) / 2)
            vals = sorted(set(ths))
        else:
            vals = [(vals[i] + vals[i + 1]) / 2
                    for i in range(len(vals) - 1)]
        for t in vals:
            lc = [0] * k
            rc = [0] * k
            nl = nr = 0
            for row, c in zip(X, y):
                if row[f] <= t:
                    lc[c] += 1
                    nl += 1
                else:
                    rc[c] += 1
                    nr += 1
            if nl < min_leaf or nr < min_leaf:
                continue
            score = gini(lc) * nl + gini(rc) * nr
            if best is None or score < best[0]:
                best = (score, f, t, lc, rc)
    if best is None or best[0] >= base - 1e-9:
        return leaf(counts)
    _, f, t, lc, rc = best
    left_X, left_y, right_X, right_y = [], [], [], []
    for row, c in zip(X, y):
        if row[f] <= t:
            left_X.append(row)
            left_y.append(c)
        else:
            right_X.append(row)
            right_y.append(c)
    return Node(counts, f, t,
                build_tree(left_X, left_y, depth + 1, max_depth,
                           min_leaf, k),
                build_tree(right_X, right_y, depth + 1, max_depth,
                           min_leaf, k))


def simulate(row, choose, max_probes=64, fallback=True):
    L, U = row['L'], row['U']
    a, b = L, U
    probes = 0
    lp = 0
    unknown = 0
    hist = []
    while a < b and probes < max_probes:
        h = choose(row, a, b)
        r = row['tab'].get(h)
        if r is None or r['verdict'] is None:
            unknown += 1
            probes += 1
            lp += (r['lp'] if r else 0)
            hist.append((h, None, (r['lp'] if r else 0)))
            if not fallback:
                return dict(closed=False, probes=probes, lp=lp,
                            unknown=unknown, reason='unknown', L=a, U=b,
                            hist=hist)
            cand = []
            for h2 in ((a + b) // 2, b - 1, a):
                r2 = row['tab'].get(h2)
                if h2 != h and r2 is not None and r2['verdict'] is not None:
                    cand.append(h2)
            if not cand:
                return dict(closed=False, probes=probes, lp=lp,
                            unknown=unknown, reason='unknown', L=a, U=b,
                            hist=hist)
            h = cand[0]
            r = row['tab'][h]
        probes += 1
        lp += r['lp']
        hist.append((h, r['verdict'], r['lp']))
        if r['verdict'] is False:
            a = h + 1
        else:
            b = min(b, r['cmax'])
    return dict(closed=(a == b), probes=probes, lp=lp,
                unknown=unknown, reason='ok', L=a, U=b, hist=hist)


def fixed_choose(name):
    first = {'v': True}

    def choose(row, a, b):
        if name == 'lower-first':
            h = a if first['v'] else (a + b) // 2
        elif name == 'upper-first':
            h = b - 1
        elif name == 'binary':
            h = (a + b) // 2
        elif name == 'pact':
            h = a if b - a <= 4 else (a + b) // 2
        else:
            raise ValueError(name)
        first['v'] = False
        return h

    return choose


def oracle_choose(row, a, b):
    dp = row.setdefault('_dp3', dp_table(row['tab'], row['L'], row['U'],
                                        actions='three'))
    v = dp.get((a, b))
    if v is None or v[1] is None:
        return (a + b) // 2
    return v[1]


def choice_acc(tree, rows):
    ok = n = 0
    for r in rows:
        a, b = r['L'], r['U']
        dp = dp_table(r['tab'], a, b, actions='three')
        v = dp.get((a, b))
        if v is None or v[1] is None:
            continue
        f = state_features(r['sf'], r['L'], r['U'], a, b)
        pred = action_of(a, b, tree.predict([f[k] for k in FEATURES]))
        ok += (pred == v[1])
        n += 1
    return ok, n


def aggregate(results):
    return dict(n=len(results),
                closed=sum(r['closed'] for r in results),
                probes=sum(r['probes'] for r in results),
                unknown=sum(r.get('unknown', 0) for r in results),
                lp=sum(r['lp'] for r in results),
                median_probes=(sorted(r['probes'] for r in results)
                               [len(results) // 2] if results else None))


def main():
    rows = load_data()
    for r in rows:
        r['_dp3'] = dp_table(r['tab'], r['L'], r['U'], actions='three')
    folds = 5
    by_fold = [[] for _ in range(folds)]
    for i, r in enumerate(rows):
        by_fold[i % folds].append(r)
    all_learned = []
    all_first = []
    all_oracle = []
    all_oraall = []
    acc_ok = acc_n = 0
    fixed = {name: [] for name in
             ('lower-first', 'upper-first', 'binary', 'pact')}
    for k in range(folds):
        test = by_fold[k]
        train = [r for j in range(folds) if j != k for r in by_fold[j]]
        X, y, _ = samples(train, actions='three')
        tree = build_tree(X, y, 0)
        ok, n = choice_acc(tree, test)
        acc_ok += ok
        acc_n += n
        for r in test:
            def learned(row, a, b, tree=tree):
                f = state_features(row['sf'], row['L'], row['U'], a, b)
                c = tree.predict([f[x] for x in FEATURES])
                return action_of(a, b, c)
            def learned_first(row, a, b, tree=tree):
                if (a, b) != (row['L'], row['U']):
                    return (a + b) // 2
                f = state_features(row['sf'], row['L'], row['U'], a, b)
                c = tree.predict([f[x] for x in FEATURES])
                return action_of(a, b, c)
            all_learned.append(simulate(r, learned))
            all_first.append(simulate(r, learned_first))
            all_oracle.append(simulate(r, oracle_choose))
            dpall = dp_table(r['tab'], r['L'], r['U'], actions='all')
            def ora_all(row, a, b, dpall=dpall):
                v = dpall.get((a, b))
                return v[1] if v and v[1] is not None else (a + b) // 2
            all_oraall.append(simulate(r, ora_all))
            for name in fixed:
                fixed[name].append(simulate(r, fixed_choose(name)))
        print('fold', k, 'train', len(train), 'test', len(test),
              'samples', len(y), 'first_acc', round(ok / max(1, n), 3),
              flush=True)
    print('first-action accuracy', acc_ok, '/', acc_n,
          round(acc_ok / max(1, acc_n), 3))
    print('learned     ', aggregate(all_learned))
    print('learned-first', aggregate(all_first))
    print('oracle3     ', aggregate(all_oracle))
    print('oracle-all  ', aggregate(all_oraall))
    for name, rs in fixed.items():
        print(name.ljust(12), aggregate(rs))
    out = dict(accuracy=[acc_ok, acc_n],
               learned=all_learned, learned_first=all_first,
               oracle3=all_oracle, oracle_all=all_oraall,
               fixed={k: v for k, v in fixed.items()})
    with open('exp/v9talc/learned_eval.json', 'w') as f:
        json.dump(out, f)


if __name__ == '__main__':
    main()
