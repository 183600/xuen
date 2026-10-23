"""Proof-object statistics: tau sequence, mixture certificate, synergy gap."""
import sys, pickle, json
sys.path[:0] = ['exp/v80', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qcm import QCM, mix_certificate, replay_mixture, cover_lp
FILES = {'holdout50': 'exp/v20/holdout_cases50.pkl',
 'synth45': 'exp/v28/synth2_45.pkl', 'large_a': 'exp/v14/large_a.pkl',
 'large_b': 'exp/v14/large_b.pkl', 'large_het': 'exp/v14/large_het.pkl',
 'hard3': 'exp/v13/hard3.pkl', 'deep8': 'exp/v18/deep.pkl'}
def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]
def one(name, idx, inst, h):
    q = QCM(inst, h)
    v, st = q.decide()
    rec = dict(name=name, idx=idx, verdict=v, why=st['why'],
               lp=st['lp_solves'], cover=st['cover_lp'], nodes=st['nodes'],
               leaves=st['leaves'], probes=st['probes'],
               clause_sizes=[len(E) for E in q.clauses],
               skills=[int(E and len({i for i, t in E}) == 1)
                       for E in q.clauses])
    if q.mix is not None:
        clauses, tau, res = q.mix
        mc = mix_certificate(q.lp, clauses, res)
        caps = []
        for E in clauses:
            t, _ = cover_lp(q.lp, [E])
            caps.append(t)
        rec.update(tau=tau, caps=caps,
                   synergy=(min(caps) - tau) if caps and None not in caps else None,
                   pi=mc['pi'][:len(clauses)] if mc else None,
                   S=mc['S'] if mc else None, obj=mc['obj'] if mc else None,
                   replay=(mc is not None and
                           replay_mixture(q.lp, clauses, mc)))
    return rec
rows = []
for name, f in FILES.items():
    for idx, (inst, opt) in enumerate(load(f)):
        rows.append(one(name, idx, inst, opt - 1))
for (name, k, inst, opt, an, al) in pickle.load(open('exp/v71/perturb60.pkl', 'rb')):
    r = one(name, 'p%d' % k, inst, opt - 1)
    rows.append(r)
json.dump(rows, open('exp/v80/proof_stats.json', 'w'), indent=1)
cov = [r for r in rows if r.get('tau') is not None]
print('cover-closed', len(cov))
for r in cov:
    print(f"{r['name']}:{r['idx']} tau={r['tau']:.3f} K={len(r['clause_sizes'])} "
          f"caps={[round(x,3) for x in r['caps']]} "
          f"synergy={r['synergy']} pi={r['pi']} S={r['S']} obj={r['obj']} "
          f"replay={r['replay']} nodes={r['nodes']} leaves={r['leaves']}")
print('audit mix', sum(bool(r.get('replay')) for r in cov), '/', len(cov))
