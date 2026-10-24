"""v9.0 SCALE-ID benchmark: existing NO 252 and YES 141."""
import sys
import json
import time

sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v9c', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from rdf import RDF, check_schedule
from scale import SCALE
from bench_rdf import base_corpus, no_corpus


def run(cls, inst, h, budget, nodecap, kw=None):
    t0 = time.time()
    q = cls(inst, h, **(kw or {}))
    v, st = q.decide(budget=budget, nodecap=nodecap)
    dt = time.time() - t0
    au = q.audit_scale() if hasattr(q, 'audit_scale') else q.audit_rdf()
    pc = q.proof_complete()
    return q, v, st, dt, au, pc


def main():
    no = no_corpus()
    yes = base_corpus()
    out = {'no': [], 'yes': []}

    print('NO corpus', len(no), flush=True)
    for ci, (name, idx, inst, h, src) in enumerate(no):
        row = dict(name=name, idx=idx, src=src)
        for tag, cls, kw in [
                ('rdf', RDF, dict(yes_scan=False)),
                ('scale', SCALE, dict(yes_scan=False)),
                ('scale_noprep', SCALE, dict(yes_scan=False,
                                             decompose=False,
                                             prep_energy=False,
                                             prep_force=False))]:
            q, v, st, dt, au, pc = run(cls, inst, h, 100, 5000, kw)
            row[tag] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                            t=round(dt, 4), audit=bool(au), pc=bool(pc),
                            probes=st.get('probes_total'),
                            prep=bool(st.get('prep_no')),
                            prep_kind=(st.get('prep_cert') or {}).get('kind'),
                            comps=st.get('components'),
                            iso=st.get('iso_classes'),
                            iso_saved=st.get('iso_saved'),
                            forced=len(st.get('window_forces') or {}),
                            id_nodes=st.get('id_nodes'))
        out['no'].append(row)
        if ci % 50 == 0:
            print('NO', ci, flush=True)

    print('YES corpus', len(yes), flush=True)
    for ci, (name, idx, inst, opt) in enumerate(yes):
        row = dict(name=name, idx=idx)
        for tag, cls in [('rdf', RDF), ('scale', SCALE)]:
            q, v, st, dt, au, pc = run(cls, inst, opt, 100, 5000,
                                       dict(yes_scan=True))
            row[tag] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                            t=round(dt, 4), audit=bool(au), pc=bool(pc),
                            why=st.get('why'),
                            yes_calls=st.get('yes_calls'),
                            yes_trials=st.get('yes_trials'),
                            yes_nodes=st.get('yes_nodes'),
                            id_nodes=st.get('id_nodes'),
                            comps=st.get('components'),
                            iso=st.get('iso_classes'),
                            forced=len(st.get('window_forces') or {}),
                            sched=(q.schedule is not None and
                                   check_schedule(inst, opt, q.schedule,
                                                  q.machine)))
        out['yes'].append(row)
        if ci % 25 == 0:
            print('YES', ci, flush=True)

    json.dump(out, open('exp/v9c/bench_scale.json', 'w'))
    print('\n== NO', len(out['no']))
    for tag in ['rdf', 'scale', 'scale_noprep']:
        a = dict(no=0, lp=0, nodes=0, t=0.0, audit=0, pc=0, prep=0,
                 comps=0, iso_saved=0)
        for r in out['no']:
            x = r[tag]
            a['no'] += int(x['v'] is False)
            a['lp'] += x['lp']
            a['nodes'] += x['nodes']
            a['t'] += x['t']
            a['audit'] += int(x['audit'])
            a['pc'] += int(x['pc'])
            a['prep'] += int(x.get('prep') or 0)
            a['comps'] += int(bool(x.get('comps')))
            a['iso_saved'] += int(x.get('iso_saved') or 0)
        a['t'] = round(a['t'], 3)
        print(tag, a)
    print('\n== YES', len(out['yes']))
    for tag in ['rdf', 'scale']:
        a = dict(yes=0, unk=0, no=0, lp=0, nodes=0, ynodes=0, trials=0,
                 id_nodes=0, t=0.0, audit=0, sched=0)
        for r in out['yes']:
            x = r[tag]
            a['yes'] += int(x['v'] is True)
            a['unk'] += int(x['v'] is None)
            a['no'] += int(x['v'] is False)
            a['lp'] += x['lp']
            a['nodes'] += x['nodes']
            a['ynodes'] += x.get('yes_nodes') or 0
            a['trials'] += x.get('yes_trials') or 0
            a['id_nodes'] += x.get('id_nodes') or 0
            a['t'] += x['t']
            a['audit'] += int(x['audit'])
            a['sched'] += int(bool(x.get('sched')))
        a['t'] = round(a['t'], 3)
        print(tag, a)


if __name__ == '__main__':
    main()
