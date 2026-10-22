"""Held-out random suite: 100 instances with a non-trivial v1.6 tree.

Generation is independent of deep.pkl (which was selected for base>=200).
"""
import sys,random,json,time,statistics
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18'); sys.path.insert(0,'exp/v19')
import po,pace_q,pace_v18
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
def run(mod,inst,h,odom,dcd=False,hp=False):
    kw=dict(odom=odom,hpack_on=hp,omd=True,**CFG)
    if mod is pace_v18: kw['dcd']=dcd
    return mod.decide(inst,h,**kw)
rng=random.Random(424242)
rows=[]; tried=0
t0=time.time()
while len(rows)<50 and tried<3000:
    tried+=1
    n=rng.randint(12,16); inst=gen(rng,n,3)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3)
    opt=None
    for h in range(lo,lo+18):
        (ok,_),st=run(pace_q,inst,h,False,hp=False)
        if ok: opt=h; break
    if opt is None: continue
    h=opt-1
    ((b,_),sb)=run(pace_q,inst,h,False,hp=False)
    if sb["nodes"]<15: continue
    ((q7,_),s7)=run(pace_q,inst,h,True,hp=True)
    ((d8,_),s8)=run(pace_v18,inst,h,False,dcd=True,hp=True)
    ((ok,_),_)=run(pace_v18,inst,opt,False,dcd=True,hp=True)
    assert b==q7==d8==False and ok
    rows.append(dict(n=n,opt=opt,base=sb['nodes'],v17=s7['nodes'],v18=s8['nodes'],
                     fan_max=s8['dcd_fan_max_before'],fan_after=s8['dcd_fan_max_after']))
out=dict(n=len(rows),tried=tried,
         nodes={k:sum(r[k] for r in rows) for k in ('base','v17','v18')},
         ratio17=round(sum(r['v17'] for r in rows)/sum(r['v18'] for r in rows),3),
         ratio16=round(sum(r['base'] for r in rows)/sum(r['v18'] for r in rows),3),
         wins=sum(1 for r in rows if r['v18']<r['v17']),
         ties=sum(1 for r in rows if r['v18']==r['v17']),
         losses=sum(1 for r in rows if r['v18']>r['v17']),
         median_ratio=round(statistics.median(r['v17']/r['v18'] for r in rows),3),
         rows=rows)
json.dump(out,open('exp/v19/res_rand_v18.json','w'),indent=1)
print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=1))
print('time',round(time.time()-t0,2))
