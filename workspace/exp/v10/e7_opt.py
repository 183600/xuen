import sys, json, time
sys.path.insert(0,'exp/v10')
from profile import _canon
R=json.load(open('exp/v08/results.json'))

def profile_opt(p,m,U):
    idx=sorted(range(len(p)),key=lambda i:(-p[i],i))
    cur={(0,)*m}; tot=1
    for i in idx:
        s=p[i]; nxt=set()
        for r in cur:
            for k in range(m):
                t=list(r); t[k]+=s
                if max(t)<=U: nxt.add(tuple(sorted(t)))
        cur=nxt; tot+=len(cur)
        if not cur: return None,tot
    return min(max(r) for r in cur),tot

rows=[]
for fam in ('part2','part3'):
    for r in R[fam]:
        p=r['p']; m=r['m']
        b=[0]*m
        for s in sorted(p,reverse=True):
            k=min(range(m),key=lambda x:b[x]); b[k]+=s
        U=max(b)
        t=time.time(); opt,ns=profile_opt(p,m,U); dt=time.time()-t
        rows.append((fam,len(p),m,opt,r['OPT'],ns,round(dt,5)))
ok=sum(x[3]==x[4] for x in rows)
print('pure packing: profile-opt == OPT',ok,'/',len(rows),
      'max states',max(x[5] for x in rows),'max t',max(x[6] for x in rows))
for x in rows[:3]: print(x)
