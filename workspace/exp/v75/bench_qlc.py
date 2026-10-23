"""Benchmark QLC-ALC against QNC (v7.1) and QCC (v7.3)."""
import sys, pickle, json, time, collections
sys.path[:0] = ['exp/v75', 'exp/v73', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC
from qcc import QCC
from qlc import QLC

FILES = {
    'holdout50': 'exp/v20/holdout_cases50.pkl',
    'synth45': 'exp/v28/synth2_45.pkl',
    'large_a': 'exp/v14/large_a.pkl',
    'large_b': 'exp/v14/large_b.pkl',
    'large_het': 'exp/v14/large_het.pkl',
    'hard3': 'exp/v13/hard3.pkl',
    'deep8': 'exp/v18/deep.pkl',
}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def corpus():
    out = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            out.append((name, idx, inst, opt - 1))
    return out


def perturb():
    return [(name, k, inst, opt - 1) for (name, k, inst, opt, an, al)
            in pickle.load(open('exp/v71/perturb60.pkl', 'rb'))]


def branch51():
    return [(r['src'], r['idx'], r['inst'], r['h'])
            for r in pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))]


METHODS = [
    ('qnc', QNC, {}),
    ('qcc', QCC, dict(use_cover=True, cover_min_k=1)),
    ('qlc', QLC, dict(use_cover=True, cover_min_k=1)),
    ('qlc_nocover', QLC, dict(use_cover=False)),
    ('qlc_nocase', QLC, dict(use_cover=True, cover_min_k=1, case_on=False)),
    ('qlc_atom', QLC, dict(use_cover=True, cover_min_k=1,
                           split='largest_atom')),
]


def run(cases, methods=METHODS, budget=30000, nodecap=10000):
    rows = []
    for name, idx, inst, h in cases:
        row = dict(name=name, idx=idx, n=inst['n'], m=inst['m'], h=h)
        for tag, cls, kw in methods:
            t0 = time.time()
            q = cls(inst, h, **kw)
            try:
                v, st = q.decide(budget=budget, nodecap=nodecap)
                ok = q.audit() if hasattr(q, 'audit') else True
            except Exception as e:
                v, st, ok = None, {}, False
                print('ERR', tag, name, idx, repr(e), flush=True)
            row[tag] = dict(v=v, lp=st.get('lp_solves', 0),
                            nodes=st.get('nodes', 0),
                            prunes=st.get('prunes', 0),
                            empty=st.get('empty_prunes', 0),
                            leaves=st.get('leaves', 0),
                            clauses=st.get('clause_db', st.get('clauses', 0)),
                            cover_calls=st.get('cover_calls', 0),
                            cover_hits=st.get('cover_hits', 0),
                            case=st.get('case_branches', 0),
                            prop=st.get('prop_steps', 0),
                            t=time.time() - t0, audit=bool(ok),
                            loss=st.get('loss_events', 0))
        rows.append(row)
    return rows


def agg(rows, key):
    return dict(no=sum(int(r[key]['v'] is False) for r in rows),
                yes=sum(int(r[key]['v'] is True) for r in rows),
                unk=sum(int(r[key]['v'] is None) for r in rows),
                lp=sum(r[key]['lp'] for r in rows),
                nodes=sum(r[key]['nodes'] for r in rows),
                t=round(sum(r[key]['t'] for r in rows), 3),
                audit=sum(int(r[key]['audit']) for r in rows),
                cover_calls=sum(r[key]['cover_calls'] for r in rows),
                cover_hits=sum(r[key]['cover_hits'] for r in rows),
                case=sum(r[key]['case'] for r in rows),
                clauses=sum(r[key]['clauses'] for r in rows))


def main():
    out = {}
    for tag, cases in [('corpus', corpus()), ('pert', perturb()),
                       ('branch51', branch51())]:
        t0 = time.time()
        rows = run(cases)
        out[tag] = dict(rows=rows, wall=round(time.time() - t0, 3),
                        agg={k: agg(rows, k) for k, _, _ in METHODS})
        print(tag, out[tag]['agg'], flush=True)

    rows = out['corpus']['rows'] + out['pert']['rows']
    out['corpus201'] = dict(agg={k: agg(rows, k) for k, _, _ in METHODS})
    print('corpus201', out['corpus201']['agg'], flush=True)

    json.dump(out, open('exp/v75/qlc_bench.json', 'w'), indent=1)
    print('saved exp/v75/qlc_bench.json')


if __name__ == '__main__':
    main()
