import sys, json, time
sys.path[:0]=['exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from search_hard import make_inst
import sage
from sage import lp_branch_decide
from cert import integer_certificate, verify
from sdecc import SDLP
from po import heads_tails

inst=make_inst(18,3,264,edgep=0.15,hetero=0.5)
calls=[]
orig=sage.integer_certificate
def wrap(inst,h,use_expect=False,use_dom=True,elig_aware=None,forbid=None,dens=None):
    c=orig(inst,h,use_expect=use_expect,use_dom=use_dom,elig_aware=elig_aware,forbid=forbid)
    calls.append((frozenset(forbid or ()), c is not None, c))
    return c
sage.integer_certificate=wrap
r=lp_branch_decide(inst,32,nodecap=10000,depthcap=100)
print('verdict',r['verdict'],'nodes',r['nodes'],'leaves',r['leaves'],'unknown',r['unknown'])
print('cert calls',len(calls),'fails',sum(1 for _,ok,_ in calls if not ok))
for F,ok,c in calls:
    if not ok:
        print('FAIL F size',len(F),'F',sorted(F)[:40],'...')
        n=inst['n'];m=inst['m']
        est,q=heads_tails(inst,0,[0]*n)
        elig=any(len(set(inst['elig'][i]))<m for i in range(n))
        lp=SDLP(inst,32,est,q,use_dom=True,elig_aware=elig,forbid=F)
        res=lp.solve()
        print('  rebuild LP status',res.status,'N',lp.N,'rows',lp.A.shape)
        # try direct lp solution with forbid and cert LP
        from cert import _farkas_lp
        if hasattr(lp,'A'):
            fr=_farkas_lp(lp)
            print('  farkas status',fr.status,'fun',fr.fun)
        # density ladder
        if fr.status==0:
            import numpy as np
            A=lp.A.tocsr(); meta=None
            for D in (1,2,3,4,5,6,10,12,20,60,100,240,1000,10000):
                y=np.rint(fr.x*D).astype(np.int64)
                ATy=A.T.dot(y); bt=int(lp.hi[lp.n_eq:].dot(y[lp.n_eq:]))+int(y[:lp.n_eq].sum())
                if ATy.min()>=0 and bt<0:
                    print('  D',D,'works')
                    break
            else:
                print('  no D works; min ATy',ATy.min(),'bt',bt,'frac',fr.x[:5])
        break
