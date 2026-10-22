import sys, random, time, json, itertools
sys.path.insert(0,'v13'); sys.path.insert(0,'v11')
import po, plib

def brute(inst,h,cap=[0]):
    n,m,p=inst['n'],inst['m'],inst['p']
    full=inst['full']; cap[0]+=1
    if cap[0]>2_000_000: raise TimeoutError
    def rec(rem,A,est):
        if rem==0: return True
        q=po.tails(inst,rem)
        ready=[i for i in po.bititer(rem) if not (inst['pmask'][i]&rem)]
        for i in ready:
            if est[i]+p[i]+q[i]>h: continue
            for k in inst['elig'][i]:
                t=max(A[k],est[i])
                if t+p[i]+q[i]>h: continue
                nA=list(A); nA[k]=t+p[i]
                nest=list(est)
                for j in inst['succ'][i]:
                    if (rem>>j)&1 and t+p[i]>nest[j]: nest[j]=t+p[i]
                if rec(rem&~(1<<i),tuple(nA),tuple(nest)): return True
        return False
    est0,_=po.heads_tails(inst,0,[0]*n)
    return rec(full,(0,)*m,tuple(est0))

def rand_inst(rng,n,m):
    p=[rng.randint(1,7) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<0.2: pred[j].append(i)
    elig=[]
    for i in range(n):
        e=[k for k in range(m) if rng.random()<0.8]
        if not e: e=[rng.randrange(m)]
        elig.append(e)
    return po.make_inst(p,m,pred,elig)

if __name__=='__main__':
    rng=random.Random(11)
    bad=0; tot=0
    for trial in range(250):
        n=rng.randint(4,7); m=rng.choice([2,3])
        inst=rand_inst(rng,n,m)
        est,q=po.heads_tails(inst,0,[0]*n)
        lb=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),max(inst['p']))
        h=rng.randint(lb,lb+5)
        b=brute(inst,h)
        for mode in ['plain','sub','ladder_front']:
            (ok,_),st=po.decide(inst,h,mode=mode,nodecap=500000)
            tot+=1
            if ok!=b:
                bad+=1; print('BRUTE MISMATCH',mode,n,m,h,ok,b,inst['p'],inst['pred'])
                if bad>5: sys.exit()
    print('brute checks',tot,'mismatch',bad)

    # profile-layer dominance is vacuous: same layer => same total load
    rng=random.Random(5); pairs=0; layers=0; states=0
    for trial in range(60):
        m=rng.choice([2,3]); n=rng.randint(6,9); H=rng.randint(10,18)
        p=[rng.randint(1,8) for _ in range(n)]
        ok,layers_,ns=plib.profile_base(p,[H]*m,want_layers=True)
        for L in layers_:
            states+=len(L)
            Ls=list(L)
            for a in range(len(Ls)):
                for b in range(a+1,len(Ls)):
                    x,y=Ls[a],Ls[b]
                    if all(u<=v for u,v in zip(x,y)) or all(v<=u for u,v in zip(x,y)):
                        pairs+=1
            layers+=1
    print('profile layers',layers,'states',states,'comparable pairs',pairs)
