import sys, random, time, json
sys.path.insert(0,'exp/v13')
import po

def check_sched(inst,h,sched):
    n,m,p=inst['n'],inst['m'],inst['p']
    A=[0]*m; est=[0]*n; done=[False]*n
    # sched is in decision order
    for (i,k,t) in sched:
        assert 0<=i<n and 0<=k<m, 'range'
        assert not done[i], 'dup'
        assert k in inst['elig'][i], 'elig'
        assert t>=A[k], 'machine'
        if t<est[i]: return False,'est',(i,k,t,est[i])
        if t+p[i]+inst['q'][i]>h if 'q' in inst else False: pass
        A[k]=t+p[i]; done[i]=True
        for j in inst['succ'][i]:
            if not done[j]: est[j]=max(est[j],t+p[i])
    if not all(done): return False,'missing',None
    return True,None,None

def verify_witnesses(inst,h,sched):
    """independent: recompute q and check deadline."""
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q=po.heads_tails(inst,0,[0]*n)
    A=[0]*m; est=[0]*n; done=[False]*n
    for (i,k,t) in sched:
        if k not in inst['elig'][i]: return 'elig'
        if t<max(A[k],est[i]): return 'machine/est'
        if t+p[i]+q[i]>h: return 'deadline'
        A[k]=t+p[i]; done[i]=True
        for j in inst['succ'][i]:
            if not done[j]: est[j]=max(est[j],t+p[i])
    return None if all(done) else 'missing'

def rand_inst(rng,n,m,pmax=8,ep=0.2,elig_p=0.75):
    p=[rng.randint(1,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
    elig=[]
    for i in range(n):
        e=[k for k in range(m) if rng.random()<elig_p]
        if not e: e=[rng.randrange(m)]
        elig.append(e)
    return po.make_inst(p,m,pred,elig)

if __name__=='__main__':
    rng=random.Random(7)
    MODES=['plain','canon','front','sub','ladder_front']
    bad=0; tot=0; wit_bad=0
    t0=time.time()
    for trial in range(400):
        n=rng.randint(5,9); m=rng.choice([2,3])
        inst=rand_inst(rng,n,m)
        est,q=po.heads_tails(inst,0,[0]*n)
        lb=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),max(inst['p']))
        h=rng.randint(lb, lb+6)
        ans={}
        for mode in MODES:
            (ok,sched),st=po.decide(inst,h,mode=mode,nodecap=300000)
            ans[mode]=ok
            if ok and sched is not None:
                err=verify_witnesses(inst,h,sched)
                if err: wit_bad+=1; print('WITNESS',mode,err,inst,h,sched)
        tot+=1
        if len(set(ans.values()))!=1:
            bad+=1
            print('MISMATCH',trial,n,m,h,ans,inst['p'],inst['pred'],inst['elig'])
            if bad>3: break
        if not ans['plain'] and h>lb:
            # check a smaller deadline must also be NO (monotonicity sanity)
            (ok2,_),_=po.decide(inst,h-1,mode='plain',nodecap=300000)
            if ok2: print('MONO FAIL',h,inst['p'])
    print('trials',tot,'mismatch',bad,'witness_bad',wit_bad,'t',round(time.time()-t0,2))
