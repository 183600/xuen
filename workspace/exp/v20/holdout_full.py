import sys,random,json,time,statistics
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v15');sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19');sys.path.insert(0,'exp/v20')
import po,pace_q,pace_v18,pace_v19,pace_v20
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
def run(mod,inst,h,odom=False,hpack_on=False,**kw):
    return mod.decide(inst,h,odom=odom,hpack_on=hpack_on,omd=True,**CFG,**kw)
rng=random.Random(424242); rows=[]; tried=0
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
    (b,_),sb=run(pace_q,inst,h)
    if sb['nodes']<15: continue
    (d16,_),s16=run(pace_q,inst,h)
    (d18,_),s18=run(pace_v18,inst,h,dcd=True,hpack_on=True)
    (d19,_),s19=run(pace_v19,inst,h,dcd=True,hpack_on=True,rhd=True)
    (d20,_),s20=run(pace_v20,inst,h,dcd=True,hpack_on=True,dhd=True)
    (ok,_),_=run(pace_v20,inst,opt,dcd=True,hpack_on=True,dhd=True)
    assert b==d18==d19==d20==False and ok
    rows.append(dict(v16=s16['nodes'],v18=s18['nodes'],v19=s19['nodes'],v20=s20['nodes']))
tot={k:sum(r[k] for r in rows) for k in ('v16','v18','v19','v20')}
print(tot, 'v19/v20',round(tot['v19']/tot['v20'],4),'v16/v20',round(tot['v16']/tot['v20'],4),
      'wins',sum(1 for r in rows if r['v20']<r['v19']),
      'ties',sum(1 for r in rows if r['v20']==r['v19']),
      'loss',sum(1 for r in rows if r['v20']>r['v19']))
json.dump(dict(nodes=tot,rows=rows),open('exp/v20/res_holdout_full.json','w'),indent=1)
