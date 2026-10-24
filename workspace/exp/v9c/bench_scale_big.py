"""v9.0 SCALE-ID scalability benchmark.

Families:
  * replicated hard YES: R disjoint copies of holdout #35 on disjoint
    machine groups; each copy is feasible at h=OPT.
  * replicated hard NO: R disjoint copies of holdout #5 at h=OPT-1.
  * energy overload: n independent jobs on m identical machines with
    total processing > m*h, so h is infeasible by capacity alone.
"""
import sys
import json
import time
import random
import pickle

sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v9c', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from rdf import RDF, check_schedule
from scale import SCALE
from po import make_inst


def replicate(inst, R):
    n0, m0 = inst['n'], inst['m']
    n, m = n0 * R, m0 * R
    p = list(inst['p']) * R
    pred = []
    for r in range(R):
        for i in range(n0):
            pred.append([r * n0 + j for j in inst['pred'][i]])
    elig = []
    for r in range(R):
        for i in range(n0):
            elig.append([r * m0 + k for k in inst['elig'][i]])
    return make_inst(p, m, pred, elig)


def energy_inst(n, m, seed):
    rng = random.Random(seed)
    p = [rng.randint(1, 5) for _ in range(n)]
    h = (sum(p) // m) - 1
    pred = [[] for _ in range(n)]
    elig = [list(range(m)) for _ in range(n)]
    return make_inst(p, m, pred, elig), h


def run(cls, inst, h, budget, nodecap, kw):
    t0 = time.time()
    q = cls(inst, h, **kw)
    v, st = q.decide(budget=budget, nodecap=nodecap)
    dt = time.time() - t0
    au = q.audit_scale() if hasattr(q, 'audit_scale') else q.audit_rdf()
    pc = q.proof_complete()
    sched = (q.schedule is not None and
             check_schedule(inst, h, q.schedule, q.machine))
    return q, v, st, dt, au, pc, sched


def main():
    D = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    yes_inst, yes_opt = D[35]
    no_inst, no_opt = D[5]
    out = {'yes_rep': [], 'no_rep': [], 'energy': []}

    print('replicated hard YES', flush=True)
    for R in [1, 2, 3, 4, 6, 8]:
        inst = replicate(yes_inst, R)
        row = dict(R=R, n=inst['n'], m=inst['m'], h=yes_opt)
        for tag, cls, kw in [
                ('rdf', RDF, dict(yes_scan=True)),
                ('scale', SCALE, dict(yes_scan=True)),
                ('scale_noiso', SCALE, dict(yes_scan=True, iso_on=False))]:
            q, v, st, dt, au, pc, sched = run(cls, inst, yes_opt, 100,
                                              5000, kw)
            row[tag] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                            t=round(dt, 4), audit=bool(au), pc=bool(pc),
                            sched=bool(sched),
                            ynodes=st.get('yes_nodes'),
                            trials=st.get('yes_trials'),
                            comps=st.get('components'),
                            iso=st.get('iso_classes'),
                            iso_saved=st.get('iso_saved'),
                            why=st.get('why'))
        out['yes_rep'].append(row)
        print(' R', R, {k: (row[k]['v'], row[k]['t'], row[k]['lp'],
                            row[k]['ynodes']) for k in
                        ['rdf', 'scale', 'scale_noiso']}, flush=True)

    print('replicated hard NO', flush=True)
    for R in [1, 2, 4, 8, 16]:
        inst = replicate(no_inst, R)
        row = dict(R=R, n=inst['n'], m=inst['m'], h=no_opt - 1)
        for tag, cls in [('rdf', RDF), ('scale', SCALE)]:
            q, v, st, dt, au, pc, sched = run(cls, inst, no_opt - 1, 100,
                                              5000, dict(yes_scan=False))
            row[tag] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                            t=round(dt, 4), audit=bool(au), pc=bool(pc),
                            comps=st.get('components'),
                            iso_saved=st.get('iso_saved'))
        out['no_rep'].append(row)
        print(' R', R, {k: (row[k]['v'], row[k]['t'], row[k]['lp'])
                        for k in ['rdf', 'scale']}, flush=True)

    print('energy overload', flush=True)
    for n, m in [(50, 10), (100, 10), (200, 10), (400, 20)]:
        inst, h = energy_inst(n, m, 1)
        row = dict(n=n, m=m, h=h)
        for tag, cls in [('rdf', RDF), ('scale', SCALE)]:
            q, v, st, dt, au, pc, sched = run(cls, inst, h, 100, 5000,
                                              dict(yes_scan=False))
            row[tag] = dict(v=v, lp=st['lp_solves'], t=round(dt, 4),
                            audit=bool(au), pc=bool(pc),
                            prep=bool(st.get('prep_no')),
                            kind=(st.get('prep_cert') or {}).get('kind'))
        out['energy'].append(row)
        print(' n,m', n, m, {k: (row[k]['v'], row[k]['t'], row[k]['lp'])
                             for k in ['rdf', 'scale']}, flush=True)

    json.dump(out, open('exp/v9c/bench_scale_big.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
