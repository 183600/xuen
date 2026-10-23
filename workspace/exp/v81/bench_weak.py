import sys,pickle,json,time
sys.path[:0]=['exp/v81','exp/v71','exp/v61','exp/v60','exp/v13']
from weak import WeakQNC
from qcc2 import QCC2
from aqc import AQC
from qnc import QNC
FILES={'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
cases=[]
for name,f in FILES.items():
    for idx,(inst,opt) in enumerate(load(f)): cases.append((name,idx,inst,opt-1))
rows=[]; t0=time.time()
for ci,(name,idx,inst,h) in enumerate(cases):
    w=WeakQNC(inst,h); vw,sw=w.decide(nodecap=3000,budget=20000)
    c=QCC2(inst,h,cut_kind='uniform'); vc,sc=c.decide(nodecap=3000,budget=20000)
    a=AQC(inst,h,cut_kind='uniform'); va,sa=a.decide(nodecap=3000,budget=20000)
    rows.append(dict(name=name,idx=idx,w=(vw,sw['lp_solves'],sw['nodes'],sw['why']),
                     c=(vc,sc['lp_solves'],sc['nodes'],sc['why']),
                     a=(va,sa['lp_solves'],sa['nodes'],sa['why']),
                     probes=sa.get('probes',0),pairs=sa.get('pairs',0),
                     covers=sc.get('covers',0),audit=a.audit()))
    if (ci+1)%20==0: print('done',ci+1,'elapsed',round(time.time()-t0,1),flush=True)
json.dump(rows,open('exp/v81/weak_bench.json','w'),indent=1)
for key in ['w','c','a']:
    no=sum(r[key][0] is False for r in rows); lp=sum(r[key][1] for r in rows); nd=sum(r[key][2] for r in rows)
    br=sum(r[key][2]>1 for r in rows)
    print(key,'NO',no,'LP',lp,'nodes',nd,'branch',br)
print('weak branch cases',sum(1 for r in rows if r['w'][2]>1))
for r in rows:
    if r['w'][2]>1:
        print(r['name'],r['idx'],'w',r['w'][1:],'c',r['c'][1:],'a',r['a'][1:],'cov',r['covers'],'probe',r['probes'],'pair',r['pairs'])
