"""Eligibility-aware stress test for v7.3 QSP.

Same construction as exp/v72/elig_stress.py: take the 7 root-fractional
cases, randomly remove one eligible machine from every job, keep
h = OPT_old - 1 (removing eligibility can only raise OPT, so every
variant is still NO).  Runs QUC, QSP-2 and QSP-4/1 side by side and
checks whether support mining produces certificates on the
eligibility-aware path.
"""
import sys, pickle, json, copy, random, time

sys.path[:0] = ['exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']
from quc import QUC
from qsp import QSP

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
    for (name, k, inst, opt, an, al) in pickle.load(
            open('exp/v71/perturb60.pkl', 'rb')):
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
            row = dict(base=name, idx=idx, variant=v)
            q = QUC(inst, opt - 1, unit_budget=6)
            val, st = q.decide()
            row['quc'] = dict(val=val, lp=st['lp_solves'], nodes=st['nodes'],
                              trap=st['trap'] is not None,
                              audit=q.audit_quc())
            for tag, kw in (('qsp2', dict(node_budget=2, internal_budget=0)),
                            ('qsp4', dict(node_budget=4, internal_budget=1))):
                q = QSP(inst, opt - 1, probe_budget=24, **kw)
                val, st = q.decide()
                row[tag] = dict(val=val, lp=st['lp_solves'],
                                nodes=st['nodes'],
                                root_frac=st['root_frac'],
                                probes=st['probes_total'],
                                events=len(q.force_events),
                                mine_fail=st['mine_fail'], why=st['why'],
                                audit=q.audit_qsp())
            rows.append(row)
    out = dict(rows=rows)
    for tag in ('quc', 'qsp2', 'qsp4'):
        out[tag] = dict(
            n=len(rows),
            no=sum(r[tag]['val'] is False for r in rows),
            unk=sum(r[tag]['val'] is None for r in rows),
            lp=sum(r[tag]['lp'] for r in rows),
            nodes=sum(r[tag]['nodes'] for r in rows),
            probes=sum(r[tag].get('probes', 0) for r in rows),
            events=sum(r[tag].get('events', 0) for r in rows),
            mine_fail=sum(r[tag].get('mine_fail', 0) for r in rows),
            root_frac=sum(r[tag].get('root_frac', 0) for r in rows),
            audit=sum(r[tag]['audit'] for r in rows))
        print(tag, out[tag], flush=True)
    out['wall'] = time.time() - t0
    json.dump(out, open('exp/v76/elig_qsp.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
