import sys,pickle,json,time
sys.path[:0]=['exp/v81','exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
from qcc2 import QCC2
from aqc1 import AQC1
from sqr import SQR
FILES={'holdout50':'exp/v20/holdout_cases50.pkl','synth45':'exp/v28/synth2_45.pkl',
 'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl',
 'large_het':'exp/v14/large_het.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
def mk(cases):
    out=[]
    for name,idx,inst,h in cases:
        row={}
        for tag,cls,kw in [('q',QNC,{}),('c',QCC2,{'cut_kind':'uniform'}),
                           ('a',AQC1,{}),('s',SQR,{})]:
            x=cls(inst,h,**kw); v,st=x.decide()
            row[tag]=dict(v=v,lp=st['lp_solves'],nodes=st['nodes'],why=st['why'],
                          splits=st.get('splits',0),probes=st.get('probes',0),
                          audit=x.audit(),
                          audit_split=(x.audit_split() if hasattr(x,'audit_split') else None))
        row['name']=name; row['idx']=idx
        out.append(row)
    return out
corpus=[]
for name,f in FILES.items():
    for idx,(inst,opt) in enumerate(load(f)): corpus.append((name,idx,inst,opt-1))
pert=[(name,k,inst,opt-1) for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb'))]
stress=[(r['src'],r['idx'],r['inst'],r['h']) for r in pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))]
t0=time.time(); out={'corpus':mk(corpus),'pert':mk(pert),'stress':mk(stress)}
json.dump(out,open('exp/v81/final_bench.json','w'),indent=1)
for part in out:
    rows=out[part]; print('===',part,len(rows))
    for tag in 'qcas':
        print(tag,'NO',sum(r[tag]['v'] is False for r in rows),'LP',sum(r[tag]['lp'] for r in rows),'nodes',sum(r[tag]['nodes'] for r in rows),
              'audit',sum(bool(r[tag]['audit']) for r in rows),'split_audit',sum(bool(r[tag]['audit_split']) for r in rows))
print('wall',round(time.time()-t0,1))
