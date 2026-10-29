import sys, json, random, math, time
sys.path.insert(0,'.'); sys.path.insert(0,'v09')
from lp import frac_pack

def feasible(sizes,m,C):
    sizes=sorted(sizes,reverse=True)
    bins=[0]*m
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
    # LPT ub
    b=[0]*m
    for s in sorted(sizes,reverse=True):
        k=min(range(m), key=lambda x:b[x]); b[k]+=s
    hi=max(b)
    for C in range(lo,hi):
        if feasible(sizes,m,C): return C
    return hi

def dff(sizes,m):
    best=0
    for t in range(1,max(sizes)+1):
        c=sum(s//t for s in sizes)
        best=max(best,t*((c+m-1)//m))
    return best

rng=random.Random(7)
rows=[]
for trial in range(80):
    m=rng.choice([2,3,4])
    n=rng.randint(9,14)
    maxp=rng.choice([7,9,12])
    sizes=[rng.randint(1,maxp) for _ in range(n)]
    OPT=bin_opt(sizes,m)
    H=OPT-1
    tau,w,info=frac_pack(sizes,[H]*m)
    rows.append(dict(trial=trial,m=m,n=n,sizes=sizes,OPT=OPT,H=H,total=sum(sizes),
                     slack=m*H-sum(sizes),tau=tau,lp_no=(tau>m+1e-9),
                     dff=dff(sizes,m),L0=max(max(sizes),math.ceil(sum(sizes)/m))))
json.dump(rows,open('random.json','w'),indent=1)

def summ(rs,label):
    print(label,len(rs),'LP-NO',sum(r['lp_no'] for r in rs),
          'DFF>=OPT',sum(r['dff']>=r['OPT'] for r in rs))
summ(rows,'all')
for sl in ('0','>0'):
    rs=[r for r in rows if (r['slack']==0)==(sl=='0')]
    summ(rs,'slack='+sl)
print('by m:')
for m in (2,3,4):
    rs=[r for r in rows if r['m']==m]; summ(rs,' m=%d'%m)
print('slack==0 rows:')
for r in rows:
    if r['slack']==0: print(' ',r['m'],r['n'],r['OPT'],'tau',round(r['tau'],3),'lpn',r['lp_no'])
print('LP feasible but integer NO (true gap) examples:')
c=0
for r in rows:
    if not r['lp_no']:
        print(' ','m',r['m'],'n',r['n'],'OPT',r['OPT'],'H',r['H'],'slack',r['slack'],'tau',round(r['tau'],3),'p',r['sizes']); c+=1
        if c>=8: break
