import sys, json, random, time
from fractions import Fraction as F
sys.path.insert(0,'.'); sys.path.insert(0,'v09')
from lp import frac_pack
from cert import bb_pack, check_schedule

def exact_check(sizes,m,C,w,tol_den=120):
    n=len(sizes)
    wr=[F(x).limit_denominator(tol_den) for x in w]
    if any(x<0 for x in wr): return False,'neg'
    if sum(wr)<=m: return False,'sum %s <= %d'%(sum(wr),m)
    for k in range(m):
        dp=[F(0)]*(C+1)
        for i in range(n):
            s=sizes[i]
            if s>C: continue
            for c in range(C,s-1,-1):
                if dp[c-s]+wr[i]>dp[c]: dp[c]=dp[c-s]+wr[i]
        if max(dp)>1: return False,'machine %d max %s'%(k,max(dp))
    return True,'ok %s'%([str(x) for x in wr][:6])

rows=json.load(open('study.json'))
rng=random.Random(9)
acc=0; exact_ok=0; rej=0; tot=0; times=[]
for r in rows:
    if r['fam'] not in ('part2','part3'): continue
    p=r['p']; m=r['m']; n=r['n']; U=r['OPT']
    bins=bb_pack(p,m,U); assert check_schedule(bins,p,m,U)[0]
    tau,w,info=frac_pack(p,[U-1]*m)
    ok,msg=exact_check(p,m,U-1,w)
    acc+=1; exact_ok+=ok
    if not ok: print('EXACT FAIL',r['fam'],r['k'],msg)
    assert check_schedule(bins,p,m,U)[0]
    # deliberate corruptions: overload or coverage
    for _ in range(10):
        b2=[x[:] for x in bins]
        i=rng.randrange(n); src=next(k for k in range(m) if i in b2[k])
        dst=next((k for k in range(m) if k!=src and sum(p[j] for j in b2[k])+p[i]>U), None)
        if dst is None:
            # coverage corruption: drop item
            b2[src].remove(i)
        else:
            b2[src].remove(i); b2[dst].append(i)
        o,_=check_schedule(b2,p,m,U); tot+=1; rej+=(not o)
    t0=time.time(); exact_check(p,m,U-1,w); times.append(time.time()-t0)
print('certs',acc,'exact rational witness ok',exact_ok)
print('corruptions rejected',rej,'/',tot)
print('exact check time med %.5fs max %.5fs'%(sorted(times)[len(times)//2],max(times)))
