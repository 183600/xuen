"""Generate a large sound branch-stress corpus by mutating p.

Ground truth: keep only instances where QNC returns NO (its Farkas leaf
certificates are replayed by audit) and the search needs >1 node.  YES
instances are discarded, so no label depends on an unchecked integral LP.
"""
import sys, pickle, random, json, time
sys.setrecursionlimit(20000)
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC

FILES={'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
bases=[]
for name,f in FILES.items():
    for idx,(inst,opt) in enumerate(load(f)):
        bases.append((name,idx,inst,opt))
rng=random.Random(20261023)
kept=[]; seen=set(); trials=0; t0=time.time()
while len(kept)<240 and trials<12000:
    trials+=1
    name,idx,inst,opt=bases[rng.randrange(len(bases))]
    nj=rng.choice([1,1,2]); jobs=rng.sample(range(inst['n']),nj)
    p=list(inst['p']); ok=True
    for j in jobs:
        d=rng.choice([-3,-2,-1,1,2,3])
        if p[j]+d<1: ok=False; break
        p[j]+=d
    if not ok: continue
    key=(name,idx,tuple(p))
    if key in seen: continue
    seen.add(key)
    inst2=dict(inst); inst2['p']=p
    # keep h fixed at the original opt-1; QNC decides NO/YES soundly
    q=QNC(inst2,opt-1)
    try:
        v,st=q.decide(nodecap=800,budget=5000)
    except (RecursionError,MemoryError):
        continue
    if v is False and st['nodes']>1 and q.audit():
        kept.append(dict(src=name,idx=idx,jobs=jobs,p=p,h=opt-1,
                         q_lp=st['lp_solves'],q_nodes=st['nodes'],
                         n=inst['n'],m=inst['m'],inst=inst2))
    if trials%500==0:
        print('trials',trials,'kept',len(kept),'elapsed',round(time.time()-t0,1),flush=True)
pickle.dump(kept,open('exp/v81/branch240.pkl','wb'))
json.dump([{k:v for k,v in r.items() if k!='inst'} for r in kept],
          open('exp/v81/branch240_meta.json','w'),indent=1)
print('DONE trials',trials,'kept',len(kept),'time',round(time.time()-t0,1))
from collections import Counter
print(Counter((r['src'],r['idx']) for r in kept).most_common(20))
print('nodes',sum(r['q_nodes'] for r in kept),'lp',sum(r['q_lp'] for r in kept))
