import sys,time,collections,json
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from chip import base_corpus,pert_corpus,stress_corpus
from satproto import solve
from rdf import check_schedule
import itertools, time
rows=[]
for tag,fn in [('base',base_corpus),('pert',pert_corpus),('stress',stress_corpus)]:
    for row in fn():
        if len(row)==4: name,idx,inst,known=row
        else: idx,known,inst=row; name=tag
        rows.append((tag,name,idx,inst,known))
print('n',len(rows),flush=True)
res=[]
t0=time.time()
for q,(tag,name,idx,inst,known) in enumerate(rows):
    rr={}
    for h in (known-1,known):
        r=solve(inst,h)
        rr[h]=r
    res.append((tag,name,idx,known,rr))
    if q%25==0: print(q,round(time.time()-t0,2),flush=True)
print('total wall',round(time.time()-t0,2))
# summaries
for hrel in (0,1):
    us=sum(1 for *_,rr in res if rr[ (lambda k: k[0])(res) ])
