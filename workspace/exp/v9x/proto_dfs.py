import sys,json,time
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from po import heads_tails
from rdf import check_schedule, _earliest
from sparc import Swarm, _strong_init

def avail(inst,mask):
    return [i for i in range(inst['n']) if not (mask>>i)&1 and all((mask>>j)&1 for j in inst['pred'][i])]

def bound(inst,mask,starts,cm,target):
    n=inst['n']; p=inst['p']
    fin=[(starts[i]+p[i]) if (mask>>i)&1 else 0 for i in range(n)]
    est,q=heads_tails(inst,mask,fin)
    lb=cm
    for i in range(n):
        if not (mask>>i)&1:
            v=est[i]+p[i]+q[i]
            if v>lb: lb=v
    return lb

def dfs(inst,target,rank,nodecap=200000):
    n=inst['n']; p=inst['p']; m=inst['m']; full=(1<<n)-1
    starts=[None]*n; machs=[None]*n
    busy=[[] for _ in range(m)]; predfin=[0]*n
    seen=set(); nodes=0; t0=time.time()
    def rec(mask,cm):
        nonlocal nodes
        nodes+=1
        if nodes>nodecap: return None
        if mask==full:
            return (list(starts),list(machs),cm)
        key=(mask,tuple(tuple(x) for x in busy),tuple(predfin))
        if key in seen: return None
        seen.add(key)
        av=avail(inst,mask)
        av.sort(key=lambda i:(rank[i],i))
        for i in av:
            base=predfin[i]
            opts=[]
            for k in inst['elig'][i]:
                tt=_earliest(busy[k],base,p[i])
                ft=tt+p[i]
                if ft<=target:
                    opts.append((tt,ft,k))
            # dedup same (tt,k) etc; try earliest first
            opts.sort()
            for tt,ft,k in opts:
                nm=mask|(1<<i)
                starts[i]=tt; machs[i]=k
                busy[k].append((tt,ft)); busy[k].sort()
                old=[predfin[j] for j in inst['succ'][i]]
                for j in inst['succ'][i]:
                    if ft>predfin[j]: predfin[j]=ft
                if bound(inst,nm,starts,max(cm,ft),target)<=target:
                    r=rec(nm,max(cm,ft))
                    if r is not None: return r
                for j,v in zip(inst['succ'][i],old): predfin[j]=v
                busy[k].remove((tt,ft))
                starts[i]=None; machs[i]=None
        return None
    r=rec(0,0)
    return r,dict(nodes=nodes,t=round(time.time()-t0,4),seen=len(seen))

def main():
    rows=list(corpora()); idx={(c,n,i):(c,n,i,inst,k) for c,n,i,inst,k in rows}
    sp=json.load(open('exp/v91/bench_sparc.json'))['rows']['strong_pso1_lower']
    hard=[r for r in sp if r['known']==r['lb0'] and r['ub_pso']>r['lb0']]
    for cap in (10000,50000,200000,1000000):
        ok=0; tt=0; nn=0; det=[]
        for r in hard:
            c,n,i,inst,known=idx[(r['corpus'],r['name'],r['idx'])]
            L,U,s,m,proof,pin=_strong_init(inst)
            sw=Swarm(inst,U,s,m,n_particles=8,iters=1,seed=7,stall=1000)
            best,st=sw.run()
            cc,s2,m2=best
            # rank from pso schedule
            rank={i:s2[i]+1e-6*i for i in range(inst['n'])}
            sol,stt=dfs(inst,r['lb0'],rank,nodecap=cap)
            tt+=stt['t']; nn+=stt['nodes']
            if sol is not None:
                ok+=1
                ss,mm,ccc=sol
                assert check_schedule(inst,ccc,ss,mm)
            det.append((r['corpus'],r['name'],r['idx'],sol is not None,stt['nodes'],stt['t']))
        print('cap',cap,'ok',ok,'nodes',nn,'t',round(tt,2))
        if cap==200000:
            for d in det: print(' ',d)

if __name__=='__main__': main()
