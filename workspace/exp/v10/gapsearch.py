import sys, random, math, time, json
sys.path.insert(0,'exp/v10')
from lp import frac_pack

def feasible(sizes,m,C):
    if not sizes: return True
    if sum(sizes)>m*C or max(sizes)>C: return False
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

def bin_opt(sizes,m):
    lo=max(max(sizes), math.ceil(sum(sizes)/m))
    b=[0]*m
    for s in sorted(sizes,reverse=True):
        k=min(range(m),key=lambda x:b[x]); b[k]+=s
    hi=max(b)
    for C in range(lo,hi+1):
        if feasible(sizes,m,C): return C
    return hi

if __name__=='__main__':
    rng=random.Random(7); t0=time.time(); gaps=[]; tries=0; hard=0
    for tr in range(6000):
        m=3; H=rng.choice([15,16,18,20,21,24,25,27,30])
        lo=H//4+1; hi=H//2-1
        if hi<=lo: continue
        n=3*m + rng.choice([0,0,0,1,2])
        sizes=[rng.randint(lo,hi) for _ in range(n)]
        while sum(sizes) > m*H:
            i=rng.randrange(n)
            if sizes[i]>lo: sizes[i]-=1
        if sum(sizes) < m*H - 2: continue
        tries+=1
        if feasible(sizes,m,H): continue
        hard+=1
        for h in range(H, max(max(sizes),math.ceil(sum(sizes)/m))-1, -1):
            tau,w,_=frac_pack(sizes,[h]*m)
            if tau<=m+1e-7:
                gaps.append(dict(H=h,sizes=sizes,OPT=bin_opt(sizes,m),tau=tau)); print('GAP',h,sizes,'OPT',bin_opt(sizes,m),'tau',round(tau,4),flush=True)
                break
        if len(gaps)>=8: break
    print('tries',tries,'hard',hard,'gaps',len(gaps),'time',round(time.time()-t0,1))
    json.dump(gaps,open('exp/v10/gaps.json','w'),indent=1)
