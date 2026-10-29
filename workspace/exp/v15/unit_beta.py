import sys, random
sys.path.insert(0,'exp/v15')
import mint
rng=random.Random(5)
bad=0
for it in range(20000):
    n=rng.randint(1,8); h=rng.randint(5,40)
    ps=[rng.randint(1,10) for _ in range(n)]
    r=[rng.randint(0,h) for _ in range(n)]
    d=[r[i]+ps[i]+rng.randint(0,max(0,h-(r[i]+ps[i]))) for i in range(n)]
    # random union of 1..3 disjoint intervals
    k=rng.randint(1,3)
    cuts=sorted(rng.sample(range(0,h+1),min(2*k,h+1)))
    S=[]
    for j in range(0,len(cuts)-1,2):
        if cuts[j+1]>cuts[j]: S.append((cuts[j],cuts[j+1]))
    if not S: continue
    for i in range(n):
        b1=mint.beta(i,ps,r,d,S)
        b2=min(sum(max(0,min(s+ps[i],bb)-max(s,aa)) for aa,bb in S)
               for s in range(r[i],d[i]-ps[i]+1))
        if b1!=b2:
            bad+=1
            if bad<5: print('BAD',i,ps[i],r[i],d[i],S,b1,b2)
print('beta cases 20000 bad',bad)
