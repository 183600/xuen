import sys, json, time, random, math, heapq
sys.path[:0] = ['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from hap import weak_rows
from pdicf import _pin_weak, _guide_at
from lpr import marginals, topo_order, quantile, sgs
from pact import PACT
from po import heads_tails
from rdf import check_schedule

d=json.load(open('exp/v8u/bench_pdicf_final_pd.json'))

def get(which,name,idx):
    if which=='main':
        for c,n,i,inst,known in corpora():
            if n==name and i==idx:
                co=PACT(inst,pact_mode='complete',use_ga=False)
                L,U,s,m=co.initial_bounds(); L,U=int(L),int(U)
                ps,guide,extra=_guide_at(co,L) if L<U else (None,None,0)
                return c,inst,known,int(L),int(U),ps,guide
    else:
        for c,n,i,inst,known,init in weak_rows(4):
            if n==name and i==idx:
                L0,U0,s0,m0,p0=init
                co,L,U,s,m,proof,pinlp=_pin_weak(inst,L0,U0,s0,m0,p0)
                ps,guide,extra=_guide_at(co,L) if L<U else (None,None,0)
                return c,inst,known,int(L),int(U),ps,guide

def greedy_place(inst,starts,busy,i):
    base=0
    for j in inst['pred'][i]: base=max(base,starts[j]+inst['p'][j])
    best=None
    for k in inst['elig'][i]:
        t=base; pi=inst['p'][i]
        for a,b in busy[k]:
            if t+pi<=a: break
            if t<b: t=b
        cand=(t+pi,t,k)
        if best is None or cand<best: best=cand
    return best[2],best[1],best[0]

def greedy_route(inst,order):
    starts=[0]*inst['n']; busy=[[] for _ in range(inst['m'])]; route=[-1]*inst['n']
    for i in order:
        k,t,ft=greedy_place(inst,starts,busy,i)
        route[i]=k; starts[i]=t; busy[k].append((t,ft)); busy[k].sort()
    return route

def lds_route(inst,H,key,refroute,max_disc=3,node_cap=200000,time_cap=0.2):
    n=inst['n']; p=inst['p']; elig=inst['elig']; pred=inst['pred']; succ=inst['succ']
    t0=time.time(); nodes=0; found=None; best=[10**9]
    starts=[0]*n; machine=[-1]*n; busy=[[] for _ in range(inst['m'])]
    indeg=[len(pred[i]) for i in range(n)]
    ready0=frozenset(i for i in range(n) if indeg[i]==0)
    def rec(ready,indeg,disc,cm):
        nonlocal nodes,found
        if found is not None: return
        nodes+=1
        if nodes>node_cap or time.time()-t0>time_cap: return
        if not ready:
            if cm<best[0]: best[0]=cm
            if cm<=H: found=(list(starts),list(machine),cm)
            return
        order=sorted(ready,key=lambda i:(key(i),i))
        refjob=order[0]
        # reference machine at this state
        refm,_,_=greedy_place(inst,starts,busy,refjob)
        for i in order:
            base=0
            for j in pred[i]: base=max(base,starts[j]+p[j])
            # candidate machines: reference job uses greedy first; others use eligible
            machs=sorted(elig[i], key=lambda k: (k!=refroute[i], k))
            if i==refjob:
                machs=sorted(elig[i], key=lambda k: (k!=refm,k))
            for k in machs:
                dm=0 if (i==refjob and k==refm) or (i!=refjob and k==refroute[i]) else 1
                nd=disc+(0 if i==refjob else 1)+dm
                if nd>max_disc: continue
                t=base
                for a,b in busy[k]:
                    if t+p[i]<=a: break
                    if t<b: t=b
                ft=t+p[i]
                if ft>H: continue
                old=list(busy[k])
                busy[k].append((t,ft)); busy[k].sort()
                starts[i]=t; machine[i]=k
                nready=frozenset(j for j in ready if j!=i)
                nind=list(indeg)
                for j in succ[i]:
                    nind[j]-=1
                    if nind[j]==0: nready=nready|{j}
                rec(nready,nind,nd,max(cm,ft))
                busy[k]=old; starts[i]=0; machine[i]=-1
                if found is not None: return
    rec(ready0,indeg,0,0)
    return dict(found=found,best=best[0] if best[0]<10**9 else None,nodes=nodes,t=time.time()-t0)

def keys_for(inst,ps,guide,L):
    mrg=marginals(inst,ps,guide); mean=[m for m,_ in mrg]
    est,tail=heads_tails(inst,0,[0]*inst['n'])
    out={'mean':lambda i: mean[i]+i*1e-6}
    for q in (0.02,0.1,0.25,0.5,0.75,0.9,0.98):
        out['q%g'%q]=lambda i,q=q: quantile(mrg[i][1],q)+i*1e-6
    out['tail']=lambda i: -tail[i]+i*1e-6
    out['latest']=lambda i: -(L-tail[i]-inst['p'][i])+i*1e-6
    return out

if __name__=='__main__':
    targets=[('main',r) for r in d['main']['pd'] if r['probes']>0 and any(st[0]=='YES' for st in r['steps'])]
    targets+=[('weak',r) for r in d['weak']['pd'] if r['probes']>0 and any(st[0]=='YES' for st in r['steps'])]
    for which,r in targets:
        c,inst,known,L,U,ps,guide=get(which,r['name'],r['idx'])
        print('\n',which,c,r['name'],r['idx'],'known',known,'L',L,'n',inst['n'])
        if ps is None: print(' no guide'); continue
        ks=keys_for(inst,ps,guide,L)
        for tag,key in ks.items():
            order=topo_order(inst,key)
            rr=greedy_route(inst,order)
            hit=None
            for dm in range(0,6):
                z=lds_route(inst,L,key,rr,max_disc=dm,node_cap=60000,time_cap=0.08)
                if z['found'] is not None:
                    hit=(dm,z['nodes'],round(z['t'],3)); break
            print(' ',tag,'hit',hit)
