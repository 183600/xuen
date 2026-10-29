"""v8.1 SCL benchmark: 141 YES + 60 perturb YES + hard cases."""
import sys, pickle, json, time
sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v8b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']
from rdf import RDF, check_schedule
from scl import SCL

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
    return [(name, idx, inst, opt)
            for name, f in FILES.items()
            for idx, (inst, opt) in enumerate(load(f))]


def pert_corpus():
    d = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    return [(name, k, inst, opt) for (name, k, inst, opt, _, _) in d]


def run(cls, inst, h, kw=None, budget=100, nodecap=5000):
    t0 = time.time()
    q = cls(inst, h, **(kw or {}))
    v, st = q.decide(budget=budget, nodecap=nodecap)
    dt = time.time() - t0
    au = q.audit_rdf()
    pc = q.proof_complete()
    sched = (q.schedule is not None and
             check_schedule(inst, h, q.schedule, q.machine))
    return q, v, st, dt, au, pc, sched


def main():
    out = {'base': [], 'pert': []}
    for tag, corpus in [('base', base_corpus()), ('pert', pert_corpus())]:
        print(tag, len(corpus), flush=True)
        for ci, (name, idx, inst, opt) in enumerate(corpus):
            row = dict(name=name, idx=idx, opt=opt)
            for mtag, cls, kw in [
                    ('rdf', RDF, dict(yes_scan=True)),
                    ('scl', SCL, dict(yes_scan=True))]:
                q, v, st, dt, au, pc, sched = run(cls, inst, opt, kw)
                row[mtag] = dict(v=v, lp=st['lp_solves'],
                                 nodes=st['nodes'], t=round(dt, 4),
                                 audit=bool(au), pc=bool(pc),
                                 why=st.get('why'),
                                 calls=st.get('yes_calls'),
                                 trials=st.get('yes_trials'),
                                 ynodes=st.get('yes_nodes'),
                                 evals=st.get('scl_evals'),
                                 rounds=st.get('scl_rounds'),
                                 best=st.get('scl_best_loss'),
                                 dfs=st.get('scl_dfs_calls'),
                                 sched=bool(sched))
            out[tag].append(row)
            if ci % 25 == 0:
                print(tag, ci, flush=True)
    json.dump(out, open('exp/v8b/bench_scl.json', 'w'))
    for tag in ['base', 'pert']:
        rows = out[tag]
        print('\n==', tag, len(rows))
        for mtag in ['rdf', 'scl']:
            agg = dict(yes=0, unk=0, no=0, lp=0, nodes=0, audit=0,
                       pc=0, t=0.0, calls=0, trials=0, ynodes=0, sched=0,
                       evals=0)
            for r in rows:
                a = r[mtag]
                agg['yes'] += int(a['v'] is True)
                agg['unk'] += int(a['v'] is None)
                agg['no'] += int(a['v'] is False)
                agg['lp'] += a['lp']
                agg['nodes'] += a['nodes']
                agg['audit'] += int(bool(a['audit']))
                agg['pc'] += int(bool(a['pc']))
                agg['t'] += a['t']
                agg['calls'] += a.get('calls') or 0
                agg['trials'] += a.get('trials') or 0
                agg['ynodes'] += a.get('ynodes') or 0
                agg['sched'] += int(bool(a.get('sched')))
                agg['evals'] += a.get('evals') or 0
            print(mtag, agg)


if __name__ == '__main__':
    main()
