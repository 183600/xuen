import sys,pickle,json,time
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v14');sys.path.insert(0,'exp/v15')
sys.path.insert(0,'exp/v16');sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19')
import po, pace_v18, pace_w
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
def load(p):
    d=pickle.load(open(p,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def run(mod,inst,h,odom,hp,mode='dcd'):
    kw=dict(odom=odom,hpack_on=hp,omd=fe(inst),dcd=True,**CFG)
    if mod is pace_w: kw['dcd_mode']=mode
    return mod.decide(inst,h,**kw)
modes=['dcd','tsd','noest','noest_nop','est_ge']
out={}
# 38
tot={m:0 for m in modes}; rows=[]
for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst,h=rec['inst'],rec['opt']-1
        ns={}
        for m in modes:
            ((ok,_),st)=run(pace_w,inst,h,False,True,m); assert ok is False,(tag,k,m)
            ns[m]=st['nodes']
        ((ok,_),st)=run(pace_w,inst,rec['opt'],False,True,'dcd'); assert ok
        for m in modes: tot[m]+=ns[m]
        if len(set(ns.values()))>1: rows.append(dict(tag=tag,idx=k,**ns))
out['bench38']=dict(rows=rows,tot=tot)
print('38',tot); print(rows)
# deep
D=pickle.load(open('exp/v18/deep.pkl','rb'))
tot={m:0 for m in modes}; rows=[]
for idx,(inst,opt,bn,qn,bt,qt) in enumerate(D):
    h=opt-1; ns={}
    for m in modes:
        ((ok,_),st)=run(pace_w,inst,h,False,True,m); assert ok is False,(idx,m)
        ns[m]=st['nodes']
    for m in modes: tot[m]+=ns[m]
    rows.append(dict(idx=idx,n=inst['n'],**ns))
out['deep']=dict(rows=rows,tot=tot)
print('deep',tot)
for r in rows: print(r)
json.dump(out,open('exp/v19/res_oracle_w.json','w'),indent=1)
