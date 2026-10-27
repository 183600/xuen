import sys,time,random,collections
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from po import heads_tails
from rdf import check_schedule

def _prep(inst):
    n=inst['n'];p=inst['p'];pred=inst['pred'];succ=inst['succ']
    indeg=[len(pred[i]) for i in range(n)];q=[i for i in range(n) if indeg[i]==0];topo=[]
    while q:
        i=q.pop();topo.append(i)
        for j in succ[i]:
            indeg[j]-=1
            if indeg[j]==0:q.append(j)
    est=[0]*n
    for i in topo: est[i]=max([0]+[est[j]+p[j] for j in pred[i]])
    tail=[0]*n
    for i in reversed(topo): tail[i]=max([0]+[p[j]+tail[j] for j in succ[i]])
    pm=[0]*n
    for i in range(n):
        for j in pred[i]:pm[i]|=1<<j
    return est,tail,pm

def lds(inst,h,D,budget,seed=0,w=3,time_cap=1.0):
    n=inst['n'];m=inst['m'];p=inst['p'];elig=inst['elig'];succ=inst['succ']
    est,tail,pm=_prep(inst);rng=random.Random(seed)
    starts=[-1]*n;mach=[-1]*n;occ=[0]*m;pred_ready=[0]*n
    nodes=0;t0=time.time()
    def lower(unsched):
        mx=0
        for i in range(n):
            if not (unsched>>i)&1:continue
            v=max(est[i],pred_ready[i])+p[i]+tail[i]
            if v>mx:mx=v
        return mx
    def rec(unsched,cmax,disc):
        nonlocal nodes
        nodes+=1
        if nodes>budget or time.time()-t0>time_cap:return None
        if unsched==0:return (list(starts),list(mach))
        if lower(unsched)>h:return None
        sched=((1<<n)-1)^unsched
        alts=[]
        for i in range(n):
            if (unsched>>i)&1 and (pm[i]&sched)==pm[i]:
                hr=max(est[i],pred_ready[i])
                key=(-(tail[i]+p[i])+rng.random()*0.01,hr,i)
                alts.append((key,i,hr))
        alts.sort()
        for ai,(_,i,hr) in enumerate(alts):
            # rank machines by earliest finish
            ms=[]
            for k in elig[i]:
                t=hr
                while t+p[i]<=h:
                    if (occ[k]>>t)&((1<<p[i])-1)==0:break
                    t+=1
                if t+p[i]<=h:ms.append((t+p[i],t,k))
            ms.sort()
            for mi,(ft,t,k) in enumerate(ms):
                nd=disc+(1 if ai>0 else 0)+(1 if mi>0 else 0)
                if nd>D:continue
                starts[i]=t;mach[i]=k;occ[k]|=((1<<p[i])-1)<<t
                old=[pred_ready[j] for j in succ[i]]
                for j in succ[i]:
                    if pred_ready[j]<ft:pred_ready[j]=ft
                r=rec(unsched&~(1<<i),max(cmax,ft),nd)
                if r is not None:return r
                for j,o in zip(succ[i],old):pred_ready[j]=o
                occ[k]&=~(((1<<p[i])-1)<<t);starts[i]=-1;mach[i]=-1
        return None
    r=rec((1<<n)-1,0,0)
    return r,nodes,round(time.time()-t0,4)

if __name__=='__main__':
    rows=weak_rows(4)
    for j,(c,name,idx,inst,known,initial) in enumerate(rows[:10]):
        L,U,s,m,proof=initial
        for D in [0,1,2,3]:
            r,nodes,t=lds(inst,U-1,D,20000,seed=j)
            print(j,name,idx,'known',known,'U0',U,'D',D,'found',r is not None,'nodes',nodes,'t',t)
        print()
