"""Ablations for v7.3 QSP on the 141+60 corpus and the 51 stress set.

Rows: probe operators and their order (units-first / sets-first / mixed),
root-only vs recursive probing, root probe budget, internal probe budget,
probe budget, and a units-only variant without set probes.  Every
configuration is audited (audit_qsp).
"""
import sys, pickle, json, time

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


def sets():
    out = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            out.append((name, idx, inst, opt - 1))
    for (name, k, inst, opt, an, al) in pickle.load(
            open('exp/v71/perturb60.pkl', 'rb')):
        out.append((name, k, inst, opt - 1))
    for n, r in enumerate(pickle.load(open('exp/v81/h5h47_branch.pkl',
                                           'rb'))):
        out.append(('stress', n, r['inst'], r['h']))
    return out


def run(cases, make):
    lp = nd = pt = ev = mu = 0
    ok = 0
    t0 = time.time()
    for name, idx, inst, h in cases:
        q = make(inst, h)
        v, st = q.decide()
        lp += st['lp_solves']
        nd += st['nodes']
        pt += st.get('probes_total', st.get('unit_probes', 0))
        ev += len(getattr(q, 'force_events', []))
        mu += sum(1 for i, a, E, c in getattr(q, 'force_events', [])
                  if len({t for j, t in E if j == i}) >= 2)
        ok += (q.audit_qsp() if hasattr(q, 'audit_qsp')
               else q.audit_quc())
    return dict(lp=lp, nodes=nd, probes=pt, events=ev, multi=mu, audit=ok,
                n=len(cases), t=round(time.time() - t0, 2))


def main():
    allc = sets()
    out = {}
    configs = {
        'quc_u6': lambda i, h: QUC(i, h, unit_budget=6),
        'qsp_units_r4i1': lambda i, h: QSP(i, h, probe_budget=24,
                                           node_budget=4, internal_budget=1),
        'qsp_units_r4i0': lambda i, h: QSP(i, h, probe_budget=24,
                                           node_budget=4, internal_budget=0),
        'qsp_units_r2i0': lambda i, h: QSP(i, h, probe_budget=24,
                                           node_budget=2, internal_budget=0),
        'qsp_units_r2i1': lambda i, h: QSP(i, h, probe_budget=24,
                                           node_budget=2, internal_budget=1),
        'qsp_units_r4i2': lambda i, h: QSP(i, h, probe_budget=24,
                                           node_budget=4, internal_budget=2),
        'qsp_sets_r4i1': lambda i, h: QSP(i, h, probe_budget=24,
                                          node_budget=4, internal_budget=1,
                                          portfolio='sets_first'),
        'qsp_mixed_r4i1': lambda i, h: QSP(i, h, probe_budget=24,
                                           node_budget=4, internal_budget=1,
                                           portfolio='mixed'),
        'qsp_units_pb6': lambda i, h: QSP(i, h, probe_budget=6,
                                          node_budget=4, internal_budget=1),
        'qsp_units_pb12': lambda i, h: QSP(i, h, probe_budget=12,
                                           node_budget=4, internal_budget=1),
        'qsp_nounit_r4i1': lambda i, h: QSP(i, h, probe_budget=24,
                                            node_budget=4, internal_budget=1,
                                            unit_probe=False),
    }
    for tag, make in configs.items():
        sub = {}
        for sec in ('all', 'stress'):
            cs = (allc if sec == 'all' else
                  [c for c in allc if c[0] == sec])
            sub[sec] = run(cs, make)
        out[tag] = sub
        print(tag, {k: v for k, v in sub.items() if k in ('all', 'stress')},
              flush=True)
    json.dump(out, open('exp/v76/qsp_ablation.json', 'w'), indent=1)

    # per-case comparison on stress for the three portfolios
    stress = [c for c in allc if c[0] == 'stress']
    per = []
    for name, idx, inst, h in stress:
        row = {}
        for tag, make in (('quc', lambda i, h: QUC(i, h, unit_budget=6)),
                          ('units', lambda i, h: QSP(
                              i, h, probe_budget=24, node_budget=4,
                              internal_budget=1)),
                          ('sets', lambda i, h: QSP(
                              i, h, probe_budget=24, node_budget=4,
                              internal_budget=1, portfolio='sets_first'))):
            q = make(inst, h)
            v, st = q.decide()
            row[tag] = dict(lp=st['lp_solves'], nodes=st['nodes'],
                            probes=st.get('probes_total',
                                          st.get('unit_probes', 0)),
                            events=len(getattr(q, 'force_events', [])),
                            multi=sum(1 for i2, a, E, c in
                                      getattr(q, 'force_events', [])
                                      if len({t for j, t in E
                                              if j == i2}) >= 2))
        per.append(dict(idx=idx, **row))
    out['per_stress'] = per
    json.dump(out, open('exp/v76/qsp_ablation.json', 'w'), indent=1)
    print('per_stress saved', flush=True)


if __name__ == '__main__':
    main()
