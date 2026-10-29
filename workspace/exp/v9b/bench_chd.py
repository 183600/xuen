"""v9.0 CHD benchmark: NO 252 (QSP vs CHD pure NO) + YES 141 (BRC vs CHD)."""
import sys
import pickle
import json
import time

sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from qsp import QSP
from rdf import RDF, check_schedule
from chd import CHD

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
    for (name, k, inst, opt, an, al) in pickle.load(
            open('exp/v71/perturb60.pkl', 'rb')):
        out.append((name, k, inst, opt - 1, 'pert'))
    for r in pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb')):
        out.append(('stress', r['idx'], r['inst'], r['h'], 'stress'))
    return out


def run(cls, inst, h, budget, nodecap, kw=None):
    t0 = time.time()
    q = cls(inst, h, **(kw or {}))
    v, st = q.decide(budget=budget, nodecap=nodecap)
    dt = time.time() - t0
    if hasattr(q, 'audit_chd'):
        au = q.audit_chd()
    elif hasattr(q, 'audit_rdf'):
        au = q.audit_rdf()
    else:
        au = q.audit_qsp()
    pc = q.proof_complete() if hasattr(q, 'proof_complete') else None
    return q, v, st, dt, au, pc


def main():
    no = no_corpus()
    yes = base_corpus()
    out = {'no': [], 'yes': []}

    print('NO corpus', len(no), flush=True)
    for ci, (name, idx, inst, h, src) in enumerate(no):
        row = dict(name=name, idx=idx, src=src)
        for tag, cls, kw in [
                ('qsp', QSP, {}),
                ('chd', CHD, dict(yes_scan=False))]:
            q, v, st, dt, au, pc = run(cls, inst, h, 100, 5000, kw)
            row[tag] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                            t=round(dt, 4), audit=bool(au),
                            pc=(None if pc is None else bool(pc)),
                            probes=st.get('probes_total'))
        out['no'].append(row)
        if ci % 25 == 0:
            print('NO', ci, flush=True)

    print('YES corpus', len(yes), flush=True)
    for ci, (name, idx, inst, opt) in enumerate(yes):
        row = dict(name=name, idx=idx)
        q, v, st, dt, au, pc = run(RDF, inst, opt, 100, 5000,
                                   dict(yes_scan=True))
        row['brc'] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                          t=round(dt, 4), audit=bool(au), pc=bool(pc),
                          why=st.get('why'), yes_calls=st.get('yes_calls'),
                          yes_trials=st.get('yes_trials'),
                          yes_nodes=st.get('yes_nodes'),
                          sched=(q.schedule is not None and
                                 check_schedule(inst, opt, q.schedule,
                                                q.machine)))
        q, v, st, dt, au, pc = run(CHD, inst, opt, 100, 5000,
                                   dict(yes_scan=True))
        row['chd'] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                          t=round(dt, 4), audit=bool(au), pc=bool(pc),
                          why=st.get('why'), phase=st.get('phase'),
                          lds_calls=st.get('lds_calls'),
                          lds_nodes=st.get('lds_nodes'),
                          lds_rank=st.get('lds_rank'),
                          lds_disc=st.get('lds_disc'),
                          hull_lp=st.get('hull_lp'),
                          hull_time=st.get('hull_time'),
                          used_random=st.get('used_random'),
                          sched=(q.schedule is not None and
                                 check_schedule(inst, opt, q.schedule,
                                                q.machine)))
        out['yes'].append(row)
        if ci % 25 == 0:
            print('YES', ci, flush=True)

    json.dump(out, open('exp/v9b/bench_chd.json', 'w'))

    print('\n== NO', len(out['no']))
    for tag in ['qsp', 'chd']:
        agg = dict(no=0, lp=0, nodes=0, probes=0, audit=0, pc=0, t=0.0)
        for r in out['no']:
            a = r[tag]
            agg['no'] += int(a['v'] is False)
            agg['lp'] += a['lp']
            agg['nodes'] += a['nodes']
            agg['probes'] += (a['probes'] or 0)
            agg['audit'] += int(a['audit'])
            agg['pc'] += int(bool(a['pc']))
            agg['t'] += a['t']
        print(tag, agg)

    print('\n== YES', len(out['yes']))
    for tag in ['brc', 'chd']:
        agg = dict(yes=0, unk=0, no=0, lp=0, nodes=0, audit=0, pc=0,
                   t=0.0, calls=0, trials=0, ynodes=0, sched=0, hull=0,
                   htime=0.0, rand=0)
        for r in out['yes']:
            a = r[tag]
            agg['yes'] += int(a['v'] is True)
            agg['unk'] += int(a['v'] is None)
            agg['no'] += int(a['v'] is False)
            agg['lp'] += a['lp']
            agg['nodes'] += a['nodes']
            agg['audit'] += int(a['audit'])
            agg['pc'] += int(bool(a['pc']))
            agg['t'] += a['t']
            agg['sched'] += int(bool(a['sched']))
            if tag == 'brc':
                agg['calls'] += a.get('yes_calls') or 0
                agg['trials'] += a.get('yes_trials') or 0
                agg['ynodes'] += a.get('yes_nodes') or 0
            else:
                agg['ynodes'] += a.get('lds_nodes') or 0
                agg['hull'] += a.get('hull_lp') or 0
                agg['htime'] += a.get('hull_time') or 0
                agg['rand'] += int(bool(a.get('used_random')))
        print(tag, agg)
        if tag == 'chd':
            from collections import Counter
            print(' phases', Counter(r['chd']['phase'] for r in out['yes']))


if __name__ == '__main__':
    main()
