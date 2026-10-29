"""Eligibility-aware stress test for v7.2 QUC.

Take the 7 root-fractional trap cases, randomly remove one eligible machine
from every job, and keep h = OPT_old - 1.  Removing eligibility can only
increase OPT, so every variant is still NO.  The test exercises the
eligibility-aware column deletion/support/Farkas path; it is not part of
the main 201-case table.
"""
import sys, pickle, json, copy, random, time
sys.path[:0] = ['exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from quc import QUC

FILES = {
    'holdout50': 'exp/v20/holdout_cases50.pkl',
    'synth45': 'exp/v28/synth2_45.pkl',
    'large_a': 'exp/v14/large_a.pkl',
    'large_b': 'exp/v14/large_b.pkl',
    'large_het': 'exp/v14/large_het.pkl',
    'hard3': 'exp/v13/hard3.pkl',
    'deep8': 'exp/v18/deep.pkl'}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def main():
    cases = []
    for idx in (5, 47):
        inst, opt = load(FILES['holdout50'])[idx]
        cases.append(('holdout50', idx, inst, opt))
    pert = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    for (name, k, inst, opt, an, al) in pert:
        if an > 1:
            cases.append((name, k, inst, opt))

    random.seed(1)
    rows = []
    t0 = time.time()
    for name, idx, inst0, opt in cases:
        for v in range(5):
            inst = copy.deepcopy(inst0)
            elig = []
            for i in range(inst['n']):
                e = list(inst['elig'][i])
                if len(e) > 1:
                    e.remove(random.choice(e))
                elig.append(sorted(e))
            inst['elig'] = elig
            q = QUC(inst, opt - 1, unit_budget=6)
            val, st = q.decide()
            rows.append(dict(base=name, idx=idx, variant=v, val=val,
                             lp=st['lp_solves'], nodes=st['nodes'],
                             root_frac=st['root_frac'],
                             probes=st['unit_probes'],
                             forced=st['unit_forced'],
                             trap=st['trap'], cross=st['cross'],
                             audit=q.audit_quc()))
    summary = dict(
        n=len(rows),
        no=sum(r['val'] is False for r in rows),
        unknown=sum(r['val'] is None for r in rows),
        root_frac=sum(r['root_frac'] for r in rows),
        traps=sum(r['trap'] is not None for r in rows),
        audit=sum(r['audit'] for r in rows),
        wall=time.time() - t0)
    out = dict(summary=summary, rows=rows)
    json.dump(out, open('exp/v72/elig_stress.json', 'w'), indent=1)
    print(summary)


if __name__ == '__main__':
    main()
