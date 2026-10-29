import sys,random,time,pickle
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16'); sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18')
import po, pace_dbg
CFG=dict(mode='pot',mint_on=True,mint_depth=0,packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def gen(rng,n,m,pvals,ep):
    p=[rng.choice(pvals) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.75: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
def solve(inst,h,q,cap):
    (ok,out),st=pace_dbg.decide(inst,h,nodecap=cap,omd=True,odom=q,hpack_on=q,**CFG)
    return ok,st
rng=random.Random(31337)
kept=[]; t0=time.time(); tries=0
while len(kept)<8 and time.time()-t0<420 and tries<600:
    tries+=1
    n=rng.randint(12,16); m=3
    inst=gen(rng,n,m,rng.choice([[4,5,6],[3,4,5],[5,6,7]]),rng.choice([0.2,0.25,0.3]))
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+m-1)//m,max(inst['p']))
    opt=None
    for h in range(lo,lo+10):
        ok,st=solve(inst,h,False,cap=250000)
        if st.get('timeout'): break
        if ok: opt=h;break
    if opt is None: continue
    okb,sb=solve(inst,opt-1,False,250000)
    if sb.get('timeout'): continue
    if sb['nodes']<200: continue
    okq,sq=solve(inst,opt-1,True,250000)
    kept.append((inst,opt,sb['nodes'],sq['nodes'],sb['tables'],sq['tables']))
    print('kept',len(kept),'n',n,'opt',opt,'base',sb['nodes'],'q',sq['nodes'],'t',round(time.time()-t0,1),flush=True)
print('tries',tries,'kept',len(kept))
pickle.dump(kept,open('exp/v18/deep.pkl','wb'))
