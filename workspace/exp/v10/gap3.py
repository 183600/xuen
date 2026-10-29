import sys, itertools, math, time, json
sys.path.insert(0,'exp/v10')
from lp import frac_pack

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

def opt_bin(sizes,m):
    lo=max(max(sizes),math.ceil(sum(sizes)/m))
    b=[0]*m
    for s in sorted(sizes,reverse=True):
        k=min(range(m),key=lambda x:b[x]); b[k]+=s
    for C in range(lo,max(b)+1):
        if feas_dp(sizes,m,C): return C
    return max(b)

H=10; m=3; t0=time.time(); found=[]; cnt=0; infl=0
for n in (8,9):
    for p in itertools.combinations_with_replacement(range(1,H+1),n):
        if sum(p)>m*H: continue
        if feas_dp(list(p),m,H): continue
        cnt+=1
        tau,w,_=frac_pack(list(p),[H]*m)
        if tau<=m+1e-7:
            found.append((p,opt_bin(list(p),m),tau)); print('GAP',p,'OPT',opt_bin(list(p),m),'tau',round(tau,4),flush=True)
    print('n',n,'infeasible',cnt,'found',len(found),'t',round(time.time()-t0,1),flush=True)
json.dump([(list(p),o,t) for p,o,t in found],open('exp/v10/gapsH10.json','w'))
