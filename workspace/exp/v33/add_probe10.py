import sys,pickle
sys.path[:0]=['exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v25']
import po,wos
from gen_data import topo,rev

def run(inst,h,cap):
    st={}; ok,_=wos.sgs_solve(inst,h,nodecap=cap,stats=st); return ok,st

def add(rows):
    for x in rows:
        inst=x['inst']; h=x['h']; r=rev(inst)
        _,pf=run(inst,h,10); _,pb=run(r,h,10)
        x['p10']=[pf.get('memo',10),pb.get('memo',10),pf.get('rsi_hits',0),pb.get('rsi_hits',0),
                  pf.get('forced',0),pb.get('forced',0),pf.get('nodes',10),pb.get('nodes',10)]
    return rows
TR=pickle.load(open('exp/v33/train2.pkl','rb')); add(TR); pickle.dump(TR,open('exp/v33/train3.pkl','wb'))
# holdout: rebuild with inst? holdout_feats did not store inst. Rebuild from cases.
D=pickle.load(open('exp/v20/holdout_cases50.pkl','rb'))
from make_feats import one
HO=[]
for inst,opt in D:
    for hmod in (-1,0):
        x=one(inst,opt+hmod); r=rev(inst)
        _,pf=run(inst,opt+hmod,10); _,pb=run(r,opt+hmod,10)
        x['p10']=[pf.get('memo',10),pb.get('memo',10),pf.get('rsi_hits',0),pb.get('rsi_hits',0),
                  pf.get('forced',0),pb.get('forced',0),pf.get('nodes',10),pb.get('nodes',10)]
        HO.append(x)
pickle.dump(HO,open('exp/v33/holdout3.pkl','wb'))
print('done')
