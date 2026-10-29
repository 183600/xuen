import sys, random, time
sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v13')
import sp, po
rng=random.Random(4242)
tot=0; bad=0; rev=0; t0=time.time()
for trial in range(4000):
    n=rng.randint(4,9); m=rng.choice([2,3])
    p=[rng.randint(1,8) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<0.2: pred[j].append(i)
    elig=[]
    for i in range(n):
        e=[k for k in range(m) if rng.random()<0.7]
        if not e: e=[rng.randrange(m)]
        elig.append(e)
    inst=sp.make_inst(p,m,pred,elig)
    rem=inst['full']
    for _ in range(8):
        A=tuple(rng.randint(0,12) for _ in range(m))
        est=tuple(rng.randint(0,12) for _ in range(n))
        h=rng.randint(8,30)
        q=sp.tails(inst,rem)
        # buggy v1.2 table
        b=po.pack_exact(inst,rem,A,est,q,h)
        f=sp.pack_exact(inst,rem,A,est,q,h)
        tot+=1
        if b!=f:
            if (not b) and f: bad+=1
            else: rev+=1
print('states',tot,'buggy_false_fixed_true',bad,'other',rev,'time',round(time.time()-t0,2))
