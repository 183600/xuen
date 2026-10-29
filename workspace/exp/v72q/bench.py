import sys, pickle, json, time, collections
sys.path[:0] = ['exp/v72q', 'exp/v84', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC
from qcp import QCP

FILES = {'holdout50': 'exp/v20/holdout_cases50.pkl',
         'synth45': 'exp/v28/synth2_45.pkl',
         'large_a': 'exp/v14/large_a.pkl',
         'large_b': 'exp/v14/large_b.pkl',
         'large_het': 'exp/v14/large_het.pkl',
         'hard3': 'exp/v13/hard3.pkl',
         'deep8': 'exp/v18/deep.pkl'}

def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']) for x in d]

def one(inst, h, cls=QCP, **kw):
    t0 = time.time(); q = cls(inst, h, **kw); v, s = q.decide(); dt = time.time() - t0
    return q, v, s, dt

def summarize(rows, tag):
    agg = {}
    for name in ('qnc', 'qcp'):
        sub = [r for r in rows if r.get(name)]
        agg[name] = dict(
            n=len(sub),
            no=sum(r[name]['v'] is False for r in sub),
            lp=sum(r[name]['s']['lp_solves'] for r in sub),
            nodes=sum(r[name]['s']['nodes'] for r in sub),
            time=round(sum(r[name]['t'] for r in sub), 3),
            audit=sum(bool(r[name]['audit']) for r in sub))
    print(tag, json.dumps(agg, sort_keys=True))
    return agg

out = {}
for tag, cases in [('corpus', [(n, i, inst, opt - 1) for n, f in FILES.items()
                               for i, (inst, opt) in enumerate(load(f))]),
                   ('pert', [(n, k, inst, opt - 1) for (n, k, inst, opt, an, al)
                             in pickle.load(open('exp/v71/perturb60.pkl', 'rb'))])]:
    rows = []
    for name, idx, inst, h in cases:
        a, va, sa, ta = one(inst, h, QNC)
        b, vb, sb, tb = one(inst, h, QCP)
        cids, exact = b.minimal_core()
        row = dict(name=name, idx=idx, h=h,
                   qnc=dict(v=va, s=sa, t=ta, audit=a.audit()),
                   qcp=dict(v=vb, s=sb, t=tb, audit=b.audit(),
                            core_raw=len(b.proof_core()), core_min=len(cids),
                            core_exact=exact, core_audit=b.audit_minimal_core(),
                            leaves=len(b.leaves), conflict=(b.conflict[0] if b.conflict else None),
                            why=sb['why'], why_global=sb['why_global']))
        rows.append(row)
    out[tag] = dict(rows=rows, agg=summarize(rows, tag))
    print(tag, 'core_raw', sum(r['qcp']['core_raw'] for r in rows),
          'core_min', sum(r['qcp']['core_min'] for r in rows),
          'leaves', sum(r['qcp']['leaves'] for r in rows),
          'res_steps', sum(r['qcp']['s'].get('res_steps', 0) for r in rows),
          'units', sum(r['qcp']['s'].get('res_units', 0) for r in rows),
          'empty', sum(r['qcp']['s'].get('res_empty', 0) for r in rows),
          'audit_core', sum(bool(r['qcp']['core_audit']) for r in rows),
          'conflicts', dict(collections.Counter(r['qcp']['conflict'] for r in rows)))

D = pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))
rows = []
for n, r in enumerate(D):
    inst, h = r['inst'], r['h']
    a, va, sa, ta = one(inst, h, QNC)
    b, vb, sb, tb = one(inst, h, QCP)
    cids, exact = b.minimal_core()
    rows.append(dict(n=n, src=r['src'], idx=r['idx'],
                     qnc=dict(v=va, s=sa, t=ta, audit=a.audit()),
                     qcp=dict(v=vb, s=sb, t=tb, audit=b.audit(),
                              core_raw=len(b.proof_core()), core_min=len(cids),
                              core_exact=exact, core_audit=b.audit_minimal_core(),
                              leaves=len(b.leaves), conflict=(b.conflict[0] if b.conflict else None),
                              why=sb['why'], why_global=sb['why_global'])))
out['branch51'] = dict(rows=rows, agg=summarize(rows, 'branch51'))
print('branch51 core_raw', sum(r['qcp']['core_raw'] for r in rows),
      'core_min', sum(r['qcp']['core_min'] for r in rows),
      'leaves', sum(r['qcp']['leaves'] for r in rows),
      'res_steps', sum(r['qcp']['s'].get('res_steps', 0) for r in rows),
      'units', sum(r['qcp']['s'].get('res_units', 0) for r in rows),
      'empty', sum(r['qcp']['s'].get('res_empty', 0) for r in rows),
      'audit_core', sum(bool(r['qcp']['core_audit']) for r in rows),
      'conflicts', dict(collections.Counter(r['qcp']['conflict'] for r in rows)))

front = []
for budget in [0, 1, 2, 3, 4, 5, 8, 10, 20, 50, 100, 500, 4000]:
    lps = nds = steps = units = empty = 0; t0 = time.time(); worst = 0
    for r in D:
        q, v, s, dt = one(r['inst'], r['h'], QCP, max_steps=budget)
        lps += s['lp_solves']; nds += s['nodes']; steps += s.get('res_steps', 0)
        units += s.get('res_units', 0); empty += s.get('res_empty', 0)
        worst = max(worst, s.get('res_steps', 0))
    front.append(dict(budget=budget, lp=lps, nodes=nds, steps=steps,
                      units=units, empty=empty, worst=worst,
                      time=round(time.time() - t0, 3)))
    print('front', front[-1], flush=True)
out['front51'] = front
json.dump(out, open('exp/v72q/bench.json', 'w'), indent=1)
