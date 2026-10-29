import sys,random,json,time
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v15');sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19');sys.path.insert(0,'exp/v20')
import po,pace_q,pace_v19,pace_v20
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def gen(rng,n,m,pmax=10,ep=0.22):
    p=[rng.randint(2,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7:
            pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
rng=random.Random(8080)
tot={k:0 for k in ('v19','v20')}; tt={k:0.0 for k in ('v19','v20')}
n_inst=0; rows=[]
while n_inst<60:
    n=rng.randint(10,14); inst=gen(rng,n,3)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3,max(inst['p']))
    opt=None
    for h in range(lo,lo+10):
        ok,_=pace_q.decide(inst,h,odom=True,hpack_on=False,omd=True,**CFG)
        if ok: opt=h; break
    if opt is None: continue
    h=opt+5
    ((a,_),sa)=pace_v19.decide(inst,h,odom=False,dcd=True,rhd=True,hpack_on=True,omd=True,**CFG)
    ((b,_),sb)=pace_v20.decide(inst,h,odom=False,dcd=True,dhd=True,hpack_on=True,omd=True,**CFG)
    assert a==b==True
    tot['v19']+=sa['nodes']; tot['v20']+=sb['nodes']
    tt['v19']+=sa['t_run']; tt['v20']+=sb['t_run']
    rows.append((n,sa['nodes'],sb['nodes']))
    n_inst+=1
out=dict(n=n_inst,nodes=tot,time={k:round(v,4) for k,v in tt.items()},
         ratio=round(tot['v19']/max(1,tot['v20']),4),
         time_ratio=round(tt['v19']/max(1e-9,tt['v20']),4),rows=rows)
json.dump(out,open('exp/v20/res_easy.json','w'),indent=1)
print({k:v for k,v in out.items() if k!='rows'})
