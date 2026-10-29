"""v8.0 BRC benchmark: NO 252 + YES 141."""
import sys, pickle, json, time
sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']
from qnc import QNC
from quc import QUC
from qsp import QSP
from rdf import RDF, check_schedule

FILES = {'holdout': 'exp/v20/holdout_cases50.pkl',
         'synth': 'exp/v28/synth2_45.pkl',
         'large_a': 'exp/v14/large_a.pkl',
         'large_b': 'exp/v14/large_b.pkl',
         'large_het': 'exp/v14/large_het.pkl',
         'hard3': 'exp/v13/hard3.pkl',
         'deep': 'exp/v18/deep.pkl'}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def base_corpus():
    out = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            out.append((name, idx, inst, opt))
    return out


def no_corpus():
    out = [(name, idx, inst, opt - 1, 'base')
           for name, idx, inst, opt in base_corpus()]
    pert = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    for (name, k, inst, opt, an, al) in pert:
        out.append((name, k, inst, opt - 1, 'pert'))
    stress = pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))
    for r in stress:
        out.append(('stress', r['idx'], r['inst'], r['h'], 'stress'))
    return out


def run(cls, inst, h, budget, nodecap, kw=None):
    t0 = time.time()
    q = cls(inst, h, **(kw or {}))
    v, st = q.decide(budget=budget, nodecap=nodecap)
    dt = time.time() - t0
    if hasattr(q, 'audit_rdf'):
        au = q.audit_rdf()
        pc = q.proof_complete()
    elif hasattr(q, 'audit_qsp'):
        au = q.audit_qsp()
        pc = None
    else:
        au = q.audit()
        pc = None
    return q, v, st, dt, au, pc


def main():
    no = no_corpus()
    yes = base_corpus()
    out = {'no': [], 'yes': []}

    print('NO corpus', len(no), flush=True)
    for ci, (name, idx, inst, h, src) in enumerate(no):
        row = dict(name=name, idx=idx, src=src)
        for tag, cls, kw in [
                ('qnc', QNC, {}),
                ('quc', QUC, {}),
                ('qsp', QSP, {}),
                ('rdf', RDF, dict(yes_scan=False))]:
            q, v, st, dt, au, pc = run(cls, inst, h, 100, 5000, kw)
            row[tag] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                            t=round(dt, 4), audit=bool(au), pc=pc,
                            probes=st.get('probes_total'),
                            force=len(st.get('force_events', [])) if
                            st.get('force_events') is not None else None)
        out['no'].append(row)
        if ci % 25 == 0:
            print('NO', ci, flush=True)

    print('YES corpus', len(yes), flush=True)
    for ci, (name, idx, inst, opt) in enumerate(yes):
        row = dict(name=name, idx=idx)
        q, v, st, dt, au, pc = run(QUC, inst, opt, 6, 5000,
                                   dict(unit_budget=6))
        row['quc6'] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                           t=round(dt, 4), audit=bool(au),
                           probes=st.get('unit_probes'))
        q, v, st, dt, au, pc = run(RDF, inst, opt, 100, 5000,
                                   dict(yes_scan=True))
        row['rdf'] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                          t=round(dt, 4), audit=bool(au), pc=pc,
                          why=st.get('why'), yes_calls=st.get('yes_calls'),
                          yes_trials=st.get('yes_trials'),
                          yes_nodes=st.get('yes_nodes'),
                          sched=(q.schedule is not None and
                                 check_schedule(inst, opt, q.schedule,
                                                q.machine)))
        out['yes'].append(row)
        if ci % 25 == 0:
            print('YES', ci, flush=True)

    json.dump(out, open('exp/v8a/bench_rdf.json', 'w'))
    for key in ['no', 'yes']:
        rows = out[key]
        print('\n==', key, len(rows))
        if key == 'no':
            for tag in ['qnc', 'quc', 'qsp', 'rdf']:
                agg = dict(no=0, lp=0, nodes=0, audit=0, pc=0, t=0.0,
                           probes=0)
                for r in rows:
                    a = r[tag]
                    agg['no'] += int(a['v'] is False)
                    agg['lp'] += a['lp']
                    agg['nodes'] += a['nodes']
                    agg['audit'] += int(bool(a['audit']))
                    agg['pc'] += int(bool(a['pc']))
                    agg['t'] += a['t']
                    agg['probes'] += (a['probes'] or 0)
                print(tag, agg)
        else:
            for tag in ['quc6', 'rdf']:
                agg = dict(yes=0, unk=0, no=0, lp=0, nodes=0, audit=0,
                           t=0.0, calls=0, trials=0, ynodes=0, sched=0)
                for r in rows:
                    a = r[tag]
                    agg['yes'] += int(a['v'] is True)
                    agg['unk'] += int(a['v'] is None)
                    agg['no'] += int(a['v'] is False)
                    agg['lp'] += a['lp']
                    agg['nodes'] += a['nodes']
                    agg['audit'] += int(bool(a['audit']))
                    agg['t'] += a['t']
                    if tag == 'rdf':
                        agg['calls'] += a.get('yes_calls') or 0
                        agg['trials'] += a.get('yes_trials') or 0
                        agg['ynodes'] += a.get('yes_nodes') or 0
                        agg['sched'] += int(bool(a.get('sched')))
                print(tag, agg)


if __name__ == '__main__':
    main()
