import sys, json
sys.path[:0] = ['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from hap import weak_rows
from pdicf import _pin_weak, _guide_at
from lpr import topo_order
from pact import PACT

def sgs_fixed(inst, order, mach, H=None):
    n,m,p=inst['n'],inst['m'],inst['p']; pred=inst['pred']; elig=inst['elig']
    starts=[0]*n; machine=[-1]*n; busy=[[] for _ in range(m)]
    for i in order:
        base=0
        for j in pred[i]:
            base=max(base,starts[j]+p[j])
        k=mach[i]
        if k not in elig[i]:
            return None
        t=base
        for a,b in busy[k]:
            if t+p[i]<=a: break
            if t<b: t=b
        ft=t+p[i]
        if H is not None and ft>H: return None
        starts[i]=t; machine[i]=k
        busy[k].append((t,ft)); busy[k].sort()
    c=max(starts[i]+p[i] for i in range(n))
    return starts,machine,c

d=json.load(open('exp/v8u/bench_pdicf_final_pd.json'))
targets=[('main',r) for r in d['main']['pd'] if r['probes']>0 and any(st[0]=='YES' for st in r['steps'])]
targets+=[('weak',r) for r in d['weak']['pd'] if r['probes']>0 and any(st[0]=='YES' for st in r['steps'])]
for which,r in targets:
    s=r['schedule']; m=r['machine']; known=r['known']
    # find inst
    inst=None
    if which=='main':
        for c,n,i,ins,kn in corpora():
            if n==r['name'] and i==r['idx']: inst=ins; break
    else:
        for c,n,i,ins,kn,init in weak_rows(4):
            if n==r['name'] and i==r['idx']: inst=ins; break
    order=topo_order(inst,lambda i:(s[i],i))
    z=sgs_fixed(inst,order,m,None)
    z2=sgs_fixed(inst,order,m,r['L'])
    print(which,r['name'],r['idx'],'known',known,'L',r['L'],'sgs_fixed',z[2] if z else None,'hitL',bool(z2))
