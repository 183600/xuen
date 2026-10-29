"""YES-side smoke test: h=OPT should return True; audit must pass."""
import sys, pickle, json
sys.path[:0] = ['exp/v73', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qcc import QCC

FILES = ['exp/v20/holdout_cases50.pkl', 'exp/v28/synth2_45.pkl',
         'exp/v13/hard3.pkl', 'exp/v18/deep.pkl',
         'exp/v14/large_a.pkl', 'exp/v14/large_b.pkl',
         'exp/v14/large_het.pkl']


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def main(k=8):
    rows = []
    for f in FILES:
        for idx, (inst, opt) in enumerate(load(f)[:k]):
            q = QCC(inst, opt, case_on=True, use_cover=True)
            v, st = q.decide(budget=30000, nodecap=10000)
            rows.append(dict(file=f, idx=idx, h=opt, yes=(v is True),
                             lp=st['lp_solves'], nodes=st['nodes'],
                             why=st['why'], audit=bool(q.audit())))
    out = dict(rows=rows, n=len(rows),
               yes=sum(r['yes'] for r in rows),
               audit=sum(r['audit'] for r in rows))
    json.dump(out, open('exp/v73/yes.json', 'w'), indent=1)
    print(out['n'], 'cases; YES', out['yes'], '; audit', out['audit'])
    for r in rows:
        if not r['yes'] or not r['audit']:
            print('FAIL', r)


if __name__ == '__main__':
    main()
