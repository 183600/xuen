import sys,pickle,json,time,statistics
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v14');sys.path.insert(0,'exp/v15')
sys.path.insert(0,'exp/v16');sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19')
import po,pace_v18,pace_v19
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
def load(p):
    d=pickle.load(open(p,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
CONF={
 'base':      dict(dcd=False,rhd=False,hp=False),
 'hp':        dict(dcd=False,rhd=False,hp=True),
 'dcd':       dict(dcd=True, rhd=False,hp=True),
 'rhd':       dict(dcd=False,rhd=True, hp=True),
 'dcd+rhd':   dict(dcd=True, rhd=True, hp=True),
}
def run(inst,h,c,mod=pace_v19):
    return mod.decide(inst,h,odom=False,hpack_on=c['hp'],omd=fe(inst),
                      dcd=c['dcd'],rhd=c['rhd'],**CFG)
def med(fn,rep=3):
    ts=[]
    for _ in range(rep):
        t=time.time(); r=fn(); ts.append(time.time()-t)
    return statistics.median(ts),r
out={}
# 38
tot={k:0 for k in CONF}; tt={k:0.0 for k in CONF}; tab={k:0 for k in CONF}; rows=[]
for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst,h=rec['inst'],rec['opt']-1
        ns={}
        for name,c in CONF.items():
            t,((b,_),st)=med(lambda: run(inst,h,c))
            assert b is False,(tag,k,name)
            ns[name]=st['nodes']; tot[name]+=st['nodes']; tab[name]+=st['tables']; tt[name]+=t
        ((ok,_),_)=run(inst,rec['opt'],CONF['dcd+rhd']); assert ok
        if len(set(ns.values()))>1: rows.append(dict(tag=tag,idx=k,**ns))
out['bench38']=dict(nodes=tot,tables=tab,time={k:round(v,4) for k,v in tt.items()},rows=rows)
print('38',tot,tab); [print(r) for r in rows]
# deep
D=pickle.load(open('exp/v18/deep.pkl','rb')); tot={k:0 for k in CONF}; tab={k:0 for k in CONF}; rows=[]
for idx,(inst,opt,bn,qn,bt,qt) in enumerate(D):
    h=opt-1; ns={}
    for name,c in CONF.items():
        ((b,_),st)=run(inst,h,c); assert b is False,(idx,name)
        ns[name]=st['nodes']; tot[name]+=st['nodes']; tab[name]+=st['tables']
    ((ok,_),_)=run(inst,opt,CONF['dcd+rhd']); assert ok
    rows.append(dict(idx=idx,n=inst['n'],**ns))
out['deep']=dict(nodes=tot,tables=tab,rows=rows)
print('deep',tot,tab); [print(r) for r in rows]
json.dump(out,open('exp/v19/res_ablate_v19.json','w'),indent=1)
