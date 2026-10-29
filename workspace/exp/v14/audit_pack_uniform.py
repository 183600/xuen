import sys, random, time
sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v13')
import sp, po
rng=random.Random(31337)
tot=0; bad=0
for trial in range(5000):
    n=rng.randint(4,10); m=rng.choice([2,3])
    p=[rng.randint(1,10) for _ in range(n)]
    inst=sp.make_inst(p,m,[[] for _ in range(n)],[[k for k in range(m)] for _ in range(n)])
    rem=inst['full']
    for _ in range(10):
        A=tuple(rng.randint(0,20) for _ in range(m)); est=tuple(rng.randint(0,20) for _ in range(n)); h=rng.randint(8,35)
        q=sp.tails(inst,rem)
        b=po.pack_exact(inst,rem,A,est,q,h); f=sp.pack_exact(inst,rem,A,est,q,h)
        tot+=1
        if b!=f:
            if (not b) and f: bad+=1
print('uniform states',tot,'buggy_false_fixed_true',bad)
