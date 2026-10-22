import sys,random,time,json
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16'); sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18')
import po,pace_q
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def gen(rng,n,m,pmax=10,ep=0.22):
    p=[rng.randint(2,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
rng=random.Random(8080)
tot={'base':0,'q':0}; tt={'base':0.0,'q':0.0}; rows=[]; n_inst=0
while n_inst<60:
    n=rng.randint(10,14); inst=gen(rng,n,3)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),
           (sum(inst['p'])+2)//3,max(inst['p']))
    opt=None
    for h in range(lo,lo+10):
        (ok,_),st=pace_q.decide(inst,h,omd=True,**CFG)
        if ok: opt=h;break
    if opt is None: continue
    h=opt+5
    t=time.time(); (b,_),sb=pace_q.decide(inst,h,omd=True,**CFG); tb=time.time()-t
    t=time.time(); (qq,_),sq=pace_q.decide(inst,h,omd=True,odom=True,hpack_on=True,**CFG); tq=time.time()-t
    assert b==qq==True
    tot['base']+=sb['nodes'];tot['q']+=sq['nodes'];tt['base']+=tb;tt['q']+=tq
    n_inst+=1
out=dict(n=n_inst,nodes=tot,time={k:round(v,4) for k,v in tt.items()})
json.dump(out,open('exp/v18/res_easy.json','w'),indent=1)
print(out)
