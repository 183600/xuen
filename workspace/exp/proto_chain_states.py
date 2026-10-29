import sys, random, json, pickle
sys.path.insert(0,'.')
import exp_da as E
from proto_chain import chain_thresh
from proto_tent_root import tent_thresh
rng=random.Random(5150); pool=pickle.load(open('pool30.pkl','rb'))
rows=[]
for k,(inst,opt,nd) in enumerate(pool):
    for trial in range(3):
        S,A,c=E.random_prefix(inst,rng,rng.choice([0.25,0.4,0.55]))
        L0=E.lower_L0(inst,S,A,c); U=E.guide(inst,S,A,c)
        if L0>=U: continue
        pack,_,_=tent_thresh(inst,S,A,c,U,L0)
        chain=chain_thresh(inst,S,A,c,U,L0)
        rows.append((k,trial,L0,U,pack,chain))
print('states',len(rows),'chain>pack',sum(1 for r in rows if r[5]>r[4]),
      'chain<pack',sum(1 for r in rows if r[5]<r[4]),
      'chain==pack',sum(1 for r in rows if r[5]==r[4]))
print('sum pack',sum(r[4] for r in rows),'chain',sum(r[5] for r in rows))
for r in rows:
    if r[5]>r[4]: print('gain',r)
