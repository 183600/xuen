import sys, random, math, time, json
sys.path.insert(0,'exp/v10')
from lp import frac_pack

def opt_dp(sizes,m):
    states={(0,)*m}
    for s in sizes:
        ns=set()
        for L in states:
            for k in range(m):
                t=list(L); t[k]+=s
                if t[k]<=max(t): pass
                ns.add(tuple(sorted(t)))
        states=ns
    return min(max(L) for L in states)

def feas_dp(sizes,m,C):
    if sum(sizes)>m*C or max(sizes)>C: return False
    states={(0,)*m}
    for s in sizes:
        ns=set()
        for L in states:
            for k in range(m):
                if L[k]+s<=C:
                    t=list(L); t[k]+=s; ns.add(tuple(sorted(t)))
        states=ns
        if not states: return False
    return True

rng=random.Random(2026); t0=time.time(); gaps=[]; tried=0
for tr in range(30000):
    m=3; H=rng.randint(8,18)
    n=rng.randint(5,10)
    sizes=[rng.randint(2,H-1) for _ in range(n)]
    if sum(sizes)>m*(H+2): continue
    OPT=opt_dp(sizes,m)
    if OPT<=H: continue
    tried+=1
    tau,w,info=frac_pack(sizes,[H]*m)
    if tau<=m+1e-7:
        gaps.append(dict(H=H,sizes=sizes,OPT=OPT,tau=tau))
        print('GAP H',H,'p',sizes,'OPT',OPT,'tau',round(tau,4),flush=True)
        if len(gaps)>=10: break
print('tried',tried,'gaps',len(gaps),'time',round(time.time()-t0,1))
json.dump(gaps,open('exp/v10/gaps.json','w'),indent=1)
