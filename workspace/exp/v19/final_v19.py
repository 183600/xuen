"""Consolidated v1.9 numbers: v1.6 / v1.7 / v1.8 / v1.9 on 38 + deep."""
import sys,pickle,json,time,statistics
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v14');sys.path.insert(0,'exp/v15')
sys.path.insert(0,'exp/v16');sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19')
import po,pace_q,pace_v18,pace_v19
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
def load(p):
    d=pickle.load(open(p,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def run(ver,inst,h):
    if ver=='v16': return pace_q.decide(inst,h,odom=False,hpack_on=False,omd=fe(inst),**CFG)
    if ver=='v17': return pace_q.decide(inst,h,odom=True,hpack_on=True,omd=fe(inst),**CFG)
    if ver=='v18': return pace_v18.decide(inst,h,odom=False,dcd=True,hpack_on=True,omd=fe(inst),**CFG)
    return pace_v19.decide(inst,h,odom=False,dcd=True,rhd=True,hpack_on=True,omd=fe(inst),**CFG)
def med(fn,rep=3):
    ts=[]
    for _ in range(rep):
        t=time.time(); r=fn(); ts.append(time.time()-t)
    return statistics.median(ts),r
out={}
for setname,path in [('bench38',None),('deep',None)]: pass
# 38
vers=('v16','v17','v18','v19'); tot={v:0 for v in vers}; tab={v:0 for v in vers}; tt={v:0.0 for v in vers}; rows=[]
for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst,h=rec['inst'],rec['opt']-1; ns={}
        for v in vers:
            t,((b,_),st)=med(lambda:run(v,inst,h)); assert b is False,(tag,k,v)
            ns[v]=st['nodes']; tot[v]+=st['nodes']; tab[v]+=st['tables']; tt[v]+=t
        ((ok,_),_)=run('v19',inst,rec['opt']); assert ok
        if len(set(ns.values()))>1:
            rows.append(dict(tag=tag,idx=k,n=inst['n'],**ns,
                             t18=None,t19=None))
out['bench38']=dict(nodes=tot,tables=tab,time={v:round(tt[v],4) for v in vers},
                    rows=rows,ratio17=round(tot['v17']/tot['v19'],3),
                    ratio18=round(tot['v18']/tot['v19'],3),
                    ratio16=round(tot['v16']/tot['v19'],3))
print('38',tot,tab,out['bench38']['time']); [print(r) for r in rows]
# deep
D=pickle.load(open('exp/v18/deep.pkl','rb')); tot={v:0 for v in vers}; tab={v:0 for v in vers}; tt={v:0.0 for v in vers}; rows=[]
for idx,(inst,opt,bn,qn,bt,qt) in enumerate(D):
    h=opt-1; ns={}
    for v in vers:
        t,((b,_),st)=med(lambda:run(v,inst,h)); assert b is False,(idx,v)
        ns[v]=st['nodes']; tot[v]+=st['nodes']; tab[v]+=st['tables']; tt[v]+=t
    ((ok,_),_)=run('v19',inst,opt); assert ok
    st19=run('v19',inst,h)[1]
    rows.append(dict(idx=idx,n=inst['n'],**ns,
                     rhd_drops=st19.get('rhd_drops',0),
                     rhd_before=st19.get('rhd_fan_before',0),
                     rhd_after=st19.get('rhd_fan_after',0),
                     dcd_skips=st19.get('dcd_skips',0)))
out['deep']=dict(nodes=tot,tables=tab,time={v:round(tt[v],4) for v in vers},
                 rows=rows,ratio17=round(tot['v17']/tot['v19'],3),
                 ratio18=round(tot['v18']/tot['v19'],3),
                 ratio16=round(tot['v16']/tot['v19'],3))
print('deep',tot,tab,out['deep']['time']); [print(r) for r in rows]
json.dump(out,open('exp/v19/res_final_v19.json','w'),indent=1)
