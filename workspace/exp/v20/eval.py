"""v2.0 (DHD) vs v1.9 (RHD): 38, deep, held-out 50, adversarial, easy."""
import sys,random,json,time,statistics,pickle
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v14');sys.path.insert(0,'exp/v15')
sys.path.insert(0,'exp/v16');sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18')
sys.path.insert(0,'exp/v19');sys.path.insert(0,'exp/v20')
import po,pace_q,pace_v19,pace_v20
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def load(path):
    d=pickle.load(open(path,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def runv(ver,inst,h,**kw):
    base=dict(odom=False,dcd=True,hpack_on=True,omd=kw.pop('omd',fe(inst)),**CFG,**kw)
    if ver=='v19': return pace_v19.decide(inst,h,rhd=True,**base)
    return pace_v20.decide(inst,h,dhd=True,**base)
def med(fn,rep=3):
    ts=[]; r=None
    for _ in range(rep):
        t=time.time(); r=fn(); ts.append(time.time()-t)
    return statistics.median(ts),r
out={}
# ---------- 38 ----------
SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
tot={k:0 for k in ('v19','v20')}; tab={k:0 for k in ('v19','v20')}; tt={k:0.0 for k in ('v19','v20')}; rows=[]
for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst,h=rec['inst'],rec['opt']-1
        for v in ('v19','v20'):
            t,((b,_),st)=med(lambda:runv(v,inst,h)); assert b is False,(tag,k,v)
            tot[v]+=st['nodes']; tab[v]+=st['tables']; tt[v]+=t
        ((ok,_),_)=runv('v20',inst,rec['opt']); assert ok,(tag,k)
        rows.append(dict(tag=tag,idx=k,n=inst['n'],v19=None,v20=None))
        if True:
            r=rows[-1]; r['v19']=runv('v19',inst,h)[1]['nodes']; r['v20']=runv('v20',inst,h)[1]['nodes']
out['bench38']=dict(nodes=tot,tables=tab,time={k:round(v,4) for k,v in tt.items()},
                    ratio=round(tot['v19']/tot['v20'],4),rows=[r for r in rows if r['v19']!=r['v20']])
print('38',tot,tab,out['bench38']['time'],out['bench38']['ratio'],flush=True)
for r in out['bench38']['rows']: print(' ',r,flush=True)
# ---------- deep ----------
D=pickle.load(open('exp/v18/deep.pkl','rb'))
tot={k:0 for k in ('v19','v20')}; tab={k:0 for k in ('v19','v20')}; tt={k:0.0 for k in ('v19','v20')}; rows=[]
for idx,(inst,opt,*_) in enumerate(D):
    h=opt-1
    for v in ('v19','v20'):
        t,((b,_),st)=med(lambda:runv(v,inst,h)); assert b is False,(idx,v)
        tot[v]+=st['nodes']; tab[v]+=st['tables']; tt[v]+=t
    ((ok,_),_)=runv('v20',inst,opt); assert ok,idx
    s19=runv('v19',inst,h)[1]; s20=runv('v20',inst,h)[1]
    rows.append(dict(idx=idx,n=inst['n'],v19=s19['nodes'],v20=s20['nodes'],
                     t19=s19['tables'],t20=s20['tables'],
                     rhd_drops=s20.get('rhd_drops',0)))
out['deep']=dict(nodes=tot,tables=tab,time={k:round(v,4) for k,v in tt.items()},
                 ratio=round(tot['v19']/tot['v20'],4),rows=rows)
print('deep',tot,tab,out['deep']['time'],out['deep']['ratio'],flush=True)
for r in rows: print(' ',r,flush=True)
json.dump(out,open('exp/v20/res_main.json','w'),indent=1)
