"""Fault injection for v8.0 BRC: corrupt/fail Farkas extraction."""
import sys, pickle, json, time
sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']
from rdf import RDF

CASES = []
for f, idxs in [('exp/v20/holdout_cases50.pkl', [5, 47]),
                ('exp/v14/large_a.pkl', [5]),
                ('exp/v14/large_het.pkl', [0, 3, 7]),
                ('exp/v13/hard3.pkl', [4])]:
    d = pickle.load(open(f, 'rb'))
    for i in idxs:
        x = d[i]
        inst, opt = (x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
        CASES.append((f.split('/')[-1], i, inst, opt - 1))

MODES = [
    ('clean', dict()),
    ('corrupt1', dict(corrupt_calls=1)),
    ('fail1', dict(fail_calls=1)),
    ('corrupt1_norec', dict(corrupt_calls=1, recover=False)),
    ('fail1_norec', dict(fail_calls=1, recover=False)),
    ('failbig_norec', dict(fail_calls=1000, recover=False)),
]


def main():
    out = []
    for mode, kw in MODES:
        for name, idx, inst, h in CASES:
            t0 = time.time()
            q = RDF(inst, h, yes_scan=False, **kw)
            v, st = q.decide(budget=100, nodecap=5000)
            out.append(dict(mode=mode, name=name, idx=idx, v=v,
                            lp=st['lp_solves'], nodes=st['nodes'],
                            probes=st['probes_total'],
                            recovered=st['recovered'],
                            forced_fail=st['forced_fail'],
                            caught=st['corrupt_caught'],
                            missed=st['corrupt_missed'],
                            missing=st['leaf_missing'],
                            splits=st['ft_splits'], stuck=st['ft_stuck'],
                            audit=q.audit_rdf(), pc=q.proof_complete(),
                            t=round(time.time() - t0, 3)))
    json.dump(out, open('exp/v8a/bench_ft.json', 'w'))
    for mode, _ in MODES:
        rows = [r for r in out if r['mode'] == mode]
        print(mode, 'NO', sum(r['v'] is False for r in rows),
              'UNK', sum(r['v'] is None for r in rows),
              'rec', sum(r['recovered'] for r in rows),
              'forced', sum(r['forced_fail'] for r in rows),
              'caught', sum(r['caught'] for r in rows),
              'missed', sum(r['missed'] for r in rows),
              'missing', sum(r['missing'] for r in rows),
              'splits', sum(r['splits'] for r in rows),
              'stuck', sum(r['stuck'] for r in rows),
              'audit', sum(bool(r['audit']) for r in rows),
              'pc', sum(bool(r['pc']) for r in rows))
    for r in out:
        if r['v'] is not False or not r['audit']:
            print('  !', r)


if __name__ == '__main__':
    main()
