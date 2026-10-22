import sys, itertools, json
sys.path.insert(0,'.'); sys.path.insert(0,'v09')
from lp import frac_pack

def ip_feasible(sizes,m,C):
    sizes=sorted(sizes,reverse=True); bins=[0]*m
    def dfs(i):
        if i==len(sizes): return True
        s=sizes[i]; seen=set()
        for k in range(m):
            if bins[k]+s<=C and bins[k] not in seen:
                seen.add(bins[k]); bins[k]+=s
                if dfs(i+1): return True
                bins[k]-=s
        return False
    return dfs(0)

found=[]
for C in (8,9,10,12):
    for m in (2,3,4):
        for n in range(5,9):
            for sizes in itertools.combinations_with_replacement(range(1,C+1), n):
                if sum(sizes)>m*C: continue
                if ip_feasible(sizes,m,C): continue
                tau,w,info=frac_pack(list(sizes),[C]*m)
                if tau<=m+1e-9:
                    found.append(dict(C=C,m=m,sizes=list(sizes),tau=tau))
                    print('FOUND',C,m,sizes,float(tau),flush=True)
                    if len(found)>=10: break
            if len(found)>=10: break
        if len(found)>=10: break
    if len(found)>=10: break
print('total',len(found))
json.dump(found,open('brute_gaps.json','w'),indent=1)
