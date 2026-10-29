import sys, json, time, random, math, heapq, collections
sys.path[:0] = ['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from hap import weak_rows
from pdicf import _pin_weak, _guide_at
from lpr import marginals, topo_order, sgs
from pact import PACT
from po import heads_tails
from rdf import check_schedule

TARGETS = {('base','holdout',36),('base','large_het',3),('base','large_het',5),('base','large_het',7),('pert','h5',4),('pert','h5',28),('pert','h47',20),('pert','h47',29),('base','large_b',8),('stress','stress',5)}

def get_ctx(which, name, idx):
    if which=='main':
        for c,n,i,inst,known in corpora():
            if (c,n,i)==(name,idx) or (c,n,i)==(name,idx):
                pass
        # simpler
        for c,n,i,inst,known in corpora():
            if n==name and i==idx:
                co=PACT(inst,pact_mode='complete',use_ga=False)
                L,U,s,m=co.initial_bounds(); L,U=int(L),int(U)
                proof=co._ensure_lb_proof(L)
                ps,guide,extra=_guide_at(co,L) if L<U else (None,None,0)
                return inst,known,L,U,ps,guide
    else:
        for c,n,i,inst,known,init in weak_rows(4):
            if n==name and i==idx:
                L0,U0,s0,m0,p0=init
                co,L,U,s,m,proof,pinlp=_pin_weak(inst,L0,U0,s0,m0,p0)
                ps,guide,extra=_guide_at(co,L) if L<U else (None,None,0)
                return inst,known,int(L),int(U),ps,guide
    return None

def ref_keys(inst, ps, guide, H):
    if ps is not None and guide is not None and getattr(guide,'x',None) is not None:
        mrg=marginals(inst,ps,guide)
        mean=[m for m,_ in mrg]
        return {i: mean[i]+i*1e-6 for i in range(inst['n'])}
    return {i: (inst['est'][i] if 'est' in inst else 0)+i*1e-6 for i in range(inst['n'])}

def order_from_schedule(inst, s):
    n=inst['n']
    # sort by start, tie by topological index
    topo=topo_order(inst, lambda i: (s[i], i))
    return topo

def discrepancy(inst, order, key):
    n=inst['n']; indeg=[len(inst['pred'][i]) for i in range(n)]
    ready=set(i for i in range(n) if indeg[i]==0); d=0; pos=0
    while pos<n:
        ref=min(ready, key=lambda i:(key[i],i))
        act=order[pos]
        if act not in ready:
            return None
        if act!=ref: d+=1
        ready.remove(act); pos+=1
        for j in inst['succ'][act]:
            indeg[j]-=1
            if indeg[j]==0: ready.add(j)
    return d

def lds(inst, H, key, max_disc=3, node_cap=200000, time_cap=2.0):
    n=inst['n']; p=inst['p']; elig=inst['elig']; pred=inst['pred']; succ=inst['succ']
    t0=time.time(); nodes=0; best=(10**9,None,None)
    starts=[0]*n; machine=[-1]*n; busy=[[] for _ in range(inst['m'])]
    indeg=[len(pred[i]) for i in range(n)]
    ready0=[i for i in range(n) if indeg[i]==0]
    # order ready by key
    found=None
    def rec(done, ready, indeg, starts, machine, busy, disc, cm):
        nonlocal nodes, best, found
        if found is not None: return
        nodes+=1
        if nodes>node_cap or time.time()-t0>time_cap: return
        if not ready:
            if cm<best[0]: best=(cm,list(starts),list(machine))
            if cm<=H: found=(list(starts),list(machine),cm)
            return
        order=sorted(ready,key=lambda i:(key[i],i))
        ref=order[0]
        for kk,i in enumerate(order):
            nd=disc+(1 if i!=ref else 0)
            if nd>max_disc: continue
            # place i by SGS
            base=0
            for j in pred[i]:
                v=starts[j]+p[j]
                if v>base: base=v
            bst=None
            for k in elig[i]:
                t=base; pi=p[i]
                for a,b in busy[k]:
                    if t+pi<=a: break
                    if t<b: t=b
                cand=(t+pi,t,k)
                if bst is None or cand<bst: bst=cand
            ft,t,k=bst
            if ft>H: continue
            oldbusy=list(busy[k])
            busy[k].append((t,ft)); busy[k].sort()
            starts[i]=t; machine[i]=k
            nready=[j for j in ready if j!=i]
            nind=list(indeg)
            for j in succ[i]:
                nind[j]-=1
                if nind[j]==0: nready.append(j)
            rec(done+1,nready,nind,starts,machine,busy,nd,max(cm,ft))
            busy[k]=oldbusy; starts[i]=0; machine[i]=-1
            if found is not None: return
    rec(0,ready0,indeg,starts,machine,busy,0,0)
    return dict(found=found,best=best,nodes=nodes,t=time.time()-t0)

if __name__=='__main__':
    for which in ['main','weak']:
        print('====',which)
        for c,name,idx,inst,known,L,U,ps,guide in []:
            pass
        rows = corpora() if which=='main' else [(c,n,i,inst,known) for c,n,i,inst,known,init in weak_rows(4)]
        for c,name,idx,inst,known in rows:
            if (c,name,idx) not in TARGETS: continue
            ctx=get_ctx(which,name,idx)
            if ctx is None: continue
            inst,known,L,U,ps,guide=ctx
            key=ref_keys(inst,ps,guide,L)
            # witness order from optimal schedule in JSON
            print(c,name,idx,'known',known,'L',L,'U',U,'n',inst['n'],'m',inst['m'])
            for d in range(0,6):
                r=lds(inst,L,key,max_disc=d,node_cap=300000,time_cap=1.0)
                print('  LDS d',d,'found',r['found'] is not None,'best',r['best'][0],'nodes',r['nodes'],'t',round(r['t'],3))
                if r['found'] is not None: break
