"""Unit test: dcd_branch_set == brute-force maximal elements of the preorder."""
import sys, random
sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v19')
from pace_v18 import dcd_branch_set

def brute(ready,p,elig,fut,est):
    keep=[]
    for i in ready:
        di=fut(i)
        dom=False
        for j in ready:
            if j==i: continue
            if p[j]!=p[i] or elig[j]!=elig[i]: continue
            dj=fut(j)
            if (di & ~dj)!=0: continue          # D_i not subset D_j
            if est[j]>est[i]: continue
            # strict in the preorder (tie-break by index when D and est equal)
            if dj==di and est[j]==est[i] and j>i: continue
            dom=True; break
        if not dom: keep.append(i)
    return set(keep)

rng=random.Random(99)
for t in range(20000):
    d=rng.randint(1,6)
    ready=list(range(d))
    p=[rng.choice([2,3,4]) for _ in range(d)]
    elig=[tuple(rng.choice([(0,1),(0,1,2),(1,2)])) for _ in range(d)]
    # random nested-ish bitmasks over 5 future slots
    futm=[rng.randrange(1<<5) for _ in range(d)]
    est=[rng.choice([0,0,1,2]) for _ in range(d)]
    fut=lambda i: futm[i]
    keep,drop,_=dcd_branch_set(ready,p,elig,fut,est)
    b=brute(ready,p,elig,fut,est)
    if set(keep)!=b:
        print('FAIL',t); print('p',p); print('elig',elig); print('fut',[bin(x) for x in futm]); print('est',est)
        print('skyline',keep,'brute',b); sys.exit(1)
print('skyline unit test: 20000/20000 ok')
# explicit eviction case: same est, D1 subset D2, index 1 before 2
p=[2,2]; elig=[(0,1),(0,1)]; futm=[0b01,0b11]; est=[0,0]
keep,drop,_=dcd_branch_set([0,1],p,elig,lambda i:futm[i],est)
assert keep==[1] and drop=={0},(keep,drop)
print('eviction case ok:',keep,drop)
