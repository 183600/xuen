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
    t0=time.time(); v,st=q.decide(100000,5000,60,100); return v,st,q,time.time()-t0

def greedy(inst,h):
    q0=FullQNC(inst,h); rows=list(q0.lp.cuts)
    v,st,q,t=run(inst,h,rows)
    assert v is False and q.audit() and q.cert_fail==0
    best_lp,best_rows,best_nodes=st['lp_solves'],rows,st['nodes']
    n0=len(rows)
    for r in list(rows):
        if r not in best_rows: continue
        trial=[x for x in best_rows if x!=r]
        v2,st2,q2,t2=run(inst,h,trial)
        if (v2 is False and q2.audit() and q2.cert_fail==0
                and st2['lp_solves']<=best_lp):
            best_rows,best_lp,best_nodes=trial,st2['lp_solves'],st2['nodes']
    return n0,best_rows,best_lp,best_nodes

out=[]; t0=time.time()
for k,(name,idx,inst,h) in enumerate(cases):
    n0,rows,lp,nodes=greedy(inst,h)
    out.append(dict(name=name,idx=idx,n0=n0,n1=len(rows),lp=lp,nodes=nodes,
                    rows=[list(x) for x in rows]))
    if k%25==0: print('greedy',k,name,idx,'rows',n0,'->',len(rows),'lp',lp,flush=True)
print('offline wall',round(time.time()-t0,2),'lp',sum(r['lp'] for r in out),
      'rows',sum(r['n1'] for r in out),flush=True)
json.dump(out,open('exp/v82/rowsearch_rows.json','w'),indent=1)
# verify final row sets independently
t1=time.time(); lp=nodes=aud=0; bad=[]
for r in out:
    name,idx=r['name'],r['idx']
    inst,h=next((inst,opt-1) for (nm,i,inst,opt) in cases if nm==name and i==idx)
    cuts=[tuple(x) for x in r['rows']]
    v,st,q,t=run(inst,h,cuts)
    ok=(v is False and q.audit() and q.cert_fail==0 and st['lp_solves']==r['lp']
        and st['nodes']==r['nodes'])
    if not ok: bad.append((name,idx,v,q.audit(),q.cert_fail,st['lp_solves'],r['lp']))
    lp+=st['lp_solves']; nodes+=st['nodes']; aud+=q.audit()
print('verify wall',round(time.time()-t1,2),'lp',lp,'nodes',nodes,'audit',aud,'bad',bad[:5])
