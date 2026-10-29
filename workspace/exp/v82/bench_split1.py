import sys,pickle,json,time
sys.path[:0]=['exp/v82','exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np
from qnc import QNC
from qls import farkas_obj
from cert import verify

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl', 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl', 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl', 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl'}
def load(f):
 d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]

def one_level(inst,h):
 q=QNC(inst,h); q.budget=10000
 base=[(0,1)]*q.lp.base.N
 res,z=q._solve(base,60,100); lp=1
 if res.status==2: return dict(kind='root-no',lp=lp)
 if res.status!=0 or z is None: return dict(kind='other',lp=lp)
 frac=[c for c in range(q.lp.base.N) if 1e-7<z[c]<1-1e-7]
 if not frac: return dict(kind='yes',lp=lp)
 supp=[c for c in range(q.lp.base.N) if z[c]>1e-7]
 b2=list(base)
 for c in supp: b2[c]=(0,0)
 res2,z2=q._solve(b2,60,100); lp+=1
 if res2.status!=2: return dict(kind='mine-feas',lp=lp)
 F={q.lp.cols[c] for c in supp}
 cert,s=farkas_obj(q.lp,F)
 if cert is None: return dict(kind='mine-certfail',lp=lp)
 E=frozenset(key for cc,key in enumerate(q.lp.cols) if key in F and s[cc]<0)
 jobs={i for i,t in E}
 ok=verify(inst,h,cert,forbid=E,elig_aware=q.elig)
 if not E: return dict(kind='empty',lp=lp,E=E,ok=ok)
 if len(jobs)!=1: return dict(kind='multi',lp=lp,E=E,jobs=len(jobs),ok=ok)
 i=next(iter(jobs)); times=sorted(t for j,t in E)
 statuses=[]
 for t in times:
  b=list(base)
  for c,key in enumerate(q.lp.cols):
   if key[0]==i and key[-1]!=t: b[c]=(0,0)
  rr,zz=q._solve(b,60,100); lp+=1
  statuses.append(rr.status)
 return dict(kind='split',lp=lp,E=E,job=i,times=times,statuses=statuses,ok=ok,
             all_no=all(s==2 for s in statuses))

cases=[]
for name,f in FILES.items():
 for idx,(inst,opt) in enumerate(load(f)): cases.append((name,idx,inst,opt-1))
for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb')):
 cases.append((name+'-p'+str(k),k,inst,opt-1))
rows=[]; t0=time.time()
for name,idx,inst,h in cases:
 r=one_level(inst,h); r.update(name=name,idx=idx); rows.append(r)
agg=dict(cases=len(rows),root_no=sum(r['kind']=='root-no' for r in rows),
         split=sum(r['kind']=='split' for r in rows),
         all_no=sum(r.get('all_no',False) for r in rows),
         multi=sum(r['kind']=='multi' for r in rows),
         mine_feas=sum(r['kind']=='mine-feas' for r in rows),
         certfail=sum(r['kind']=='mine-certfail' for r in rows),
         lp=sum(r['lp'] for r in rows), wall=time.time()-t0)
print('AGG',agg)
for r in rows:
 if r['kind'] not in ('root-no',): print(r)
json.dump(dict(agg=agg,rows=rows),open('exp/v82/split1_bench.json','w'),indent=1)
