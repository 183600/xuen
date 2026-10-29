import sys, pickle, json, time
sys.path[:0]=['exp/v81','exp/v71','exp/v61','exp/v60','exp/v13']
from qcc import QCC
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
    cases.append((name,k,inst,opt-1))
rows=[]; t0=time.time()
for name,idx,inst,h in cases:
    q=QNC(inst,h); vq,sq=q.decide()
    c=QCC(inst,h); vc,sc=c.decide()
    rows.append(dict(name=name,idx=idx,
        q_v=vq,q_lp=sq['lp_solves'],q_nodes=sq['nodes'],
        c_v=vc,c_lp=sc['lp_solves'],c_nodes=sc['nodes'],
        covers=sc['covers'],restarts=sc['restarts'],root_lp=sc['root_lp'],
        skip=sc['cover_skipped'],force=sc['force'],audit=c.audit(),
        q_audit=q.audit(),q_t=sq.get('cert_t',0),c_t=sc.get('cert_t',0)))
json.dump(rows,open('exp/v81/qcc_bench.json','w'),indent=1)
for key in ['q','c']:
    print(key,'NO',sum(r[key+'_v'] is False for r in rows),'LP',sum(r[key+'_lp'] for r in rows),'nodes',sum(r[key+'_nodes'] for r in rows))
print('improved LP',sum(r['c_lp']<r['q_lp'] for r in rows),'worse',sum(r['c_lp']>r['q_lp'] for r in rows))
print('wall',time.time()-t0)
for r in rows:
    if r['c_lp']!=r['q_lp'] or r['c_nodes']!=r['q_nodes']:
        print(r)
