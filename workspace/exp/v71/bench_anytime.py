"""LP-budget anytime curve for QNC on the 141 corpus + 60 perturbed cases."""
import sys, pickle, json
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
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

cases = []
for name, f in FILES.items():
    for idx, (inst, opt) in enumerate(load(f)):
        cases.append((inst, opt - 1))
for (name, k, inst, opt, an, al) in pickle.load(open('exp/v71/perturb60.pkl', 'rb')):
    cases.append((inst, opt - 1))

out = {}
for budget in range(0, 10):
    no = aud = 0
    leaves = forces = 0
    for inst, h in cases:
        q = QNC(inst, h)
        v, st = q.decide(budget=budget)
        if v is False:
            no += 1
            if q.audit():
                aud += 1
        leaves += st['leaves']
        forces += len(st['force'])
    out[budget] = dict(no=no, audit=aud, leaves=leaves, forces=forces)
    print(budget, out[budget], flush=True)
json.dump(out, open('exp/v71/anytime.json', 'w'), indent=1)
