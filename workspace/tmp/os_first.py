import sys, time
sys.path[:0]=['exp/v28','exp/v13','exp/v20','exp/v25']
import po, sgs

def os_first(inst,h,B=10000,tau=4,nmax=16,stats=None):
    if stats is None: stats={}
    n=inst['n']; m=inst['m']
    full=all(len(set(inst['elig'][i]))==m for i in range(n))
    est,q=po.heads_tails(inst,0,[0]*n)
    cp=max(est[i]+inst['p'][i]+q[i] for i in range(n))
    S=h-cp
    stats.update(osf_S=S,osf_full=full,osf_gate=(full and n<=nmax and S<=tau))
    if not (full and n<=nmax and S<=tau): return None,est,q
    st={}; t=time.time()
    v,_=sgs.sgs_solve(inst,h,est=est,q=q,nodecap=B,stats=st)
    stats['osf_nodes']=st.get('nodes'); stats['osf_time']=time.time()-t
    return v,est,q
