import sys,random,json,time
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v23']
import po,pace_q,pace_v20,pace_v23
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
PI=dict(pi=True,pi_depth=0,pi_ncap=16,pi_tau=4,pi_gap=4,pi_wcap=15)
def gen(rng,n,m,pmax=10,ep=0.22):
    p=[rng.randint(2,pmax) for _ in range(n)]; pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
rng=random.Random(8080); rows=[]; n_inst=0
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
    ts={}; res={}
    for name,mod,kw in [('v20',pace_v20,{}),('v23',pace_v23,PI)]:
        t=time.time(); (ok,o),st=mod.decide(inst,h,odom=False,dcd=True,dhd=True,hpack_on=True,omd=True,**CFG,**kw); ts[name]=time.time()-t
        assert ok; res[name]=st
    rows.append(dict(n=n,v20=res['v20']['nodes'],v23=res['v23']['nodes'],
                     t20=ts['v20'],t23=ts['v23'],pi=res['v23'].get('pi_calls',0)))
    n_inst+=1
out=dict(n=n_inst,nodes={k:sum(r[k] for r in rows) for k in ('v20','v23')},
         time={k:round(sum(r[k] for r in rows),4) for k in ('t20','t23')},
         pi_calls=sum(r['pi'] for r in rows),rows=rows)
print({k:v for k,v in out.items() if k!='rows'})
json.dump(out,open('exp/v23/res_easy.json','w'),indent=1)
