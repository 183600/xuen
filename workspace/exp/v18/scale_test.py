import sys, random, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16'); sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18')
import po, pace_omd

def gen(rng,n,m,pmax=10,ep=0.25):
    p=[rng.randint(2,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.8: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)

def solve(inst,h,cap=120000):
    t=time.time()
    (ok,out),st=pace_omd.decide(inst,h,mode='pot',nodecap=cap,mint_on=True,mint_depth=0,
        packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000,omd=True)
    return ok,st,time.time()-t

rng=random.Random(777)
for n in (16,18,20):
  print('=== n',n,flush=True)
  for k in range(6):
    inst=gen(rng,n,3)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3,max(inst['p']))
    opt=None
    for h in range(lo,lo+15):
        ok,st,dt=solve(inst,h)
        if st.get('timeout'): break
        if ok: opt=h; break
    if opt is None:
        print('k',k,'no OPT (timeout at YES search)',flush=True); continue
    ok,st,dt=solve(inst,opt-1)
    print('k',k,'n',n,'opt',opt,'NO nodes',st['nodes'],'tables',st['tables'],'time',round(dt,3),'timeout',st.get('timeout'),flush=True)
