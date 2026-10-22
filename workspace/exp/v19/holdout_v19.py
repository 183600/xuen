"""Regenerate the v1.8 held-out 50 (seed 424242) and compare v1.8 vs v1.9."""
import sys,random,json,time,statistics
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v15');sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19')
import po,pace_q,pace_v18,pace_v19
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
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
    dcd=kw.pop('dcd',False); omd=kw.pop('omd',True)
    base=dict(odom=kw.pop('odom',False),hpack_on=kw.pop('hp',False),omd=omd)
    if mod is not pace_q: base['dcd']=dcd
    return mod.decide(inst,h,**base,**CFG,**kw)
rng=random.Random(424242); rows=[]; tried=0; t0=time.time()
while len(rows)<50 and tried<3000:
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
    ((b,_),sb)=run(pace_q,inst,h)
    if sb['nodes']<15: continue
    ((d18,_),s18)=run(pace_v18,inst,h,dcd=True,hp=True)
    ((d19,_),s19)=run(pace_v19,inst,h,dcd=True,hp=True,rhd=True)
    ((ok,_),_)=run(pace_v19,inst,opt,dcd=True,hp=True,rhd=True)
    assert b==d18==d19==False and ok
    rows.append(dict(n=n,opt=opt,base=sb['nodes'],v18=s18['nodes'],v19=s19['nodes'],
                     t18=s18['tables'],t19=s19['tables'],
                     rhd_drops=s19.get('rhd_drops',0),dcd_skips=s19.get('dcd_skips',0)))
out=dict(n=len(rows),tried=tried,
         nodes={k:sum(r[k] for r in rows) for k in ('base','v18','v19')},
         ratio18=round(sum(r['v18'] for r in rows)/sum(r['v19'] for r in rows),3),
         ratio16=round(sum(r['base'] for r in rows)/sum(r['v19'] for r in rows),3),
         wins=sum(1 for r in rows if r['v19']<r['v18']),
         ties=sum(1 for r in rows if r['v19']==r['v18']),
         losses=sum(1 for r in rows if r['v19']>r['v18']),
         median_ratio=round(statistics.median(r['v18']/r['v19'] for r in rows),3),
         rows=rows,sec=round(time.time()-t0,1))
json.dump(out,open('exp/v19/res_holdout_v19.json','w'),indent=1)
print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=1))
