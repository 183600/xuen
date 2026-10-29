"""Adversarial audit: valid certificates must pass, mutations must fail."""
import sys, os, json, pickle, copy
sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v72t', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from tca import ProofQNC, check_proof, verify_schedule, greedy_schedule, TCA

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
inst, opt = pickle.load(open(os.path.join(ROOT, 'exp/v20/holdout_cases50.pkl'),
                             'rb'))[47]

q = ProofQNC(inst, opt - 1)
v, st = q.decide()
bundle = dict(nodes=q.pnodes, forces=q.forces, root=0)
base_proof = check_proof(inst, opt - 1, bundle)

v2, st2 = TCA(inst, opt, primal_tries=100).decide()
base_sched = verify_schedule(inst, opt, st2['schedule'])

rows = []
def rec(name, got, want):
    rows.append(dict(name=name, got=got, want=want, pass_=(got == want)))

rec('base_no_proof', base_proof[0], 'NO')
rec('base_yes_schedule', base_sched[0], True)

# 1. tamper a NO leaf's alpha
b = copy.deepcopy(bundle)
for nd in b['nodes']:
    if nd['kind'] == 'no' and nd['cert']:
        nd['cert']['alpha'][0] += 1
        break
rec('no_leaf_alpha', check_proof(inst, opt - 1, b)[0] != 'NO', True)

# 2. tamper a NO leaf's beta
b = copy.deepcopy(bundle)
for nd in b['nodes']:
    if nd['kind'] == 'no' and nd['cert']:
        nd['cert']['beta'][0] = (None, nd['cert']['beta'][0][1],
                                 nd['cert']['beta'][0][2] + 1)
        break
rec('no_leaf_beta', check_proof(inst, opt - 1, b)[0] != 'NO', True)

# 3. tamper a global force event (times)
b = copy.deepcopy(bundle)
if b['forces']:
    i, E, c = b['forces'][0]
    b['forces'][0] = (i, frozenset((ii, t + 1) for (ii, t) in E), c)
rec('force_times', check_proof(inst, opt - 1, b)[0] != 'NO', True)

# 4. remove a child of the root split
b = copy.deepcopy(bundle)
for nd in b['nodes']:
    if nd['kind'] == 'split':
        nd['children'] = nd['children'][:1]
        break
rec('missing_child', check_proof(inst, opt - 1, b)[0] != 'NO', True)

# 5. shift one job in a valid YES schedule
bad = [(i, k, t + 1) for (i, k, t) in st2['schedule']]
rec('yes_shift', verify_schedule(inst, opt, bad)[0], False)

# 6. drop one job from a valid YES schedule
bad = list(st2['schedule'])[:-1]
rec('yes_drop', verify_schedule(inst, opt, bad)[0], False)

rec('no_proof_at_opt', check_proof(inst, opt, bundle)[0] != 'NO', True)
rec('yes_schedule_at_opt_minus_1',
    verify_schedule(inst, opt - 1, st2['schedule'])[0], False)

print(json.dumps(rows, indent=1))
json.dump(rows, open(os.path.join(ROOT, 'exp/v72t/cert_tests.json'), 'w'),
          indent=1)
assert all(r['pass_'] for r in rows), rows
