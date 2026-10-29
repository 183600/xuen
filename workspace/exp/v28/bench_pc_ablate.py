import sys, time, json, pickle
sys.path[:0]=['exp/v13','exp/v15','exp/v16','exp/v20','exp/v24','exp/v25','exp/v28']
import root_pc

def load(f):
    d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
def synth():
    d=pickle.load(open('exp/v28/synth2_45.pkl','rb')); return [(x[0],x[1]) for x in d]
sets={'holdout':load('exp/v20/holdout_cases50.pkl'),'hard3':load('exp/v13/hard3.pkl'),
      'residual':[load('exp/v20/holdout_cases50.pkl')[i] for i in [5,21,32,42,47]],
      'synth':synth()}
variants={
 'default':dict(),
 'no_icc':dict(icc_on=False),
 'no_probe':dict(probe=0),
 'probe64':dict(probe=64),
 'probe300':dict(probe=300),
 'no_os':dict(os_ncap=0),
 'pace_only':dict(pmax=0,icc_on=False),
}
out={}
for vn,kw in variants.items():
    out[vn]={}
    for sn,cs in sets.items():
        t=time.time(); nodes=0; vs={}
        for inst,opt in cs:
            st={}; ok,st=root_pc.pc_solve(inst,opt-1,stats=st,**kw)
            nodes+= (st.get('probe_nodes') or 0)+(st.get('os_nodes') or 0)+(st.get('pace_nodes') or 0)
            vs[st['verdict']]=vs.get(st['verdict'],0)+1
        out[vn][sn]=dict(t=round(time.time()-t,4),nodes=nodes,vs=vs)
        print(vn,sn,out[vn][sn],flush=True)
json.dump(out,open('exp/v28/res_pc_ablate.json','w'),indent=1)
