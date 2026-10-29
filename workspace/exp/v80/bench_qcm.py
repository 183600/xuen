"""QCM v8.0 benchmark: cover-LP probe on the 141 NO corpus + 60 perturbed."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v80', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qcm import QCM
from qnc import QNC

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl', 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl', 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl', 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl'}

def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]

def one(cls, inst, h, **kw):
    t0 = time.time()
    q = cls(inst, h, **kw)
    v, st = q.decide()
    return v, st, time.time() - t0, q

def run(inst, h):
    out = {}
    v, st, t, q = one(QNC, inst, h)
    out['qnc'] = dict(v=v, lp=st['lp_solves'], nodes=st['nodes'],
                      leaves=st['leaves'], cert=st['cert_calls'],
                      t=t, audit=q.audit())
    v, st, t, q = one(QCM, inst, h)
    out['qcm'] = dict(v=v, lp=st['lp_solves'], cover=st['cover_lp'],
                      skip=st['skipped'], nodes=st['nodes'],
                      leaves=st['leaves'], cert=st['cert_calls'],
                      cert_t=st['cert_t'], cover_t=st['cover_t'],
                      t=t, tau=st['tau'], why=st['why'],
                      audit=q.audit_full())
    v, st, t, q = one(QCM, inst, h, probe='multi')
    out['qcm_multi'] = dict(v=v, lp=st['lp_solves'], cover=st['cover_lp'],
                            nodes=st['nodes'], leaves=st['leaves'], t=t)
    v, st, t, q = one(QCM, inst, h, eps=0.25)
    out['qcm_eps25'] = dict(v=v, lp=st['lp_solves'], cover=st['cover_lp'],
                            nodes=st['nodes'], leaves=st['leaves'],
                            tau=st['tau'], why=st['why'], t=t)
    return out

def agg(rows, key):
    r = [x[key] for x in rows]
    return dict(no=sum(x['v'] is False for x in r),
                lp=sum(x['lp'] for x in r),
                cover=sum(x.get('cover', 0) for x in r),
                nodes=sum(x['nodes'] for x in r),
                leaves=sum(x['leaves'] for x in r),
                cert=sum(x.get('cert', 0) for x in r),
                t=round(sum(x['t'] for x in r), 3))

def main():
    cases = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            cases.append((name, idx, inst, opt - 1))
    rows = []
    for name, idx, inst, h in cases:
        r = run(inst, h)
        r.update(name=name, idx=idx, h=h)
        rows.append(r)
    print('CORPUS')
    for k in ('qnc', 'qcm', 'qcm_multi', 'qcm_eps25'):
        print(' ', k, agg(rows, k))
    print(' audit_full', sum(r['qcm']['audit'] for r in rows), '/', len(rows))
    print(' cover-closed', sum(r['qcm']['why'] == 'cover' for r in rows))
    pert = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    rows2 = []
    for (name, k, inst, opt, an, al) in pert:
        r = run(inst, opt - 1)
        r.update(name=name, k=k, opt=opt)
        rows2.append(r)
    print('PERTURBED')
    for k in ('qnc', 'qcm', 'qcm_multi', 'qcm_eps25'):
        print(' ', k, agg(rows2, k))
    print(' audit_full', sum(r['qcm']['audit'] for r in rows2), '/', len(rows2))
    print(' cover-closed', sum(r['qcm']['why'] == 'cover' for r in rows2))
    for r in rows + rows2:
        if r['qcm']['why'] == 'cover':
            print(' COVER', r['name'], r.get('idx', r.get('k')),
                  'tau', round(r['qcm']['tau'], 4), 'clauses', r['qcm']['leaves'],
                  'lp', r['qnc']['lp'], '->', r['qcm']['lp'] + r['qcm']['cover'],
                  'nodes', r['qnc']['nodes'], '->', r['qcm']['nodes'])
    json.dump(dict(corpus=rows, pert=rows2), open('exp/v80/qcm_bench.json', 'w'),
              indent=1)

if __name__ == '__main__':
    main()
