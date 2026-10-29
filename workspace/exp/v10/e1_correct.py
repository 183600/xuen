import sys, random, json, time
sys.path.insert(0,'exp/v10'); sys.path.insert(0,'exp/v08'); sys.path.insert(0,'exp/v07'); sys.path.insert(0,'exp')
import exp_da as E, ip
from profile import profile_dec

rng=random.Random(1); bad=0; tested=0
for tr in range(3000):
    m=rng.choice([2,3,4]); n=rng.randint(3,10); H=rng.randint(4,30)
    p=[rng.randint(1,H) for _ in range(n)]
    ok1,_,_=profile_dec(p,[H]*m)
    # independent: exact DFS assignment (m^n) with pruning
    sizes=sorted(p,reverse=True); bins=[0]*m
    def dfs(i):
        if i==len(sizes): return True
        s=sizes[i]; seen=set()
        for k in range(m):
            if bins[k]+s<=H and bins[k] not in seen:
                seen.add(bins[k]); bins[k]+=s
                if dfs(i+1): return True
                bins[k]-=s
        return False
    ok2=dfs(0); tested+=1
    if ok1!=ok2:
        bad+=1; print('MISMATCH',m,H,p,ok1,ok2)
print('tested',tested,'mismatch',bad)
