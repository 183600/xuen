import sys, random, json, pickle
sys.path.insert(0,'exp/v10'); sys.path.insert(0,'exp/v08'); sys.path.insert(0,'exp/v07'); sys.path.insert(0,'exp')
import exp_da as E, ip
from profile import profile_dec_elig
R=json.load(open('exp/v08/results.json')); pool=pickle.load(open('exp/pool30.pkl','rb'))
rng=random.Random(17); bad=0; tot=0
for tr in range(500):
    inst=pool[rng.randrange(len(pool))][0]; n=inst['n']; m=inst['m']
    # random partial state: take a random prefix-like S by ordering
    S=0; A=[0]*m; c=[-1]*n
    order=list(range(n)); rng.shuffle(order)
    for i in order[:rng.randint(0,n-1)]:
        if all(j in [x for x in order[:order.index(i)] ] for j in inst['pred'][i]):
            k=rng.randrange(m); st=max(A[k],0); S|=1<<i; A[k]=st+inst['p'][i]; c[i]=st
    A=tuple(A)
    est,q=E.heads_tails(inst,S,c)
    H=max(A)+rng.randint(0,6)
    elig=[[k for k in range(m) if max(A[k],est[i])+inst['p'][i]+q[i]<=H] for i in range(n)]
    rem=[i for i in range(n) if not (S>>i)&1]
    caps=[H-A[k] for k in range(m)]
    blocks=[]
    vals=sorted(set(A))
    lo=0
    for v in vals:
        cnt=sum(1 for a in A if a==v); blocks.append((lo,lo+cnt)); lo+=cnt
    ok1,_=profile_dec_elig([inst['p'][i] for i in rem],caps,[elig[i] for i in rem],A,blocks)
    ok2=ip.pack_feas(inst,S,A,c,H)
    tot+=1
    if ok1!=ok2:
        bad+=1; print('MISMATCH',n,m,H,A,ok1,ok2)
print('tested',tot,'mismatch',bad)
