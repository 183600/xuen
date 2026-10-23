import sys, time
sys.path[:0]=['exp/v28','exp/v13','exp/v20','exp/v25']
import po, hybrid

def root_hy(inst,h,probe=300,os_ncap=10000,stats=None):
    if stats is None: stats={}
    n=inst['n']; m=inst['m']
    full=all(len(set(inst['elig'][i]))==m for i in range(n))
    est,q=po.heads_tails(inst,0,[0]*n)
    cp=max(est[i]+inst['p'][i]+q[i] for i in range(n))
    S=h-cp
    stats.update(S=S,full=full,gate=(full and n<=22 and 0<=S<=4))
    if not (full and n<=22 and 0<=S<=4): return None,est,q
    t=time.time()
    v=hybrid.hybrid_certify(inst,inst['full'],tuple([0]*m),est,q,h,tau=4,
                            probe=probe,os_ncap=os_ncap,stats=stats)
    stats['root_time']=time.time()-t
    return v,est,q
