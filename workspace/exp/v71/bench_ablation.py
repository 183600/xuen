"""Ablation: ALC vs QNC(empty-precheck only) vs QNC(full quorum)."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC
from alc import ALC

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl', 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl', 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl', 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl'}

def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]

def run_all(inst, h):
    t0 = time.time(); a = ALC(inst, h); va, sa = a.decide(); ta = time.time()-t0
    t0 = time.time(); q1 = QNC(inst, h, use_quorum=False); v1, s1 = q1.decide(); t1 = time.time()-t0
    t0 = time.time(); q2 = QNC(inst, h); v2, s2 = q2.decide(); t2 = time.time()-t0
    return dict(alc=(va, sa, ta), empty=(v1, s1, t1), full=(v2, s2, t2),
                audit=q2.audit())

def main():
    out = {'corpus': {}, 'perturbed': {}}
    cases = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            cases.append((name, idx, inst, opt-1))
    res = []
    t0 = time.time()
    for name, idx, inst, h in cases:
        r = run_all(inst, h)
        r.update(name=name, idx=idx, h=h)
        res.append(r)
    out['corpus']['rows'] = [
        dict(name=r['name'], idx=r['idx'],
             alc_v=r['alc'][0], alc_lp=r['alc'][1]['lp_solves'],
             alc_nodes=r['alc'][1]['nodes'], alc_t=r['alc'][2],
             emp_v=r['empty'][0], emp_lp=r['empty'][1]['lp_solves'],
             emp_nodes=r['empty'][1]['nodes'], emp_t=r['empty'][2],
             qnc_v=r['full'][0], qnc_lp=r['full'][1]['lp_solves'],
             qnc_nodes=r['full'][1]['nodes'], qnc_t=r['full'][2],
             leaves=r['full'][1]['leaves'], force=r['full'][1]['force'],
             clauses=r['full'][1]['clauses'], audit=r['audit'],
             cert_t=r['full'][1]['cert_t'], cert_scale=(r['full'][1]['cert'] or {}).get('scale'))
        for r in res]
    for key in ['alc', 'emp', 'qnc']:
        rows = out['corpus']['rows']
        out['corpus'][key] = dict(
            no=sum(r[key+'_v'] is False for r in rows),
            lp=sum(r[key+'_lp'] for r in rows),
            nodes=sum(r[key+'_nodes'] for r in rows),
            t=sum(r[key+'_t'] for r in rows))
    out['corpus']['audit'] = sum(r['audit'] for r in res)
    out['corpus']['leaves'] = sum(r['leaves'] for r in out['corpus']['rows'])
    out['corpus']['wall'] = time.time()-t0
    print('CORPUS', {k: v for k, v in out['corpus'].items()
                     if k not in ('rows',)}, flush=True)

    pert = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    rows = []
    for (name, k, inst, opt, an, al) in pert:
        r = run_all(inst, opt-1)
        rows.append(dict(name=name, k=k, opt=opt,
                         alc_v=r['alc'][0], alc_lp=r['alc'][1]['lp_solves'],
                         alc_nodes=r['alc'][1]['nodes'],
                         emp_v=r['empty'][0], emp_lp=r['empty'][1]['lp_solves'],
                         emp_nodes=r['empty'][1]['nodes'],
                         qnc_v=r['full'][0], qnc_lp=r['full'][1]['lp_solves'],
                         qnc_nodes=r['full'][1]['nodes'], leaves=r['full'][1]['leaves'],
                         force=r['full'][1]['force'], audit=r['audit']))
    out['perturbed']['rows'] = rows
    for key in ['alc', 'emp', 'qnc']:
        out['perturbed'][key] = dict(
            no=sum(r[key+'_v'] is False for r in rows),
            lp=sum(r[key+'_lp'] for r in rows),
            nodes=sum(r[key+'_nodes'] for r in rows))
    out['perturbed']['audit'] = sum(r['audit'] for r in rows)
    out['perturbed']['branch'] = [r for r in rows if r['alc_nodes'] > 1]
    print('PERTURBED', {k: v for k, v in out['perturbed'].items() if k != 'rows' and k != 'branch'}, flush=True)
    for r in out['perturbed']['branch']:
        print(' pert', r, flush=True)
    json.dump(out, open('exp/v71/ablation.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
