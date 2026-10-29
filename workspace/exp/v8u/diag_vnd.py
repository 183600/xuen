import sys, time, collections
sys.path[:0] = ['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from lpr import _pin_weak, _guide_at, sgs
from lbp import ParametricSD
from pdicf import decode_orders, decode_random
from rdf import check_schedule
from asr import base_orders, topo_ok

def improve(inst, ps, res, L, U, max_iter=6, width=3):
    n=inst['n']; work=0
    pool=[]
    for tag,o in base_orders(inst,ps,res,use_cfa=True):
        r=sgs(inst,o,None); work+=1
        if not r: continue
        s,m,c=r
        if not check_schedule(inst,c,s,m): continue
        if c<=L: return ('base:'+tag,c,work)
        pool.append((c,tag,o))
    pool.sort(key=lambda x:x[0]); pool=pool[:width]
    best=pool[0][0] if pool else None
    for it in range(max_iter):
        cand=None
        for c0,tag,o in pool:
            pos0=[0]*n
            for k,v in enumerate(o): pos0[v]=k
            for i in range(n):
                pos=pos0[i]; rem=o[:pos]+o[pos+1:]
                for j in range(pos+1,n):
                    o2=rem[:j]+[i]+rem[j:]
                    if not topo_ok(inst,o2): continue
                    work+=1
                    r=sgs(inst,o2,None)
                    if r is None: continue
                    s,m,c=r
                    if not check_schedule(inst,c,s,m): continue
                    if c<=L: return ('vnd:%s:%d'% (tag,it+1),c,work)
                    if cand is None or c<cand[0]: cand=(c,tag,o2)
        if cand is None or cand[0]>=best: break
        best=cand[0]; pool=[cand]
    return (None,best,work)

instances=[]
for k,(corp,name,idx,inst,known,init) in enumerate(weak_rows(4)):
    L0,U0,s0,m0,proof0=init
    co,L,U,s,m,proof,pin_lp=_pin_weak(inst,L0,U0,s0,m0,proof0)
    ps,guide,extra=_guide_at(co,L)
    if ps is None or guide is None: ps=ParametricSD(inst,int(U)); guide=ps.solve_h(L)
    r=decode_orders(inst,ps,guide,L,use_cfa=True)
    if r['hit']: continue
    r2=decode_random(inst,ps,guide,L,restarts=50,seed=k)
    if r2['hit']: continue
    instances.append((k,name,idx,inst,L,U,ps,guide))
print('residual',len(instances))
t0=time.time(); stats=collections.Counter(); rows=[]
for k,name,idx,inst,L,U,ps,guide in instances:
    kind,c,w=improve(inst,ps,guide,L,U)
    stats['hit' if kind else 'miss']+=1; stats['work']+=w
    if kind: rows.append((k,name,idx,L,U,kind,c,w))
print(stats,'t',round(time.time()-t0,2))
for x in rows: print(x)
