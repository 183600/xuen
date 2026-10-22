import sys,random,json,time,statistics
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v23']
import po,pace_q,pace_v20,pace_v23
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
PICFG=dict(pi=True,pi_depth=0,pi_ncap=16,pi_tau=4,pi_gap=4,pi_wcap=15)
def gen(rng,n,m):
    p=[rng.randint(2,9) for _ in range(n)]
    pred=[[] for _ in range(n)]
    ep=rng.choice([0.18,0.22,0.28,0.35])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j]: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
def run(mod,inst,h,**kw):
    if mod is pace_q:
        return mod.decide(inst,h,odom=False,hpack_on=False,omd=True,**CFG,**kw)
    if mod is pace_v23:
        return mod.decide(inst,h,odom=False,hpack_on=True,omd=True,dcd=True,dhd=True,**CFG,**PICFG,**kw)
    return mod.decide(inst,h,odom=False,hpack_on=True,omd=True,dcd=True,dhd=True,**CFG,**kw)
rng=random.Random(424242); rows=[]; tried=0; cases=[]
while len(cases)<50 and tried<3000:
    tried+=1
    n=rng.randint(12,16); inst=gen(rng,n,3)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3)
    opt=None
    for h in range(lo,lo+18):
        (ok,_),_=run(pace_q,inst,h)
        if ok: opt=h; break
    if opt is None: continue
    h=opt-1
    (b,_),sb=run(pace_q,inst,h)
    if sb['nodes']<15: continue
    cases.append((inst,opt))
print('generated',len(cases),'tried',tried,flush=True)
tot={'v20':0,'v23':0}; tt={'v20':0.0,'v23':0.0}; tab={'v20':0,'v23':0}
for idx,(inst,opt) in enumerate(cases):
    h=opt-1
    for v,mod in [('v20',pace_v20),('v23',pace_v23)]:
        ts=[]; r=None
        for _ in range(2):
            t=time.time(); r=run(mod,inst,h); ts.append(time.time()-t)
        tt[v]+=statistics.median(ts)
        assert r[0][0] is False,(idx,v)
        tot[v]+=r[1]['nodes']; tab[v]+=r[1]['tables']
    (ok,o),_=run(pace_v23,inst,opt); assert ok,idx
    s20=run(pace_v20,inst,h)[1]; s23=run(pace_v23,inst,h)[1]
    rows.append(dict(idx=idx,n=inst['n'],v20=s20['nodes'],v23=s23['nodes'],
                     pi=s23.get('pi_beta'),pi_time=round(s23.get('pi_time',0),4),
                     calls=s23.get('pi_calls',0)))
print('heldout',tot,tab,{k:round(v,3) for k,v in tt.items()},flush=True)
print('wins',sum(1 for r in rows if r['v23']<r['v20']),
      'ties',sum(1 for r in rows if r['v23']==r['v20']),
      'loss',sum(1 for r in rows if r['v23']>r['v20']),flush=True)
for r in rows:
    if r['v20']!=r['v23']: print(' ',r,flush=True)
json.dump(dict(nodes=tot,tables=tab,time={k:round(v,4) for k,v in tt.items()},rows=rows),
          open('exp/v23/res_holdout.json','w'),indent=1)
