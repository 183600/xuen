import sys,time,random,collections
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from po import heads_tails
from rdf import check_schedule

def prep(inst):
    n=inst['n']; p=inst['p']; pred=inst['pred']; succ=inst['succ']
    indeg=[len(pred[i]) for i in range(n)]; q=[i for i in range(n) if indeg[i]==0]; topo=[]
    while q:
        i=q.pop(); topo.append(i)
        for j in succ[i]:
            indeg[j]-=1
            if indeg[j]==0:q.append(j)
    est=[0]*n
    for i in topo: est[i]=max([0]+[est[j]+p[j] for j in pred[i]])
    tail=[0]*n
    for i in reversed(topo): tail[i]=max([0]+[p[j]+tail[j] for j in succ[i]])
    pm=[0]*n
    for i in range(n):
        for j in pred[i]: pm[i]|=1<<j
    return est,tail,pm

def solve(inst,h,node_budget,rng,mode=0):
    n=inst['n']; m=inst['m']; p=inst['p']; elig=inst['elig']; succ=inst['succ']
    est,tail,pred_mask=prep(inst)
    starts=[-1]*n; mach=[-1]*n; occ=[0]*m; pred_ready=[0]*n
    nodes=0; schedmask=0
    def lb(unsched):
        mx=0
        for i in range(n):
            if not (unsched>>i)&1: continue
            hr=max(est[i],pred_ready[i]); v=hr+p[i]+tail[i]
            if v>mx:mx=v
        # machine free + load mask bounds (cheap)
        minfree=[]
        for k in range(m):
            x=occ[k]; t=0
            while (x>>t)&1:t+=1
            minfree.append(t)
        for mask in range(1,1<<m):
            cnt=bin(mask).count('1'); load=0
            for i in range(n):
                if (unsched>>i)&1 and all((mask>>k)&1 for k in elig[i]): load+=p[i]
            if load:
                mf=min(minfree[k] for k in range(m) if (mask>>k)&1)
                v=mf+(load+cnt-1)//cnt
                if v>mx:mx=v
        return mx
    def rec(unsched,cmax):
        nonlocal nodes
        nodes+=1
        if nodes>node_budget:return None
        if unsched==0:return (list(starts),list(mach))
        if lb(unsched)>h:return None
        sched=((1<<n)-1)^unsched
        el=[]
        for i in range(n):
            if (unsched>>i)&1 and (pred_mask[i]&sched)==pred_mask[i]:
                hr=max(est[i],pred_ready[i])
                if mode==0: key=(-(tail[i]+p[i]),hr,i)
                elif mode==1: key=(-(tail[i]+p[i]+rng.random()*6),hr,i)
                elif mode==2: key=(-(p[i]+rng.random()*8),hr,i)
                else: key=(rng.random(),hr,i)
                el.append((key,i,hr))
        el.sort()
        for _,i,hr in el:
            ks=list(elig[i]); rng.shuffle(ks)
            for k in ks:
                pm=p[i]; t=hr
                while t+pm<=h:
                    if (occ[k]>>t)&((1<<pm)-1)==0: break
                    t+=1
                if t+pm>h: continue
                starts[i]=t; mach[i]=k; occ[k]|=((1<<pm)-1)<<t
                old=[pred_ready[j] for j in succ[i]]
                for j in succ[i]:
                    if pred_ready[j]<t+pm:pred_ready[j]=t+pm
                r=rec(unsched&~(1<<i),max(cmax,t+pm))
                if r is not None:return r
                for j,o in zip(succ[i],old):pred_ready[j]=o
                occ[k]&=~(((1<<pm)-1)<<t); starts[i]=-1; mach[i]=-1
        return None
    r=rec((1<<n)-1,0)
    return r,nodes

def dfs_restart(inst,U0,s0,m0,known=None,restarts=30,budget=300,seed=0):
    rng=random.Random(seed+777)
    best=U0; bs=list(s0); bm=list(m0); total=0; t0=time.time()
    for r in range(restarts):
        if best<=1:break
        h=best-1
        res,nodes=solve(inst,h,budget,rng,mode=r%4)
        total+=nodes
        if res is not None:
            s,m=res
            c=max(s[i]+inst['p'][i] for i in range(inst['n']))
            if c<=h and check_schedule(inst,c,s,m):
                best=c;bs,bm=s,m
                if best<=known:break
        if nodes>budget: continue
    return best,bs,bm,dict(t=round(time.time()-t0,3),nodes=total,restarts=r+1)

if __name__=='__main__':
    rows=weak_rows(4)
    out=[];tt=0
    for j,(c,name,idx,inst,known,initial) in enumerate(rows[:30]):
        L,U,s,m,proof=initial
        best,bs,bm,st=dfs_restart(inst,U,s,m,known=known,restarts=30,budget=400,seed=j)
        tt+=st['t']
        print(j,c,name,idx,'known',known,'U0',U,'->',best,'gap',best-known,'t',st['t'],'nodes',st['nodes'],'restarts',st['restarts'])
        out.append(best-known)
    print('opt',sum(x==0 for x in out),'/',len(out),'avg',sum(out)/len(out),'time',tt)
