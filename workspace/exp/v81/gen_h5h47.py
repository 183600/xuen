"""Generate branch cases by mutating holdout idx 5/47 processing times."""
import sys,pickle,random,json,time
sys.setrecursionlimit(20000)
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
D=pickle.load(open('exp/v20/holdout_cases50.pkl','rb'))
bases=[('holdout50',5,D[5][0],D[5][1]),('holdout50',47,D[47][0],D[47][1])]
rng=random.Random(424242)
kept=[]; seen=set(); t0=time.time()
for trial in range(4000):
    name,idx,inst,opt=bases[rng.randrange(2)]
    p=list(inst['p'])
    for j in rng.sample(range(inst['n']),rng.choice([1,2,2,3])):
        d=rng.choice([-3,-2,-1,1,2,3])
        if p[j]+d>=1: p[j]+=d
    key=(name,idx,tuple(p))
    if key in seen: continue
    seen.add(key)
    inst2=dict(inst); inst2['p']=p
    q=QNC(inst2,opt-1)
    try: v,st=q.decide(nodecap=600,budget=4000)
    except (RecursionError,MemoryError): continue
    if v is False and st['nodes']>1 and q.audit():
        kept.append(dict(src=name,idx=idx,p=p,h=opt-1,q_lp=st['lp_solves'],
                         q_nodes=st['nodes'],n=inst['n'],m=inst['m'],inst=inst2))
    if (trial+1)%500==0:
        print('trial',trial+1,'kept',len(kept),'elapsed',round(time.time()-t0,1),flush=True)
pickle.dump(kept,open('exp/v81/h5h47_branch.pkl','wb'))
json.dump([{k:v for k,v in r.items() if k!='inst'} for r in kept],
          open('exp/v81/h5h47_branch_meta.json','w'),indent=1)
print('DONE',len(kept),'time',round(time.time()-t0,1))
print('nodes',sum(r['q_nodes'] for r in kept),'lp',sum(r['q_lp'] for r in kept))
