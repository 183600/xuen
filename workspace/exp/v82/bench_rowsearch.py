import sys, pickle, time, json
sys.path[:0] = ['exp/v82', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from fullqnc import FullQNC

FILES = {'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
         'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
         'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl',
         'deep8':'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
cases=[]
for name,f in FILES.items():
    for idx,(inst,opt) in enumerate(load(f)): cases.append((name,idx,inst,opt-1))
for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb')):
    cases.append((name+'-p'+str(k),k,inst,opt-1))

def run(inst,h,cuts):
    q=FullQNC(inst,h)
    q.lp.cuts=list(cuts); q.lp.cutset=set(cuts)
    t0=time.time()
    v,st=q.decide(100000,5000,60,100)
    return v,st,q,time.time()-t0

def greedy(inst,h):
    q0=FullQNC(inst,h)
    rows=list(q0.lp.cuts)
    v,st,q,t=run(inst,h,rows)
    if v is not False or not q.audit() or q.cert_fail:
        return dict(err='baseline',v=v,audit=q.audit(),cf=q.cert_fail,n0=len(rows))
    best_lp, best_rows, best_nodes, best_t = st['lp_solves'], rows, st['nodes'], t
    n0=len(rows)
    for r in list(rows):
        if r not in best_rows: continue
        trial=[x for x in best_rows if x!=r]
        v2,st2,q2,t2=run(inst,h,trial)
        if (v2 is False and q2.audit() and q2.cert_fail==0
                and st2['lp_solves']<=best_lp):
            best_rows,best_lp,best_nodes,best_t=trial,st2['lp_solves'],st2['nodes'],t2
    return dict(n0=n0,n1=len(best_rows),lp=best_lp,nodes=best_nodes,
                t=best_t,audit=True)

rows=[]; t0=time.time()
for k,(name,idx,inst,h) in enumerate(cases):
    r=greedy(inst,h); r.update(name=name,idx=idx); rows.append(r)
    if k%20==0: print(k,name,idx,r,flush=True)
print('TOTAL lp',sum(r.get('lp',0) for r in rows),'nodes',sum(r.get('nodes',0) for r in rows),
      'rows',sum(r.get('n1',0) for r in rows),'wall',round(time.time()-t0,2))
print('errors',[r for r in rows if 'err' in r])
json.dump(rows,open('exp/v82/rowsearch_bench.json','w'),indent=1)
