import sys
import json
import collections

sys.path[:0] = ['exp/v9talc']
from train import (load_data, samples, build_tree, state_features,
                   FEATURES, action_of, simulate, fixed_choose,
                   oracle_choose, aggregate, dp_table)


def main():
    loose = load_data()
    with open('exp/v9talc/strong_data.json') as f:
        strong = json.load(f)
    for r in strong:
        r['tab'] = {int(h): v for h, v in r['tab'].items()}
    trees = {}
    for k in range(5):
        train = [r for i, r in enumerate(loose) if i % 5 != k]
        X, y, _ = samples(train, actions='three')
        trees[k] = build_tree(X, y, 0)
    out = {}
    for name in ('lower-first', 'upper-first', 'binary', 'pact',
                 'learned', 'learned-first', 'oracle3', 'oracle-all'):
        rs = []
        for i, r in enumerate(strong):
            k = i % 5
            if name == 'learned':
                def choose(row, a, b, tree=trees[k]):
                    f = state_features(row['sf'], row['L'], row['U'], a, b)
                    c = tree.predict([f[x] for x in FEATURES])
                    return action_of(a, b, c)
            elif name == 'learned-first':
                def choose(row, a, b, tree=trees[k]):
                    if (a, b) != (row['L'], row['U']):
                        return (a + b) // 2
                    f = state_features(row['sf'], row['L'], row['U'], a, b)
                    c = tree.predict([f[x] for x in FEATURES])
                    return action_of(a, b, c)
            elif name == 'oracle3':
                def choose(row, a, b):
                    dp = row.setdefault('_dp3', dp_table(
                        row['tab'], row['L'], row['U'], actions='three'))
                    v = dp.get((a, b))
                    return v[1] if v and v[1] is not None else (a + b) // 2
            elif name == 'oracle-all':
                def choose(row, a, b):
                    dp = row.setdefault('_dpa', dp_table(
                        row['tab'], row['L'], row['U'], actions='all'))
                    v = dp.get((a, b))
                    return v[1] if v and v[1] is not None else (a + b) // 2
            else:
                choose = fixed_choose(name)
            rs.append(simulate(r, choose))
        out[name] = rs
        print(name.ljust(12), aggregate(rs))
    with open('exp/v9talc/strong_eval.json', 'w') as f:
        json.dump(out, f, indent=1)


if __name__ == '__main__':
    main()
