import sys, pickle, random, time
sys.path[:0]=['exp/v13','exp/v15','exp/v16','exp/v20','exp/v24','exp/v25']
import po, pace_v25 as P
def decide_exact(inst,h,nodecap=2_000_000):
    st={}
    (ok,_),st=P.decide(inst,h,nodecap=nodecap,dhd=True,dcd=True,hpack_on=True,
                       map_on=True,cps_on=False,packset_on=True,sop_on=False,
                       omd=False,stats=st)
    if ok is None or st.get('timeout'): return None
    return bool(ok)
def opt_of(inst,hi):
    lo=max(inst['p'])
    while lo<hi:
        mid=(lo+hi)//2; v=decide_exact(inst,mid)
        if v is None: return None
        if v: hi=mid
        else: lo=mid+1
    return lo
rng=random.Random(99); out=[]; tries=0; t0=time.time()
while len(out)<45 and tries<400:
    tries+=1
    n=rng.randint(11,16); m=rng.choice([3,3,4])
    p=[rng.randint(1,4) for _ in range(n)]
    pe=rng.choice([0.10,0.15,0.20,0.28])
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<pe: pred[j].append(i)
    inst=po.make_inst(p,m,pred)
    opt=opt_of(inst,sum(p))
    if opt is None: continue
    h=opt-1
    est,q=po.heads_tails(inst,0,[0]*n)
    S=h-max(est[i]+p[i]+q[i] for i in range(n))
    if not (0<=S<=4): continue
    out.append((inst,opt,tries))
    print('accepted',len(out),'tries',tries,'n',n,'m',m,'S',S,'opt',opt,'elapsed',round(time.time()-t0,1),flush=True)
pickle.dump(out,open('exp/v28/synth2_45.pkl','wb'))
print('done',len(out),tries,round(time.time()-t0,1))
