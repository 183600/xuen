"""v7.2 UCP benchmark: 141 NO + 60 perturbed + 141 YES + anytime.

Configurations:
  qnc        v7.1 baseline
  ucp        pair-only, root, one job, gate (the proposed default)
  ucp_np     UCP with probing disabled (sanity: must equal QNC)
  ucp_f      UCP with force mode and two candidate jobs (ablation)
"""
import sys, pickle, json, time, collections
sys.setrecursionlimit(20000)
sys.path[:0] = ['exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC
from ucp import UCP

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


def run(cls, inst, h, **kw):
    q = cls(inst, h, **kw)
    t0 = time.time()
    v, st = q.decide()
    dt = time.time() - t0
    return dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                leaves=st['leaves'], probes=st.get('probes', 0),
                pairs=st.get('pairs', 0),
                pair_witness=st.get('pair_witness'),
                probes_jobs=st.get('probe_jobs', 0),
                why=st['why'], t=dt,
                audit=(q.audit_full() if hasattr(q, 'audit_full') else q.audit()))


def agg(rows, key):
    r = [x[key] for x in rows]
    return dict(no=sum(x['v'] is False for x in r),
                yes=sum(x['v'] is True for x in r),
                unknown=sum(x['v'] is None for x in r),
                lp=sum(x['lp'] for x in r),
                nodes=sum(x['nodes'] for x in r),
                leaves=sum(x['leaves'] for x in r),
                probes=sum(x['probes'] for x in r),
                pairs=sum(x['pairs'] for x in r),
                audit=sum(bool(x['audit']) for x in r),
                t=round(sum(x['t'] for x in r), 3))


def main():
    corpus = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            corpus.append((name, idx, inst, opt))

    print('NO corpus', len(corpus))
    rows = []
    for name, idx, inst, opt in corpus:
        h = opt - 1
        r = dict(name=name, idx=idx, h=h)
        r['qnc'] = run(QNC, inst, h)
        r['ucp'] = run(UCP, inst, h)
        r['ucp_np'] = run(UCP, inst, h, probe_on=False)
        r['ucp_f'] = run(UCP, inst, h, use_force=True, probe_jobs=2)
        rows.append(r)
    for k in ('qnc', 'ucp', 'ucp_np', 'ucp_f'):
        print(' ', k, agg(rows, k))

    pert = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    print('perturbed', len(pert))
    prows = []
    for (name, k, inst, opt, an, al) in pert:
        h = opt - 1
        r = dict(name=name, k=k, opt=opt)
        r['qnc'] = run(QNC, inst, h)
        r['ucp'] = run(UCP, inst, h)
        prows.append(r)
    for k in ('qnc', 'ucp'):
        print(' ', k, agg(prows, k))
    branch = [(r['name'], r['k'], r['qnc'], r['ucp'])
              for r in prows if r['qnc']['nodes'] > 1]
    print('  branch cases', len(branch))
    for b in branch:
        print('   ', b[0], b[1], 'qnc', b[2]['lp'], b[2]['nodes'],
              'ucp', b[3]['lp'], b[3]['nodes'], b[3]['pair_witness'])

    print('anytime (201)')
    anytime = []
    for budget in range(0, 11):
        no = 0
        aud = 0
        for name, idx, inst, opt in corpus:
            q = UCP(inst, opt - 1)
            v, st = q.decide(budget=budget)
            no += (v is False)
            aud += (v is not False) or q.audit_full()
        for (name, k, inst, opt, an, al) in pert:
            q = UCP(inst, opt - 1)
            v, st = q.decide(budget=budget)
            no += (v is False)
            aud += (v is not False) or q.audit_full()
        anywhere = dict(budget=budget, no=no, audit=aud)
        anytime.append(anywhere)
        print('  k', budget, anywhere)

    json.dump(dict(no_corpus=rows, perturb=prows, anytime=anytime),
              open('exp/v72/ucp_bench.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
