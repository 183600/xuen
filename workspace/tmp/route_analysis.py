import sys, json, collections, statistics
sys.path[:0] = ['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from hap import weak_rows
from pdicf import _pin_weak, _guide_at
from lpr import marginals, topo_order, sgs
from pact import PACT

d=json.load(open('exp/v8u/bench_pdicf_final_pd.json'))

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

for which in ['main','weak']:
    rows=d[which]['pd']; out=[]
    for r in rows:
        c,inst,known,L,U,ps,guide=get(which,r['name'],r['idx'])
        if ps is None or guide is None: continue
        mrg=marginals(inst,ps,guide); mean=[m for m,_ in mrg]
        key=lambda i: mean[i]+i*1e-6
        order=topo_order(inst,key)
        z=sgs(inst,order,None)
        if z is None: continue
        gs,gm,gc=z
        optm=r['machine']; opts=r['schedule']
        diff=sum(1 for i in range(inst['n']) if gm[i]!=optm[i])
        # earliest-diff position
        out.append((r['probes'],gc,known,diff,L,r['name'],r['idx'],c))
    print('\n===',which)
    print('n',len(out),'greedy hit at known',sum(1 for x in out if x[1]<=x[2]))
    print('route diff hist',collections.Counter(x[3] for x in out))
    print('greedy excess hist',collections.Counter(x[1]-x[2] for x in out))
    # by probes
    for p in [0,1]:
        z=[x for x in out if x[0]==p]
        if z:
            print(' probes',p,'n',len(z),'excess',collections.Counter(x[1]-x[2] for x in z),'route diff',collections.Counter(x[3] for x in z))
    # near misses: greedy > known
    z=[x for x in out if x[1]>x[2]]
    print(' near-miss n',len(z),'route diff mean',statistics.mean(x[3] for x in z) if z else None)
    print(' near-miss route diff hist',collections.Counter(x[3] for x in z))
