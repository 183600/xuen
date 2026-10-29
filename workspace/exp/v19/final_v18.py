"""Consolidated v1.8 numbers: v1.6 / v1.7 / v1.8 on 38 + deep + easy.

All runs use the same nodecap and the same machine-choice mode.
Timing = median of three wall-clock runs on the same process.
"""
import sys, pickle, json, time, random, statistics
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v15')
sys.path.insert(0,'exp/v16'); sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18'); sys.path.insert(0,'exp/v19')
import po, pace_q, pace_v18
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]

def load(path):
    d=pickle.load(open(path,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def run(mod,inst,h,odom,dcd=False,direct=False,hp=False):
    kw=dict(odom=odom,hpack_on=hp,omd=fe(inst),**CFG)
    if mod is pace_v18:
        kw['dcd']=dcd; kw['dcd_direct']=direct
    return mod.decide(inst,h,**kw)
def medtime(fn,rep=3):
    ts=[]
    for _ in range(rep):
        t=time.time(); r=fn(); ts.append(time.time()-t)
    return statistics.median(ts),r

out={}
# 38
tot={k:0 for k in ('v16','v17','v18')}; tab={k:0 for k in ('v16','v17','v18')}
tt={k:[] for k in ('v16','v17','v18')}; rows=[]
for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst,h=rec['inst'],rec['opt']-1
        t16,((b,_),sb)=medtime(lambda:run(pace_q,inst,h,False,hp=False))
        t17,((q,_),sq)=medtime(lambda:run(pace_q,inst,h,True,hp=True))
        t18,((d,_),sd)=medtime(lambda:run(pace_v18,inst,h,False,dcd=True,hp=True))
        assert b==q==d==False
        ((ok,_),_)=run(pace_v18,inst,rec['opt'],False,dcd=True,hp=True)
        assert ok
        for key,s in [('v16',sb),('v17',sq),('v18',sd)]:
            tot[key]+=s['nodes']; tab[key]+=s['tables']
        tt['v16'].append(t16); tt['v17'].append(t17); tt['v18'].append(t18)
        if len({sb['nodes'],sq['nodes'],sd['nodes']})>1:
            rows.append(dict(tag=tag,idx=k,n=inst['n'],m=inst['m'],opt=rec['opt'],
                             v16=sb['nodes'],v17=sq['nodes'],v18=sd['nodes'],
                             v16_t=sb['tables'],v18_t=sd['tables']))
out['bench38']=dict(rows=rows,nodes=tot,tables=tab,
                    time={k:round(sum(v),4) for k,v in tt.items()},
                    ratio16=round(tot['v16']/tot['v18'],3),
                    ratio17=round(tot['v17']/tot['v18'],3))
print('38',out['bench38']['nodes'],out['bench38']['tables'],out['bench38']['time'])

# deep
D=pickle.load(open('exp/v18/deep.pkl','rb'))
tot={k:0 for k in ('v16','v17','v18','v18_nohp','dcd_succ')}; tab={k:0 for k in ('v16','v17','v18')}
tt={k:[] for k in ('v16','v17','v18')}; rows=[]
for idx,(inst,opt,bn,qn,bt,qt) in enumerate(D):
    h=opt-1
    t16,((b,_),sb)=medtime(lambda:run(pace_q,inst,h,False,hp=False))
    t17,((q,_),sq)=medtime(lambda:run(pace_q,inst,h,True,hp=True))
    t18,((d,_),sd)=medtime(lambda:run(pace_v18,inst,h,False,dcd=True,hp=True))
    ((_,_),sdn)=run(pace_v18,inst,h,False,dcd=True,hp=False)
    ((_,_),sds)=run(pace_v18,inst,h,False,dcd=True,direct=True,hp=True)
    assert b==q==d==False
    ((ok,_),_)=run(pace_v18,inst,opt,False,dcd=True,hp=True)
    assert ok
    for key,s in [('v16',sb),('v17',sq),('v18',sd)]:
        tot[key]+=s['nodes']; tab[key]+=s['tables']
    tot['v18_nohp']+=sdn['nodes']; tot['dcd_succ']+=sds['nodes']
    tt['v16'].append(t16); tt['v17'].append(t17); tt['v18'].append(t18)
    rows.append(dict(idx=idx,n=inst['n'],m=inst['m'],opt=opt,
                     v16=sb['nodes'],v17=sq['nodes'],v18=sd['nodes'],
                     v18_nohp=sdn['nodes'],dcd_succ=sds['nodes'],
                     v16_t=sb['tables'],v18_t=sd['tables'],
                     fan_max_before=sd['dcd_fan_max_before'],
                     fan_max_after=sd['dcd_fan_max_after'],
                     fan_sum_before=sd['dcd_fan_before'],
                     fan_sum_after=sd['dcd_fan_after'],
                     sink_skips=sd['dcd_sink_skips'],
                     strict_skips=sd['dcd_strict_skips'],
                     eq_skips=sd['dcd_eq_skips']))
out['deep']=dict(rows=rows,nodes=tot,tables=tab,
                 time={k:round(sum(v),4) for k,v in tt.items()},
                 ratio16=round(tot['v16']/tot['v18'],3),
                 ratio17=round(tot['v17']/tot['v18'],3))
print('deep',out['deep']['nodes'],out['deep']['tables'],out['deep']['time'])

# easy (same generator/seed as v1.7's easy_q.py)
def gen(rng,n,m,pmax=10,ep=0.22):
    p=[rng.randint(2,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7:
            pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
rng=random.Random(8080); tot={k:0 for k in ('v16','v17','v18')}; tt={k:0.0 for k in ('v16','v17','v18')}
n_inst=0
while n_inst<60:
    n=rng.randint(10,14); inst=gen(rng,n,3)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3,max(inst['p']))
    opt=None
    for h in range(lo,lo+10):
        ((ok,_),st)=run(pace_q,inst,h,True,hp=False)
        if ok: opt=h; break
    if opt is None: continue
    h=opt+5
    _, ((b,_),sb)=medtime(lambda:run(pace_q,inst,h,False,hp=False))
    _, ((q2,_),sq)=medtime(lambda:run(pace_q,inst,h,True,hp=True))
    _, ((d,_),sd)=medtime(lambda:run(pace_v18,inst,h,False,dcd=True,hp=True))
    assert b==q2==d==True
    for key,s in [('v16',sb),('v17',sq),('v18',sd)]: tot[key]+=s['nodes']
    for key,t in [('v16',sb['t_run']),('v17',sq['t_run']),('v18',sd['t_run'])]: tt[key]+=t
    n_inst+=1
out['easy']=dict(n=n_inst,nodes=tot,time={k:round(v,4) for k,v in tt.items()})
print('easy',out['easy'])
json.dump(out,open('exp/v19/res_final_v18.json','w'),indent=1)
