import sys, json, collections
sys.path[:0] = ['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from hap import weak_rows
from pdicf import _pin_weak, _guide_at
from lpr import marginals, topo_order
from pact import PACT

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

def greedy_machine(inst, starts, busy, i):
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

def witness(inst, order, route, key):
    n=inst['n']; starts=[0]*n; busy=[[] for _ in range(inst['m'])]
    indeg=[len(inst['pred'][i]) for i in range(n)]
    ready={i for i in range(n) if indeg[i]==0}
    dj=dm=0; det=[]
    for act in order:
        if act not in ready: return None
        refjob=min(ready,key=lambda i:(key(i),i))
        if act!=refjob: dj+=1
        refm,t,ft=greedy_machine(inst,starts,busy,act)
        if route[act]!=refm: dm+=1
        # schedule with witness route
        base=0
        for j in inst['pred'][act]: base=max(base,starts[j]+inst['p'][j])
        k=route[act]
        if k not in inst['elig'][act]: return None
        tt=base
        for a,b in busy[k]:
            if tt+inst['p'][act]<=a: break
            if tt<b: tt=b
        ftt=tt+inst['p'][act]
        starts[act]=tt; busy[k].append((tt,ftt)); busy[k].sort()
        ready.remove(act)
        for j in inst['succ'][act]:
            indeg[j]-=1
            if indeg[j]==0: ready.add(j)
    return dj,dm

for which in ['main','weak']:
    rows=d[which]['pd']; hist=collections.Counter(); det=[]
    for r in rows:
        c,inst,known,L,U,ps,guide=get(which,r['name'],r['idx'])
        if ps is None or guide is None: continue
        mrg=marginals(inst,ps,guide); mean=[m for m,_ in mrg]
        key=lambda i: mean[i]+i*1e-6
        s=r['schedule']; route=r['machine']
        order=topo_order(inst,lambda i:(s[i],i))
        w=witness(inst,order,route,key)
        if w is None: continue
        dj,dm=w; hist[(dj,dm)]+=1
        if r['probes']>0 and any(st[0]=='YES' for st in r['steps']):
            det.append((r['name'],r['idx'],dj,dm,dj+dm,r['probes']))
    print('\n===',which,'hist (job,mach) top',hist.most_common(15))
    print('total',sum(hist.values()),'jobdev mean',sum((a*b) for (a,_),b in hist.items())/sum(hist.values()),'machdev mean',sum((b*a) for (_,b),a in hist.items())/sum(hist.values()))
    print('target details',det)
    # distribution of total discrepancy
    tot=collections.Counter()
    for (a,b),cnt in hist.items(): tot[a+b]+=cnt
    print('total disc hist',sorted(tot.items()))
