import sys, time
sys.path[:0]=['exp/v28','exp/v13','exp/v25']
import hybrid, sgs

def idp_certify(inst, rem, A, est, q, h, tau=4, b0=32, maxbudget=8192,
                stats=None):
    if stats is None: stats={}
    nrem=bin(rem).count('1')
    if nrem==0: return True
    if nrem>22: return None
    cp=max(est[i]+inst['p'][i]+q[i] for i in range(inst['n']) if (rem>>i)&1)
    S=h-cp; stats['cps_S']=S
    if S<0: return False
    if S>tau: return None
    full=all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']) if (rem>>i)&1)
    if not full: return None
    total_cps=0; total_os=0; rounds=0
    b=b0
    while b<=maxbudget:
        rounds+=1
        st={}
        v=hybrid.cps_probe(inst,rem,A,est,q,h,budget=b,stats=st)
        total_cps+=st.get('probe_nodes',0) or 0
        if v is not None:
            stats.update(idp_rounds=rounds,idp_cps=total_cps,idp_os=total_os,
                         idp_winner='cps',idp_b=b,probe_nodes=total_cps,
                         os_nodes=total_os,cps_res_nodes=total_cps+total_os)
            return v
        so={}
        vo,sch=sgs.sgs_solve(inst,h,rem=rem,A=A,est=est,q=q,nodecap=b,
                             dom=False,stats=so)
        total_os+=so.get('nodes',0)
        if vo is not None:
            stats.update(idp_rounds=rounds,idp_cps=total_cps,idp_os=total_os,
                         idp_winner='os',idp_b=b,probe_nodes=total_cps,
                         os_nodes=total_os,cps_res_nodes=total_cps+total_os)
            return vo
        b*=2
    stats.update(idp_rounds=rounds,idp_cps=total_cps,idp_os=total_os,
                 idp_winner=None,idp_b=b,probe_nodes=total_cps,os_nodes=total_os,
                 cps_res_nodes=total_cps+total_os)
    return None
