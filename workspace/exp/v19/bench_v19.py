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
def run(mod,inst,h,**kw):
    return mod.decide(inst,h,odom=kw.pop('odom',False),hpack_on=kw.pop('hp',True),
                      omd=fe(inst),dcd=True,**CFG,**kw)
def med(fn,rep=3):
    ts=[]
    for _ in range(rep):
        t=time.time(); r=fn(); ts.append(time.time()-t)
    return statistics.median(ts), r
out={}
# 38
tot={k:0 for k in ('v18','v19')}; rows=[]
for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst,h=rec['inst'],rec['opt']-1
        t18,((b,_),sb)=med(lambda: run(pace_v18,inst,h))
        t19,((d,_),sd)=med(lambda: run(pace_v19,inst,h,rhd=True))
        ((b2,_),_)=run(pace_v19,inst,h,rhd=False)
        assert b==b2==d==False
        ((ok,_),_)=run(pace_v19,inst,rec['opt'],rhd=True); assert ok,(tag,k)
        tot['v18']+=sb['nodes']; tot['v19']+=sd['nodes']
        if sb['nodes']!=sd['nodes']:
            rows.append(dict(tag=tag,idx=k,n=inst['n'],v18=sb['nodes'],v19=sd['nodes'],
                             t18=sb['tables'],t19=sd['tables'],
                             rhd_drops=sd.get('rhd_drops',0),
                             rhd_before=sd.get('rhd_fan_before',0),
                             rhd_after=sd.get('rhd_fan_after',0)))
out['bench38']=dict(total=tot,rows=rows,ratio=round(tot['v18']/tot['v19'],3))
print('38',tot,out['bench38']['ratio']); [print(r) for r in rows]
# deep
D=pickle.load(open('exp/v18/deep.pkl','rb')); tot={k:0 for k in ('v18','v19')}; rows=[]
for idx,(inst,opt,bn,qn,bt,qt) in enumerate(D):
    h=opt-1
    ((b,_),sb)=run(pace_v18,inst,h)
    ((d,_),sd)=run(pace_v19,inst,h,rhd=True)
    assert b==d==False
    ((ok,_),_)=run(pace_v19,inst,opt,rhd=True); assert ok,(idx,)
    tot['v18']+=sb['nodes']; tot['v19']+=sd['nodes']
    rows.append(dict(idx=idx,n=inst['n'],v18=sb['nodes'],v19=sd['nodes'],
                     v18_t=sb['tables'],v19_t=sd['tables'],
                     rhd_drops=sd.get('rhd_drops',0),
                     rhd_before=sd.get('rhd_fan_before',0),
                     rhd_after=sd.get('rhd_fan_after',0),
                     dcd_skips=sd.get('dcd_skips',0)))
out['deep']=dict(total=tot,rows=rows,ratio=round(tot['v18']/tot['v19'],3))
print('deep',tot,out['deep']['ratio']); [print(r) for r in rows]
json.dump(out,open('exp/v19/res_bench_v19.json','w'),indent=1)
