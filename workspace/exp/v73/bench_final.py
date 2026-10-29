"""Final ablation for v7.3 QCC-ALC.

Corpora:
  * 141 NO benchmark (the v6.1/v7.1 corpus)
  * 51 branch cases obtained by mutating holdout idx 5/47 (v8.1 generator)
Methods:
  qnc        v7.1 QNC-ALC baseline
  prop       QCC with clause propagation only (no cover, no case)
  cover2     QCC with cover LP, but only from the second clause
  cover1     QCC with cover LP from the first clause
  full       cover1 + gated case branching
"""
import sys, pickle, time, json, os
sys.path[:0] = ['exp/v73', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC
from qcc import QCC

FILES = {
    'holdout50': 'exp/v20/holdout_cases50.pkl',
    'synth45': 'exp/v28/synth2_45.pkl',
    'large_a': 'exp/v14/large_a.pkl',
    'large_b': 'exp/v14/large_b.pkl',
    'large_het': 'exp/v14/large_het.pkl',
    'hard3': 'exp/v13/hard3.pkl',
    'deep8': 'exp/v18/deep.pkl',
}

METHODS = {
    'qnc': (QNC, {}),
    'prop': (QCC, dict(case_on=False, use_cover=False)),
    'cover2': (QCC, dict(case_on=False, use_cover=True, cover_min_k=2)),
    'cover1': (QCC, dict(case_on=False, use_cover=True, cover_min_k=1)),
    'full': (QCC, dict(case_on=True, use_cover=True, cover_min_k=1,
                       case_max_ratio=0.6)),
}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def run(inst, h):
    out = {}
    for name, (cls, kw) in METHODS.items():
        t0 = time.time()
        q = cls(inst, h, **kw)
        v, st = q.decide(budget=30000, nodecap=10000)
        dt = time.time() - t0
        out[name] = dict(
            v=v, lp=st['lp_solves'], nodes=st['nodes'],
            cover=st.get('cover_hits', 0),
            cover_calls=st.get('cover_calls', 0),
            case=st.get('case_branches', 0),
            prop=st.get('prop_steps', 0),
            empty=st.get('empty_prunes', 0),
            clauses=st.get('clause_db', st.get('clauses', 0)),
            why=st['why'], t=dt, audit=bool(q.audit()) if hasattr(q, 'audit')
            else True)
    return out


def aggregate(rows, name):
    keys = ['lp', 'nodes', 'cover', 'cover_calls', 'case', 'prop', 'empty',
            'clauses', 't']
    agg = {k: sum(r[name][k] for r in rows) for k in keys}
    agg['audit'] = sum(int(r[name]['audit']) for r in rows)
    agg['no'] = sum(int(r[name]['v'] is False) for r in rows)
    return agg


def bench_corpus():
    rows = []
    t0 = time.time()
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            r = run(inst, opt - 1)
            r.update(name=name, idx=idx, h=opt - 1)
            rows.append(r)
    out = dict(rows=rows)
    for name in METHODS:
        out[name] = aggregate(rows, name)
    out['wall'] = time.time() - t0
    print('CORPUS', {k: v for k, v in out.items() if k != 'rows'}, flush=True)
    return out


def bench_branch():
    D = pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))
    rows = []
    for n, r in enumerate(D):
        res = run(r['inst'], r['h'])
        res.update(name=r['src'], idx=r['idx'], n=n, h=r['h'],
                   base=(r['q_lp'], r['q_nodes']))
        rows.append(res)
    out = dict(rows=rows)
    for name in METHODS:
        out[name] = aggregate(rows, name)
    print('BRANCH', {k: v for k, v in out.items() if k != 'rows'}, flush=True)
    return out


if __name__ == '__main__':
    out = dict(corpus=bench_corpus(), branch=bench_branch())
    json.dump(out, open('exp/v73/final.json', 'w'), indent=1)
    print('saved exp/v73/final.json')
