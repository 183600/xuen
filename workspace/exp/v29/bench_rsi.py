"""Count RSI-pruned nodes and memo entries on held-out 50."""
import sys, json, pickle
sys.path[:0] = ['exp/v29', 'exp/v13']
import po, os_pack

d = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
N = M = R = 0
for inst, opt in d:
    h = opt - 1
    est, q = po.heads_tails(inst, 0, [0] * inst['n'])
    s = {}
    os_pack.sgs_solve(inst, h, rem=inst['full'], A=(0,) * inst['m'],
                      est=est, q=q, nodecap=300000, stats=s)
    N += s['nodes']; M += s['memo']; R += s['rsi_hits']
out = dict(nodes=N, memo=M, rsi_hits=R)
print(json.dumps(out, indent=1))
json.dump(out, open('exp/v29/res_rsi.json', 'w'), indent=1)
