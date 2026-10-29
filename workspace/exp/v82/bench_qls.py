import sys, pickle, json, time
sys.path[:0]=['exp/v82','exp/v71','exp/v61','exp/v60','exp/v13']
from qls import QLS
from qnc import QNC

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl', 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl', 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl', 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl'}

def load(f):
 d=pickle.load(open(f,'rb'))
 return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]

cases=[]
for name,f in FILES.items():
 for idx,(inst,opt) in enumerate(load(f)):
  cases.append((name,idx,inst,opt-1))
for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb')):
 cases.append((name+'-p'+str(k),k,inst,opt-1))

rows=[]
t0=time.time()
for ci,(name,idx,inst,h) in enumerate(cases):
 q=QLS(inst,h)
 v,st=q.decide()
 rows.append(dict(name=name,idx=idx,h=h,v=v,lp=st['lp_solves'],nodes=st['nodes'],
   leaves=st['leaves'],clauses=st['clauses'],splits=q.splits,mines=q.mines,
   mine_fail=q.mine_fail,split_lits=q.split_lits,
   proof_ok=all(p[3] for p in q.proofs), audit=q.audit(),
   t=st['cert_t'], force=st['force']))
 if ci%20==0: print(ci,name,idx,v,st['lp_solves'],st['nodes'],q.splits,flush=True)
agg=dict(no=sum(r['v'] is False for r in rows),lp=sum(r['lp'] for r in rows),
         nodes=sum(r['nodes'] for r in rows),splits=sum(r['splits'] for r in rows),
         mines=sum(r['mines'] for r in rows),mine_fail=sum(r['mine_fail'] for r in rows),
         leaves=sum(r['leaves'] for r in rows),audit=sum(r['audit'] for r in rows),
         proof_ok=sum(r['proof_ok'] for r in rows),wall=time.time()-t0)
print('AGG',agg)
json.dump(dict(agg=agg,rows=rows),open('exp/v82/qls_bench.json','w'),indent=1)
# print interesting rows
for r in rows:
 if r['splits'] or r['lp']>1:
  print(r)
