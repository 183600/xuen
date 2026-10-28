import sys,json,time
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from po import heads_tails
from rdf import check_schedule, _earliest
from sparc import Swarm, _strong_init

def avail(inst,mask):
    return [i for i in range(inst['n']) if not (mask>>i)&1 and all((mask>>j)&1 for j in inst['pred'][i])]

def bound(inst,mask,starts,cm):
    n=inst['n']; p=inst['p']
    fin=[(starts[i]+p[i]) if (mask>>i)&1 else 0 for i in range(n)]
    est,q=heads_tails(inst,mask,fin)
    lb=cm
    for i in range(n):
        if not (mask>>i)&1:
            v=est[i]+p[i]+q[i]
            if v>lb: lb=v
    return lb

def expand(inst,st,target):
    n=inst['n']; p=inst['p']
    mask,starts,machs,busy,predfin,cm=st[:6]
    out=[]
    for i in avail(inst,mask):
        base=predfin[i]; best=None
        for k in inst['elig'][i]:
            t=_earliest(busy[k],base,p[i]); cand=(t+p[i],t,k)
            if best is None or cand<best: best=cand
        if best is None: continue
        ft,t,k=best
        if ft>target: continue
        nm=mask|(1<<i); ns=list(starts); ns[i]=t
        nmach=list(machs); nmach[i]=k
        nb=[list(x) for x in busy]; nb[k].append((t,ft)); nb[k].sort()
        npf=list(predfin)
        for j in inst['succ'][i]:
            if ft>npf[j]: npf[j]=ft
        lb=bound(inst,nm,ns,max(cm,ft))
        if lb>target: continue
        out.append((nm,ns,nmach,nb,npf,max(cm,ft)))
    return out

def key(st):
    mask,starts,machs,busy,predfin,cm=st
    return (mask,tuple(tuple(x) for x in busy),tuple(predfin))

def complete(inst,st,rank,target):
    n=inst['n']; p=inst['p']; m=inst['m']
    mask,starts,machs,busy,predfin,cm=[list(x) if isinstance(x,list) else x for x in st[:6]]
    starts=list(starts); machs=list(machs); busy=[list(x) for x in busy]; predfin=list(predfin)
    while mask!=(1<<n)-1:
        av=avail(inst,mask)
        if not av: return None
        av.sort(key=lambda i:(rank[i],i))
        i=av[0]; base=predfin[i]; best=None
        for k in inst['elig'][i]:
            t=_earliest(busy[k],base,p[i]); cand=(t+p[i],t,k)
            if best is None or cand<best: best=cand
        if best is None: return None
        ft,t,k=best
        if ft>target: return None
        mask|=1<<i; starts[i]=t; machs[i]=k
        busy[k].append((t,ft)); busy[k].sort()
        for j in inst['succ'][i]:
            if ft>predfin[j]: predfin[j]=ft
        cm=max(cm,ft)
    return starts,machs,cm

def beam(inst,target,width=100,ranks=None):
    n=inst['n']; t0=time.time()
    root=(0,[None]*n,[None]*n,[[] for _ in range(inst['m'])],[0]*n,0)
    beam=[root]
    seen=set(); nodes=0; rollouts=0
    best=None
    for depth in range(n):
        cand=[]
        for st in beam:
            ch=expand(inst,st,target)
            nodes+=len(ch)
            for c in ch:
                k=key(c)
                if k in seen: continue
                seen.add(k)
                # rollout best over ranks
                bestc=None
                for rank in ranks:
                    r=complete(inst,c,rank,target); rollouts+=1
                    if r is not None:
                        return r,dict(nodes=nodes,t=round(time.time()-t0,4),rollouts=rollouts,found='rollout',depth=depth)
                    # compute rollout cmax even if >target for scoring
                    # (complete returns None on >target; do a no-target variant)
                # score by lower bound
                cand.append(c)
        if not cand:
            return None,dict(nodes=nodes,t=round(time.time()-t0,4),rollouts=rollouts,depth=depth)
        cand.sort(key=lambda s:(bound(inst,s[0],s[1],s[5]),s[5],sum(x for x in s[1] if x is not None),s[0]))
        beam=cand[:width]
    return None,dict(nodes=nodes,t=round(time.time()-t0,4),rollouts=rollouts)

def main():
    rows=list(corpora()); idx={(c,n,i):(c,n,i,inst,k) for c,n,i,inst,k in rows}
    sp=json.load(open('exp/v91/bench_sparc.json'))['rows']['strong_pso1_lower']
    hard=[r for r in sp if r['known']==r['lb0'] and r['ub_pso']>r['lb0']]
    yes46=[r for r in sp if r['known']==r['lb0'] and r['ub0']>r['lb0']]
    for tag,cases in [('hard12',hard),('yes46',yes46)]:
      print('==',tag,len(cases))
      for width in (30,100,300):
        ok=0; tt=0; nn=0; rr=0; det=[]
        for r in cases:
            c,n,i,inst,known=idx[(r['corpus'],r['name'],r['idx'])]
            L,U,s,m,proof,pin=_strong_init(inst)
            # pso rank from a small run
            sw=Swarm(inst,U,s,m,n_particles=8,iters=12,seed=7,stall=4)
            best,st=sw.run(); cc,s2,m2=best
            rank1={i:s2[i]+1e-6*i for i in range(inst['n'])}
            est,q=heads_tails(inst,0,[0]*inst['n'])
            rank2={i:est[i]+1e-6*i for i in range(inst['n'])}
            rank3={i:-q[i]+1e-6*i for i in range(inst['n'])}
            ranks=[rank1,rank2,rank3]
            sol,stt=beam(inst,r['lb0'],width=width,ranks=ranks)
            tt+=stt['t']; nn+=stt['nodes']; rr+=stt['rollouts']
            if sol is not None:
                ok+=1; ss,mm,ccc=sol
                assert check_schedule(inst,ccc,ss,mm)
            det.append((r['corpus'],r['name'],r['idx'],sol is not None))
        print(' width',width,'ok',ok,'/',len(cases),'nodes',nn,'roll',rr,'t',round(tt,2))
        if tag=='hard12' and width==300:
            for d in det: print('  ',d)

if __name__=='__main__': main()
