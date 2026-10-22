import sys, random, time
sys.path.insert(0,'exp/v14')
import sp
rng=random.Random(9)
tot=0; bad=0
for trial in range(3000):
    n=rng.randint(4,10); m=rng.choice([2,3])
    p=[rng.randint(1,8) for _ in range(n)]
    elig=[]
    for i in range(n):
        e=[k for k in range(m) if rng.random()<0.7]
        if not e: e=[rng.randrange(m)]
        elig.append(e)
    inst=sp.make_inst(p,m,[[] for _ in range(n)],elig)
    rem=inst['full']
    for _ in range(6):
        A=tuple(rng.randint(0,12) for _ in range(m)); est=tuple(rng.randint(0,12) for _ in range(n)); h=rng.randint(8,30)
        q=sp.tails(inst,rem)
        a,used=sp.pack_check(inst,rem,A,est,q,h)
        b=sp.pack_exact(inst,rem,A,est,q,h)
        tot+=1
        if a!=b:
            bad+=1
            if bad<5: print('MISMATCH',n,m,p,elig,A,est,h,'check',a,used,'exact',b)
print('states',tot,'mismatch',bad)
