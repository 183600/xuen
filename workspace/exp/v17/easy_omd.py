"""v1.6 OMD: overhead on 60 easy instances (h = OPT + 5)."""
import sys, random, time, json
sys.path.insert(0, 'exp/v13'); sys.path.insert(0, 'exp/v14')
sys.path.insert(0, 'exp/v15'); sys.path.insert(0, 'exp/v16'); sys.path.insert(0, 'exp/v17')
import po, pace_omd
from diff_i import gen

CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
           packset_on=True, packset_depth=0, sop_on=True)
rng = random.Random(4242)
rows = []
while len(rows) < 60:
    n = rng.randint(10, 14); m = 3
    inst = gen(rng, n, m, ep=rng.choice([0.15, 0.25]), elig_p=1.0)
    est, q = po.heads_tails(inst, 0, [0] * n)
    lo = max(max(est[i] + inst['p'][i] + q[i] for i in range(n)),
             (sum(inst['p']) + m - 1) // m, max(inst['p']))
    opt = None
    for h in range(lo, lo + 14):
        (ok, _), st = po.decide(inst, h, mode='sub', nodecap=200000)
        if st.get('timeout'):
            break
        if ok:
            opt = h; break
    if opt is None:
        continue
    h = opt + 5
    t = time.time(); (a, _), sa = pace_omd.decide(inst, h, omd=False, **CFG); ta = time.time() - t
    t = time.time(); (b, _), sb = pace_omd.decide(inst, h, omd=True, **CFG); tb = time.time() - t
    assert a == b == True
    rows.append(dict(n=n, base_nodes=sa['nodes'], omd_nodes=sb['nodes'],
                     base_time=ta, omd_time=tb))
out = dict(count=len(rows),
           base_nodes=sum(r['base_nodes'] for r in rows),
           omd_nodes=sum(r['omd_nodes'] for r in rows),
           base_time=round(sum(r['base_time'] for r in rows), 4),
           omd_time=round(sum(r['omd_time'] for r in rows), 4))
out['time_ratio'] = round(out['omd_time'] / out['base_time'], 3)
json.dump(dict(rows=rows, summary=out), open('exp/v17/easy_omd.json', 'w'), indent=1)
print(out)
