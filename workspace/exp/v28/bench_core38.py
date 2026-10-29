import pickle, sys, time, json
sys.path[:0] = ['exp/v13','exp/v15','exp/v16','exp/v20','exp/v24','exp/v25','exp/v28']
import pace_v25 as P, cps_lib, hybrid

CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
           packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000,
           dhd=True, dcd=True, hpack_on=True, odom=False,
           map_on=True, map_tau=4, map_ncap=16,
           cps_on=True, cps_tau=4, cps_depth=0, cps_ncap=16,
           cps_nodecap=300000, cps_gate_fan=0)

def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def load(f):
    d=pickle.load(open(f,'rb')); out=[]
    for x in d:
        out.append((x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']))
    return out
files=['exp/v13/hard3.pkl','exp/v14/large_a.pkl','exp/v14/large_b.pkl','exp/v14/large_het.pkl']
orig=cps_lib.cps_certify
for tag,fn in [('cps',orig),('hybrid',hybrid.hybrid_certify)]:
    cps_lib.cps_certify=fn
    nodes=tables=0; t0=time.time(); calls=0
    for f in files:
        for inst,opt in load(f):
            cfg=dict(CFG); cfg['omd']=fe(inst); st={}
            (ok,_),st=P.decide(inst,opt-1,stats=st,**cfg)
            nodes+=st['nodes']; tables+=st['tables']; calls+=st.get('cps_calls',0)
    print(tag, nodes, tables, round(time.time()-t0,3), 'cps_calls', calls, flush=True)
cps_lib.cps_certify=orig
