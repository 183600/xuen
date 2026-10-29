import sys, json, random, time
sys.path.insert(0,'.'); sys.path.insert(0,'v09')
from lp import frac_pack, check_witness
rows=json.load(open('study.json'))
print('hierarchy violations DFF>CFG:',sum(1 for r in rows if r['LDFF']>r['LCFG']))
print('CFG>PACK:',sum(1 for r in rows if r['LCFG']>r['LPACK']))
print('PACK>OPT:',sum(1 for r in rows if r['LPACK']>r['OPT']))
for fam in ('part2','part3'):
    rs=[r for r in rows if r['fam']==fam and r['LCFG']>=r['OPT']]
    print(fam,'n',len(rs),'excess tau-m:',[round(r['tau']-r['m'],3) for r in rs])
    print('   support/n:',sorted(round(r['supp']/r['n'],2) for r in rs))
# tight configs + witness checker cost
from lp import _subsets_fitting
def tight_count(sizes,caps,w):
    n=len(sizes); cnt=0; best=0
    # DP over weight, count configs attaining max weight for each capacity
    caps=max(caps)
    dp=[0.0]*(caps+1)
    for s in sizes:
        for c in range(caps,s-1,-1):
            dp[c]=max(dp[c],dp[c-s]+w[sizes.index(s)] if False else dp[c])
    # brute force small n
    for mask in range(1,1<<n):
        ss=sum(sizes[i] for i in range(n) if (mask>>i)&1)
        if ss<=caps:
            val=sum(w[i] for i in range(n) if (mask>>i)&1)
            if val>best: best=val; cnt=1
            elif abs(val-best)<1e-12: cnt+=1
    return best,cnt
rng=random.Random(3)
mut_tot=mut_rej=0; rnd_rej=0; rnd_tot=0
for r in rows:
    if not (r['LCFG']>=r['OPT'] and r['L0']<r['OPT']): continue
    p=r['p']; m=r['m']; n=r['n']; H=r['OPT']-1
    tau,w,info=frac_pack(p,[H]*m)
    ok,msg=check_witness(p,[H]*m,[set(range(n)) for _ in range(m)],w,m)
    assert ok, (r['fam'],r['k'],msg)
    # tight configs
    best,cnt=tight_count(p,[H]*m,w)
    # mutation: increase one weight
    for _ in range(10):
        i=rng.randrange(n); wm=w[:]; wm[i]+=0.03
        o,_=check_witness(p,[H]*m,[set(range(n)) for _ in range(m)],wm,m)
        mut_tot+=1; mut_rej+= (not o)
    for _ in range(10):
        wm=[rng.random()*1.5 for _ in range(n)]
        if sum(wm)<=m: wm=[x+0.2 for x in wm]
        o,_=check_witness(p,[H]*m,[set(range(n)) for _ in range(m)],wm,m)
        rnd_tot+=1; rnd_rej+= (not o)
    print(r['fam'],r['k'],'tau',round(tau,3),'m',m,'support',r['supp'],'tight',best,round(cnt,1))
print('mutations rejected',mut_rej,'/',mut_tot)
print('random vectors rejected',rnd_rej,'/',rnd_tot)
