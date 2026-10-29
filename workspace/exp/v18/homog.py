import sys,random,time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16'); sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18')
import po, pace_dbg
CFG=dict(mode='pot',mint_on=True,mint_depth=0,packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000,omd=True)
def gen(rng,n,m,k,pvals,ep=0.3):
    p=[rng.choice(pvals) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(k):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j]: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
def solve(inst,h,odom,cap=2_000_000):
    t=time.time()
    (ok,out),st=pace_dbg.decide(inst,h,odom=odom,nodecap=cap,**CFG)
    return ok,st,time.time()-t
rng=random.Random(4242)
for trial in range(8):
    n=16;m=3;k=8
    inst=gen(rng,n,m,k,[3,4,5])
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+m-1)//m,max(inst['p']))
    opt=None
    for h in range(lo,lo+12):
        ok,st,dt=solve(inst,h,True,cap=300000)
        if st.get('timeout'): break
        if ok: opt=h;break
    if opt is None:
        print('trial',trial,'no opt'); continue
    okq,sq,tq=solve(inst,opt-1,True)
    okb,sb,tb=solve(inst,opt-1,False,cap=1_500_000)
    print('trial',trial,'opt',opt,'Q',okq,sq['nodes'],round(tq,3),'BASE',okb,sb['nodes'],round(tb,3),'timeout',sb.get('timeout'),flush=True)
