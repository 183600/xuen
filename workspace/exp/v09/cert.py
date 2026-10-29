import sys, json, random, time
sys.path.insert(0,'.'); sys.path.insert(0,'v09')
from lp import frac_pack, check_witness

def bb_pack(sizes,m,C):
    order=sorted(range(len(sizes)),key=lambda i:-sizes[i])
    bins=[[] for _ in range(m)]; loads=[0]*m
    def dfs(t):
        if t==len(order): return True
        i=order[t]; s=sizes[i]; seen=set()
        for k in range(m):
            if loads[k]+s<=C and loads[k] not in seen:
                seen.add(loads[k]); loads[k]+=s; bins[k].append(i)
                if dfs(t+1): return True
                bins[k].pop(); loads[k]-=s
        return False
    return bins if dfs(0) else None

def check_schedule(bins,p,m,U):
    seen=[0]*len(p)
    for k,bl in enumerate(bins):
        load=sum(p[i] for i in bl)
        if load>U: return False,'machine %d overload %d>%d'%(k,load,U)
        for i in bl:
            seen[i]+=1
    if any(c!=1 for c in seen): return False,'coverage'
    return True,'ok'

rows=json.load(open('study.json'))
rng=random.Random(5)
acc=0; rej_sched=0; rej_w=0; tot_sched=0; tot_w=0; cert_times=[]
for r in rows:
    if r['fam'] not in ('part2','part3'): continue
    p=r['p']; m=r['m']; n=r['n']; U=r['OPT']
    bins=bb_pack(p,m,U)
    ok,msg=check_schedule(bins,p,m,U)
    assert ok,(r['fam'],r['k'],msg)
    tau,w,info=frac_pack(p,[U-1]*m)
    ok2,msg2=check_witness(p,[U-1]*m,[set(range(n)) for _ in range(m)],w,m)
    assert ok2,(r['fam'],r['k'],msg2)
    acc+=1
    t0=time.time()
    check_schedule(bins,p,m,U); check_witness(p,[U-1]*m,[set(range(n)) for _ in range(m)],w,m)
    cert_times.append(time.time()-t0)
    # mutate schedule: move a random item to another machine (may overflow)
    for _ in range(10):
        b2=[x[:] for x in bins]
        i=rng.randrange(n); src=next(k for k in range(m) if i in b2[k])
        dst=rng.randrange(m)
        if dst==src: dst=(dst+1)%m
        b2[src].remove(i); b2[dst].append(i)
        o,_=check_schedule(b2,p,m,U); tot_sched+=1; rej_sched+=(not o)
    for _ in range(10):
        w2=w[:]; w2[rng.randrange(n)]+=0.02
        o,_=check_witness(p,[U-1]*m,[set(range(n)) for _ in range(m)],w2,m)
        tot_w+=1; rej_w+=(not o)
print('certificates accepted',acc)
print('schedule mutations rejected',rej_sched,'/',tot_sched)
print('weight mutations rejected',rej_w,'/',tot_w)
print('check time med %.6fs max %.6fs'%(sorted(cert_times)[len(cert_times)//2],max(cert_times)))
