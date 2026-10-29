import sys, random
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15')
import po, pace_i

def brute_beta(ps,r,d,S):
    return min(sum(max(0,min(s+ps,bb)-max(s,aa)) for aa,bb in S)
               for s in range(r,d-ps+1))

def rand_state(rng,n,m):
    p=[rng.randint(1,8) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<0.25: pred[j].append(i)
    elig=[[k for k in range(m) if rng.random()<0.8] or [rng.randrange(m)] for _ in range(n)]
    inst=po.make_inst(p,m,pred,elig)
    est,q=po.heads_tails(inst,0,[0]*n)
    # random partial schedule
    rem=inst['full']; A=[0]*m; est=list(est)
    while rem and rng.random()<0.5:
        ready=[i for i in po.bititer(rem) if not (inst['pmask'][i]&rem)]
        i=rng.choice(ready); k=rng.choice(inst['elig'][i])
        t=max(A[k],est[i]); A[k]=t+p[i]
        for j in inst['succ'][i]:
            if (rem>>j)&1 and t+p[i]>est[j]: est[j]=t+p[i]
        rem&=~(1<<i)
    return inst,rem,tuple(A),tuple(est),q

rng=random.Random(9); fired=0; bad=0; checked=0
for it in range(4000):
    inst,rem,A,est,q=rand_state(rng,rng.randint(5,9),rng.choice([2,3]))
    n=inst['n']
    if rem==0: continue
    for h in range(5,45):
        tasks=list(po.bititer(rem))
        if any(est[i]+inst['p'][i]+q[i]>h for i in tasks): continue
        checked+=1
        ok,phi,w=pace_i.potential(inst,rem,A,est,q,h,mint_on=True,mint_tau=5,
                                  packset_on=False)
        if (not ok) and w and w[0]=='mint':
            fired+=1
            _,S,W,cap=w
            S=sorted(S)
            if not all(S[j][1]<=S[j+1][0] for j in range(len(S)-1)):
                bad+=1; print('overlap',S); continue
            W2=0
            for i in tasks:
                W2+=brute_beta(inst['p'][i],est[i],h-q[i],S)
            cap2=0
            for a,b in S:
                for k in range(inst['m']):
                    if b>max(a,A[k]): cap2+=b-max(a,A[k])
            if not (W2==W and cap2==cap and W2>cap):
                bad+=1
                if bad<5: print('BAD',n,h,S,W,cap,W2,cap2)
print('checked states',checked,'mint fired',fired,'bad',bad)
