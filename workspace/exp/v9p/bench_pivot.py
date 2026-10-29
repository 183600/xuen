"""v9.1 PIVOT benchmark: NO 252, YES 141, plus ablations."""
import sys
import json
import time

sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v9p', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from rdf import RDF, check_schedule
from pivot import PIVOT
from bench_rdf import base_corpus, no_corpus


def run(cls, inst, h, budget, nodecap, kw=None):
    t0 = time.time()
    q = cls(inst, h, **(kw or {}))
    v, st = q.decide(budget=budget, nodecap=nodecap)
    dt = time.time() - t0
    au = q.audit_pivot() if hasattr(q, 'audit_pivot') else q.audit_rdf()
    pc = q.proof_complete()
    return q, v, st, dt, au, pc


def agg_no(rows, tag):
    a = dict(no=0, unk=0, yes=0, lp=0, nodes=0, probes=0, audit=0,
             proof=0, prep=0, t=0.0)
    for r in rows:
        x = r[tag]
        a['no'] += int(x['v'] is False)
        a['unk'] += int(x['v'] is None)
        a['yes'] += int(x['v'] is True)
        a['lp'] += x['lp']
        a['nodes'] += x['nodes']
        a['probes'] += x.get('probes') or 0
        a['audit'] += int(bool(x['audit']))
        a['proof'] += int(bool(x['proof']))
        a['prep'] += int(bool(x.get('prep')))
        a['t'] += x['t']
    a['t'] = round(a['t'], 3)
    return a


def agg_yes(rows, tag):
    a = dict(yes=0, unk=0, no=0, lp=0, nodes=0, trials=0, ynodes=0,
             audit=0, proof=0, sched=0, greedy=0, vertex_hits=0, t=0.0)
    for r in rows:
        x = r[tag]
        a['yes'] += int(x['v'] is True)
        a['unk'] += int(x['v'] is None)
        a['no'] += int(x['v'] is False)
        a['lp'] += x['lp']
        a['nodes'] += x['nodes']
        a['trials'] += x.get('trials') or 0
        a['ynodes'] += x.get('ynodes') or 0
        a['audit'] += int(bool(x['audit']))
        a['proof'] += int(bool(x['proof']))
        a['sched'] += int(bool(x.get('sched')))
        a['greedy'] += int(bool(x.get('greedy')))
        a['vertex_hits'] += int(x.get('vertex_hits') or 0)
        a['t'] += x['t']
    a['t'] = round(a['t'], 3)
    return a


def main():
    no = no_corpus()
    yes = base_corpus()
    out = {'no': [], 'yes': []}

    print('NO corpus', len(no), flush=True)
    no_variants = [
        ('brc', RDF, dict(yes_scan=False)),
        ('prep', PIVOT, dict(yes_scan=False, prep_on=True,
                             greedy_on=False, vertex_on=False)),
        ('pivot', PIVOT, dict(yes_scan=False, prep_on=True,
                              greedy_on=True, vertex_on=True)),
    ]
    for ci, (name, idx, inst, h, src) in enumerate(no):
        row = dict(name=name, idx=idx, src=src)
        for tag, cls, kw in no_variants:
            q, v, st, dt, au, pc = run(cls, inst, h, 100, 5000, kw)
            row[tag] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                            probes=st.get('probes_total'),
                            audit=bool(au), proof=bool(pc),
                            prep=st.get('prep_kind'), why=st.get('why'),
                            t=round(dt, 4))
        out['no'].append(row)
        if ci % 50 == 0:
            print('NO', ci, flush=True)

    print('YES corpus', len(yes), flush=True)
    yes_variants = [
        ('brc', RDF, dict(yes_scan=True)),
        ('greedy', PIVOT, dict(yes_scan=True, vertex_on=False,
                               vertex_trials=0)),
        ('vertex', PIVOT, dict(yes_scan=True, greedy_on=False,
                               vertex_trials=12)),
        ('pivot4', PIVOT, dict(yes_scan=True, vertex_trials=4)),
        ('pivot8', PIVOT, dict(yes_scan=True, vertex_trials=8)),
        ('pivot12', PIVOT, dict(yes_scan=True, vertex_trials=12)),
        ('pivot16', PIVOT, dict(yes_scan=True, vertex_trials=16)),
    ]
    for ci, (name, idx, inst, opt) in enumerate(yes):
        row = dict(name=name, idx=idx, n=inst['n'], m=inst['m'])
        for tag, cls, kw in yes_variants:
            q, v, st, dt, au, pc = run(cls, inst, opt, 100, 5000, kw)
            row[tag] = dict(
                v=v, lp=st['lp_solves'], nodes=st['nodes'],
                trials=st.get('yes_trials'), ynodes=st.get('yes_nodes'),
                why=st.get('why'), greedy=st.get('greedy_rule'),
                vertex_used=st.get('vertex_used'),
                vertex_hits=st.get('vertex_hits'),
                prep=st.get('prep_kind'),
                audit=bool(au), proof=bool(pc),
                sched=(q.schedule is not None and
                       check_schedule(inst, opt, q.schedule, q.machine)),
                t=round(dt, 4))
        out['yes'].append(row)
        if ci % 25 == 0:
            print('YES', ci, flush=True)

    json.dump(out, open('exp/v9p/bench_pivot.json', 'w'))
    print('\n== NO', len(out['no']))
    for tag, _, _ in no_variants:
        print(tag, agg_no(out['no'], tag))
    print('\n== YES', len(out['yes']))
    for tag, _, _ in yes_variants:
        print(tag, agg_yes(out['yes'], tag))


if __name__ == '__main__':
    main()
