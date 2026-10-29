"""Unit checks for the composed quotient K = DCD(RHD(READY))."""
import sys,random,itertools
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v15');sys.path.insert(0,'exp/v16');sys.path.insert(0,'exp/v19')
import po,pace_v19

def dom_dcd(i,j,p,E,fut,est):
    # i dominates j?  (j can be dropped)
    if p[i]!=p[j] or E[i]!=E[j]: return False
    if (fut(j)&~fut(i))!=0: return False
    if fut(i)==fut(j) and est[i]==est[j]: return i<j
    return est[i]<=est[j]

def check_state(ready,p,E,fut,est):
    v=min(est[i]+p[i] for i in ready)
    rk=[i for i in ready if est[i]<v]
    keep,drop,_=pace_v19.dcd_branch_set(rk,p,E,fut,est)
    # brute force: no RHD dominator and no DCD dominator
    bf=[]
    for j in ready:
        if any(est[i]+p[i]<=est[j] for i in ready if i!=j): continue
        if any(dom_dcd(i,j,p,E,fut,est) for i in ready if i!=j): continue
        bf.append(j)
    assert set(keep)==set(bf), (ready,pprint(keep),pprint(bf))
    assert keep
    return keep

def pprint(x): return sorted(x)

def main(N=30000,seed=3):
    rng=random.Random(seed); bad=0
    for t in range(N):
        n=rng.randint(1,11); m=rng.choice([2,3])
        p=[rng.randint(1,5) for _ in range(n)]
        E=[tuple(sorted(rng.sample(range(m),rng.randint(1,m)))) for _ in range(n)]
        # random DAG forward edges
        pred=[[] for _ in range(n)]
        for j in range(n):
            for i in range(j):
                if rng.random()<0.3: pred[j].append(i)
        inst=po.make_inst(p,m,pred,E)
        # random *normalized* est: build from a random partial schedule
        A=tuple(rng.randint(0,6) for _ in range(m))
        est=[rng.randint(0,8) for _ in range(n)]
        for i in range(n):
            mn=min(A[k] for k in E[i])
            if est[i]<mn: est[i]=mn
        rem=rng.randint(1,(1<<n)-1)
        ready=[i for i in range(n) if rem>>i&1 and all(not (rem>>j&1) for j in pred[i])]
        if not ready: continue
        fut=lambda x: inst['desc'][x]&rem
        try:
            check_state(ready,p,E,fut,est)
        except AssertionError as e:
            bad+=1; print('BAD',t,e); print(p,E,pred,est,rem,ready)
            if bad>=3: break
    print('states checked',N,'bad',bad)

def witness():
    # root done at 3; k sibling heads released at 3, private chains, distinct p
    k=6
    p=[3]+[3+2*i for i in range(k)]+[1]*k
    n=len(p); m=3
    pred=[[] for _ in range(n)]
    for i in range(k): pred[1+i]=[0]
    for i in range(k): pred[1+k+i]=[1+i]
    inst=po.make_inst(p,m,pred)
    rem=(1<<n)-1
    for i in [0]: rem&=~(1<<i)
    est=[0]*n
    for i in range(n):
        if rem>>i&1:
            # head i released at 3; chain successor at 3+p_head
            est[i]=3 if i<=k else 3+p[i-k]
    ready=[1+i for i in range(k)]
    fut=lambda x: inst['desc'][x]&rem
    keep=check_state(ready,p,inst['elig'],fut,est)
    print('witness k=%d d=%d rhd_keep=%d final_c=%d'%(k,len(ready),len([i for i in ready if est[i]<min(est[j]+p[j] for j in ready)]),len(keep)))

if __name__=='__main__':
    main()
    witness()
