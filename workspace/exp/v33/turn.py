"""TURN: time-reversal dual WOS + Hall certificate + learned direction selector."""
import sys, json, math, time
sys.path[:0]=['exp/v33','exp/v31','exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v25']
import po, icc, hec
import wos
import pace_v25 as P

SEL=json.load(open('exp/v33/selector_clean.json'))

PACE_CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
              packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000,
              dhd=True,dcd=True,hpack_on=True,odom=False,
              map_on=True,map_tau=4,map_ncap=16,
              cps_on=True,cps_tau=4,cps_depth=0,cps_ncap=16,
              cps_nodecap=300000,cps_gate_fan=0)

def topo(inst):
    n=inst['n']; indeg=[len(inst['pred'][i]) for i in range(n)]
    st=[i for i in range(n) if indeg[i]==0]; out=[]
    while st:
        i=st.pop(); out.append(i)
        for j in inst['succ'][i]:
            indeg[j]-=1
            if indeg[j]==0: st.append(j)
    if len(out)!=n: raise ValueError('cycle')
    return out

def rev_inst(inst):
    n=inst['n']; m=inst['m']; o=topo(inst); pos={v:k for k,v in enumerate(o)}
    rp={i:n-1-pos[i] for i in range(n)}
    pr=[[] for _ in range(n)]
    for i in range(n): pr[rp[i]]=sorted(rp[j] for j in inst['succ'][i])
    pp=[0]*n; E=[None]*n
    for i in range(n): pp[rp[i]]=inst['p'][i]; E[rp[i]]=inst['elig'][i]
    return po.make_inst(pp,m,pr,E), rp

def static_feats(inst,h,est,q):
    n=inst['n']; m=inst['m']; p=inst['p']; xs=[n,m]
    for arr in (p,est,q):
        mu=sum(arr)/n; sd=(sum((v-mu)**2 for v in arr)/n)**0.5
        xs += [mu,sd,max(arr),min(arr)]
    xs += [sum(len(inst['pred'][i]) for i in range(n))/n,
           sum(1 for i in range(n) if not inst['pred'][i]),
           sum(1 for i in range(n) if not inst['succ'][i]),
           max(est[i]+p[i]+q[i] for i in range(n)), h,
           h-max(est[i]+p[i]+q[i] for i in range(n))]
    return xs

def select(inst,h,est,q):
    x=static_feats(inst,h,est,q)
    z=[(x[j]-SEL['mu'][j])/SEL['sd'][j] for j in range(20)]
    if SEL['kind']=='logit':
        v=sum(SEL['w'][j]*z[j] for j in range(20))+SEL['b']
        p=1/(1+math.exp(-max(-30,min(30,v))))
    else:
        W1,b1,W2,b2=SEL['W1'],SEL['b1'],SEL['W2'],SEL['b2']
        hh=[math.tanh(sum(W1[k][j]*z[j] for j in range(20))+b1[k]) for k in range(len(W2))]
        v=sum(W2[k]*hh[k] for k in range(len(W2)))+b2
        p=1/(1+math.exp(-max(-30,min(30,v))))
    return p

def solve_dir(inst,h,est,q,backward,nodecap,stats=None):
    if not backward:
        return wos.sgs_solve(inst,h,rem=inst['full'],A=tuple([0]*inst['m']),
                             est=est,q=q,nodecap=nodecap,rsi=True,force=True,
                             order='lpt',stats=stats)
    r,rpos=rev_inst(inst)
    er,qr=po.heads_tails(r,0,[0]*r['n'])
    ok,sched=wos.sgs_solve(r,h,rem=r['full'],A=tuple([0]*r['m']),
                           est=er,q=qr,nodecap=nodecap,rsi=True,force=True,
                           order='lpt',stats=stats)
    if ok and sched:
        # map back: rev task rt = rpos[orig]; start_orig = h - (start_rev + p)
        inv={v:k for k,v in rpos.items()}
        so={}
        for rt,t in sched.items():
            i=inv[rt]; so[i]=h-(t+inst['p'][i])
        sched=so
    return ok,sched

def bb_solve(inst,h,os_ncap=10000,pmax=16,tau=4,stats=None,use_hec=True,
             use_sel=True,force_dir=None,pace_cfg=None,icc_util_gate=None):
    if stats is None: stats={}
    n,m=inst['n'],inst['m']
    full=all(len(set(inst['elig'][i]))==m for i in range(n))
    est,q=po.heads_tails(inst,0,[0]*n)
    cp=max(est[i]+inst['p'][i]+q[i] for i in range(n)); S=h-cp
    stats.update(S=S,full=full,gate=(full and n<=pmax and 0<=S<=tau))
    t0=time.time()
    if use_hec and not full and not hec.check(inst,h,est,q,stats):
        stats['verdict']='HEC'; stats['t']=time.time()-t0; return False,stats
    util=sum(inst['p'])/(m*h) if h>0 else 0.0
    if full and (icc_util_gate is None or util>=icc_util_gate):
        ok,w=icc.icc(inst,inst['full'],tuple([0]*m),est,q,h,stats=stats)
        if not ok:
            stats['verdict']='ICC'; stats['cert']=w; stats['t']=time.time()-t0
            return False,stats
    if full and n<=pmax and 0<=S<=tau:
        p=select(inst,h,est,q) if use_sel else 0.0
        backward=(force_dir=='b') if force_dir else (p>SEL['th'])
        stats['p_bwd']=p; stats['dir']='B' if backward else 'F'
        so={}
        ok,sched=solve_dir(inst,h,est,q,backward,os_ncap,so)
        stats['os_nodes']=so.get('nodes',0); stats['os_memo']=so.get('memo',0)
        if ok is not None:
            stats['verdict']='OS-'+stats['dir']; stats['t']=time.time()-t0
            return ok,stats
    if use_hec and not full:
        cfg=dict(pace_cfg or PACE_CFG); cfg['map_on']=False
    else:
        cfg=dict(pace_cfg or PACE_CFG); cfg['omd']=full
    st2={}
    (ok,_),st2=P.decide(inst,h,stats=st2,**cfg)
    stats['pace_nodes']=st2.get('nodes'); stats['verdict']='PACE'
    stats['t']=time.time()-t0
    return ok,stats
