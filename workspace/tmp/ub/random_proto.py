import sys,time,random,collections,math
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from po import heads_tails
from rdf import check_schedule

def sched_order(inst, order):
    n=inst['n']; m=inst['m']; p=inst['p']; elig=inst['elig']
    starts=[0]*n; mach=[-1]*n; busy=[[] for _ in range(m)]
    for i in order:
        base=0
        for j in inst['pred'][i]: base=max(base,starts[j]+p[j])
        best=None
        for k in elig[i]:
            t=base
            for a,b in busy[k]:
                if t+p[i]<=a: break
                if t<b: t=b
            if best is None or (t+p[i],t,k)<best: best=(t+p[i],t,k)
        ft,t,k=best
        starts[i]=t; mach[i]=k; busy[k].append((t,ft)); busy[k].sort()
    c=max(starts[i]+p[i] for i in range(n))
    return starts,mach,c

def topo(inst):
    n=inst['n']; indeg=[len(inst['pred'][i]) for i in range(n)]
    q=[i for i in range(n) if indeg[i]==0]; out=[]
    while q:
        i=q.pop(); out.append(i)
        for j in inst['succ'][i]:
            indeg[j]-=1
            if indeg[j]==0:q.append(j)
    return out

def random_search(inst, U0, s0,m0, known=None, iters=2000, seed=0):
    rng=random.Random(seed+999)
    n=inst['n']; est,q=heads_tails(inst,0,[0]*n)
    best=U0; bs=list(s0); bm=list(m0)
    t0=time.time()
    for it in range(iters):
        # random priority key among eligible
        indeg=[len(inst['pred'][i]) for i in range(n)]
        ready=[i for i in range(n) if indeg[i]==0]
        order=[]
        mode=it%4
        while ready:
            # choose biased by tail/p/est/noise
            if mode==0: key=lambda i:(-(q[i]+rng.random()*5),)
            elif mode==1: key=lambda i:(-(q[i]+inst['p'][i]*0.5+rng.random()*8),)
            elif mode==2: key=lambda i:(rng.random(),)
            else: key=lambda i:(est[i]-q[i]*0.3+rng.random()*6,)
            ready.sort(key=key)
            # pick among top 2
            idx=0 if rng.random()<0.7 or len(ready)==1 else 1
            i=ready.pop(idx); order.append(i)
            for j in inst['succ'][i]:
                indeg[j]-=1
                if indeg[j]==0: ready.append(j)
        s,m,c=sched_order(inst,order)
        if c<best and check_schedule(inst,c,s,m):
            best=c; bs,bm=s,m
            if best<=known: break
    return best,bs,bm,dict(t=round(time.time()-t0,3),iters=it+1)

if __name__=='__main__':
    rows=weak_rows(4)
    print('rows',len(rows))
    out=[]; tt=0
    for j,(c,name,idx,inst,known,initial) in enumerate(rows[:30]):
        L,U,s,m,proof=initial
        best,bs,bm,st=random_search(inst,U,s,m,known=known,iters=3000,seed=j)
        tt+=st['t']
        print(j,c,name,idx,'known',known,'U0',U,'->',best,'gap',best-known,'t',st['t'],'iters',st['iters'])
        out.append(best-known)
    print('opt count',sum(x==0 for x in out),'/',len(out),'avg gap',sum(out)/len(out),'time',tt)
