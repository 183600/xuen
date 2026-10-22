import sys,pickle,json
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v14');sys.path.insert(0,'exp/v15')
sys.path.insert(0,'exp/v16');sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19')
import po,pace_w
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
def load(p):
    d=pickle.load(open(p,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def run(inst,h,mode):
    return pace_w.decide(inst,h,odom=False,dcd=True,dcd_mode=mode,hpack_on=True,
                         omd=fe(inst),**CFG)
out={}
# 38
tot={'dcd':0,'tsd':0}; rows=[]
for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst,h=rec['inst'],rec['opt']-1; ns={}
        for m in ('dcd','tsd'):
            ((ok,_),st)=run(inst,h,m); assert ok is False,(tag,k,m)
            ns[m]=st['nodes']
        ((ok,_),st)=run(inst,rec['opt'],'tsd'); assert ok,(tag,k,'falseNO')
        for m in ns: tot[m]+=ns[m]
        if len(set(ns.values()))>1: rows.append(dict(tag=tag,idx=k,**ns))
out['bench38']=dict(tot=tot,rows=rows); print('38',tot,rows)
# deep
D=pickle.load(open('exp/v18/deep.pkl','rb')); tot={'dcd':0,'tsd':0}; rows=[]
for idx,(inst,opt,bn,qn,bt,qt) in enumerate(D):
    h=opt-1; ns={}
    for m in ('dcd','tsd'):
        ((ok,_),st)=run(inst,h,m); assert ok is False,(idx,m)
        ns[m]=st['nodes']
    ((ok,_),st)=run(inst,opt,'tsd'); assert ok,(idx,'falseNO')
    for m in ns: tot[m]+=ns[m]; rows.append(dict(idx=idx,n=inst['n'],**ns))
out['deep']=dict(tot=tot,rows=rows); print('deep',tot); [print(r) for r in rows]
json.dump(out,open('exp/v19/res_tsd_w.json','w'),indent=1)
