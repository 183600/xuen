"""Post-hoc proof-tree compression: smaller tree, but pays duplicate LP solves."""
import sys, pickle, json
sys.path[:0] = ['exp/v70', 'exp/v61', 'exp/v60', 'exp/v13']
from dcs import DCS, verify_tree

def main():
    cases = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    out = {}
    for idx in (5, 47):
        inst, opt = cases[idx]; h = opt - 1
        a = DCS(inst, h)
        root, _ = a.build(frozenset(), 500000)
        before = a.stats(root); split0 = root.split
        a.compress(root, 500000)
        after = a.stats(root)
        ok, why = verify_tree(inst, h, root, frozenset(), a.elig_aware)
        out[str(idx)] = dict(before=before, after=after, split0=split0,
                             split=root.split, verify=ok, why=why)
        print(idx, out[str(idx)])
    json.dump(out, open('exp/v70/compress_test.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
