import sys, random, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14')
import po, pace

def gen(rng,n,m,pmax=8,ep=0.3,elig_p=1.0):
    p=[rng.randint(1,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7: pred[j].append(rng.randrange(j))
    if elig_p>=1.0:
        elig=[list(range(m)) for _ in range(n)]
    else:
        elig=[]
        for i in range(n):
            e=[k for k in range(m) if rng.random()<elig_p]
            if not e: e=[rng.randrange(m)]
            elig.append(e)
    return po.make_inst(p,m,pred,elig)

def brute(inst,h):
    n=inst['n']; m=inst['m']; p=inst['p']; pred=inst['pred']
    order=sorted(range(n),key=lambda i:len(pred[i]))
    # enumerate all task orders/extensions with time
    best=[False]
    def rec(rem,A,est):
        if best[0]: return
        if rem==0: best[0]=True; return
        q=po.tails(inst,rem)
        for i in po.bititer(rem):
            if any((rem>>j)&1 for j in pred[i]): continue
            for k in inst['elig'][i]:
                t=max(A[k],est[i])
                if t+p[i]+q[i]>h: continue
                nA=list(A); nA[k]=t+p[i]
                nest=list(est)
                for j in inst['succ'][i]:
                    if (rem>>j)&1 and t+p[i]>nest[j]: nest[j]=t+p[i]
                rec(rem&~(1<<i),tuple(nA),tuple(nest))
                if best[0]: return
    est0,_=po.heads_tails(inst,0,[0]*n)
    rec(inst['full'],(0,)*m,tuple(est0))
    return best[0]

if __name__=='__main__':
    rng=random.Random(int(sys.argv[1]) if len(sys.argv)>1 else 1)
    bad=0; cnt=0; potclose=0; t0=time.time()
    for it in range(300):
        n=rng.randint(5,9); m=rng.choice([2,3])
        ep=rng.choice([0.15,0.3,0.5]); elig_p=rng.choice([1.0,0.7,0.5])
        inst=gen(rng,n,m,ep=ep,elig_p=elig_p)
        est,q=po.heads_tails(inst,0,[0]*n)
        lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),
               (sum(inst['p'])+m-1)//m, max(inst['p']))
        for h in range(lo, lo+6):
            b=brute(inst,h)
            (r1,_),s1=po.decide(inst,h,mode='sub',nodecap=200000)
            (r2,_),s2=pace.decide(inst,h,mode='pot',slack_cap=10**9)
            cnt+=1
            if r1!=b or r2!=b or s2.get('timeout'):
                bad+=1
                print('MISMATCH it',it,'n',n,'m',m,'h',h,'brute',b,'sub',r1,'pot',r2,
                      'ep',ep,'eligp',elig_p,flush=True)
                if bad>5: raise SystemExit
            if s2['pot_prunes']>0: potclose+=1
    print('done cases',cnt,'mismatch',bad,'pot-prune cases',potclose,'time',round(time.time()-t0,1))
