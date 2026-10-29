"""Benchmark v7.4 QMC-ALC against v7.1 QNC and the cover-only QCC layer.

Outputs exp/v74/qmc_bench.json:
  corpus201 : 141 NO + 60 perturbed cases, QNC / QCC / QMC
  hard51    : idx5/47 mutation set, QNC / QCC / QMC
  branch7   : the 2 originals + 5 perturbed branch cases
  anytime51 : NO count vs per-case LP budget
"""
import sys, pickle, json, time
sys.path[:0] = ['exp/v74', 'exp/v81', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC
from qcc import QCC
from qmc import QMC

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


def corpus201():
    out = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            out.append((name, idx, inst, opt - 1))
    for row in pickle.load(open('exp/v71/perturb60.pkl', 'rb')):
        out.append((row[0], row[1], row[2], row[3] - 1))
    return out


def one(inst, h, budget=100000):
    rows = {}
    for tag, cls, kw in [
        ('q', QNC, {}),
        ('c', QCC, {}),
        ('m', QMC, dict(core_cap=8)),
    ]:
        t0 = time.time()
        x = cls(inst, h, **kw)
        v, st = x.decide(budget=budget)
        rows[tag] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                         t=time.time() - t0, why=st['why'],
                         covers=st.get('cover_added', 0),
                         core=st.get('core_calls', 0),
                         root_cert=st.get('root_cert_ok', None),
                         audit=x.audit())
    return rows


def aggregate(rows):
    out = {}
    for tag in ['q', 'c', 'm']:
        out[tag] = dict(
            no=sum(r[tag]['v'] is False for r in rows),
            lp=sum(r[tag]['lp'] for r in rows),
            nodes=sum(r[tag]['nodes'] for r in rows),
            t=sum(r[tag]['t'] for r in rows),
            max_lp=max(r[tag]['lp'] for r in rows),
            max_nodes=max(r[tag]['nodes'] for r in rows),
        )
    out['cover_root'] = sum(r['m']['why'] == 'cover-root' for r in rows)
    out['audit_m'] = sum(r['m']['audit'] for r in rows)
    out['root_cert'] = sum(bool(r['m']['root_cert']) for r in rows)
    out['core_calls'] = sum(r['m']['core'] for r in rows)
    out['covers'] = sum(r['m']['covers'] for r in rows)
    return out


def main():
    res = {}
    t0 = time.time()
    rows = []
    cases = corpus201()
    for i, (name, idx, inst, h) in enumerate(cases):
        r = one(inst, h)
        r.update(name=name, idx=idx, h=h)
        rows.append(r)
        if (i + 1) % 50 == 0:
            print('201', i + 1, round(time.time() - t0, 1), flush=True)
    res['corpus201'] = dict(rows=rows, agg=aggregate(rows))
    print('CORPUS201', res['corpus201']['agg'], flush=True)

    hard = pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))
    rows = []
    t0 = time.time()
    for r in hard:
        x = one(r['inst'], r['h'])
        x.update(src=r['src'], idx=r['idx'], h=r['h'])
        rows.append(x)
    res['hard51'] = dict(rows=rows, agg=aggregate(rows))
    print('HARD51', res['hard51']['agg'], round(time.time() - t0, 2), flush=True)

    base = load('exp/v20/holdout_cases50.pkl')
    branch = [('holdout', 5, base[5][0], base[5][1] - 1),
              ('holdout', 47, base[47][0], base[47][1] - 1)]
    want = {('h5', 6), ('h5', 16), ('h47', 6), ('h47', 18), ('h47', 26)}
    for name, k, inst, opt, an, al in pickle.load(open('exp/v71/perturb60.pkl', 'rb')):
        if (name, k) in want:
            branch.append((name, k, inst, opt - 1))
    rows = []
    for name, k, inst, h in branch:
        x = one(inst, h)
        x.update(name=name, k=k, h=h)
        rows.append(x)
    res['branch7'] = dict(rows=rows, agg=aggregate(rows))
    print('BRANCH7', res['branch7']['agg'], flush=True)

    anytime = {}
    for k in [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20]:
        counts = {'q': 0, 'c': 0, 'm': 0}
        for r in hard:
            for tag, cls, kw in [('q', QNC, {}), ('c', QCC, {}),
                                 ('m', QMC, dict(core_cap=8))]:
                v, st = cls(r['inst'], r['h'], **kw).decide(budget=k)
                counts[tag] += (v is False)
        anytime[k] = counts
        print('anytime', k, counts, flush=True)
    res['anytime51'] = anytime
    json.dump(res, open('exp/v74/qmc_bench.json', 'w'), indent=1)
    print('wrote exp/v74/qmc_bench.json', round(time.time() - t0, 1))


if __name__ == '__main__':
    main()
