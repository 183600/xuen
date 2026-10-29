import sys, json, random, heapq
sys.path[:0] = ['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from hap import weak_rows
from pdicf import _pin_weak, _guide_at
from lpr import marginals, topo_order, quantile, sgs
from pact import PACT
from po import heads_tails
from rdf import check_schedule

d=json.load(open('exp/v8u/bench_pdicf_final_pd.json'))
sched={}
for which in ['main','weak']:
    for r in d[which]['pd']:
        sched[(r['name'],r['idx'],r['known'],tuple(r['schedule']))]=r

def get(which,name,idx):
    if which=='main':
        for c,n,i,inst,known in corpora():
            if n==name and i==idx:
                co=PACT(inst,pact_mode='complete',use_ga=False)
                L,U,s,m=co.initial_bounds(); L,U=int(L),int(U)
                ps,guide,extra=_guide_at(co,L) if L<U else (None,None,0)
                return c,inst,known,L,U,ps,guide
    else:
        for c,n,i,inst,known,init in weak_rows(4):
            if n==name and i==idx:
                L0,U0,s0,m0,p0=init
                co,L,U,s,m,proof,pinlp=_pin_weak(inst,L0,U0,s0,m0,p0)
                ps,guide,extra=_guide_at(co,L) if L<U else (None,None,0)
                return c,inst,known,int(L),int(U),ps,guide

def disc(inst,order,key):
    n=inst['n']; indeg=[len(inst['pred'][i]) for i in range(n)]
    ready={i for i in range(n) if indeg[i]==0}; d=0
    for act in order:
        if act not in ready: return None
        ref=min(ready,key=lambda i:(key[i],i))
        if act!=ref: d+=1
        ready.remove(act)
        for j in inst['succ'][act]:
            indeg[j]-=1
            if indeg[j]==0: ready.add(j)
    return d

targets=[('main',r) for r in d['main']['pd'] if r['probes']>0 and any(st[0]=='YES' for st in r['steps'])]
targets+=[('weak',r) for r in d['weak']['pd'] if r['probes']>0 and any(st[0]=='YES' for st in r['steps'])]
for which,r in targets:
    name,idx=r['name'],r['idx']
    c,inst,known,L,U,ps,guide=get(which,name,idx)
    s=r['schedule']
    order=topo_order(inst,lambda i:(s[i],i))
    # verify sgs order <= known
    z=sgs(inst,order,None)
    print('\n',which,c,name,idx,'known',known,'L',L,'U',U,'n',inst['n'],'order_cmax',z[2] if z else None)
    if ps is None: 
        print(' no ps'); continue
    mrg=marginals(inst,ps,guide)
    mean=[m for m,_ in mrg]
    est,tail=heads_tails(inst,0,[0]*inst['n'])
    keys={'mean':{i:mean[i]+i*1e-6 for i in range(inst['n'])},
          'tail':{i:-tail[i]+i*1e-6 for i in range(inst['n'])},
          'latest':{i:-(L-tail[i]-inst['p'][i])+i*1e-6 for i in range(inst['n'])}}
    for q in (0.02,0.1,0.25,0.5,0.75,0.9,0.98):
        keys['q%g'%q]={i:quantile(mrg[i][1],q)+i*1e-6 for i in range(inst['n'])}
    print('  witness disc', {k:disc(inst,order,v) for k,v in keys.items()})
