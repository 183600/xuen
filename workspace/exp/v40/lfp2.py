"""Optimized layered frontier prover (LFP2)."""
import sys, time
sys.path[:0] = ['exp/v13']
import po

def lfp_solve(inst,h,force=True,rsi=True,nodecap=10**7,stats=None,est_in=None,q_in=None):
    n,m,p=inst['n'],inst['m'],inst['p']
    cw=max(1,m.bit_length())
    if est_in is None:
        est,q=po.heads_tails(inst,0,[0]*n)
    else:
        est,q=est_in,q_in
    rw=max(1,max([h]+list(est)).bit_length()); rmask=(1<<rw)-1
    d=[h-q[i] for i in range(n)]
    full=(1<<n)-1
    predm=[0]*n
    for i in range(n):
        for j in inst['pred'][i]: predm[i]|=1<<j
    succ=[list(inst['succ'][i]) for i in range(n)]
    ones=((1<<(cw*h))-1)//((1<<cw)-1)
    cp0=m*ones
    rp0=0
    for i in range(n): rp0|=est[i]<<(rw*i)
    rep=[0]*(max(p)+2)
    for k in range(1,len(rep)): rep[k]=(rep[k-1]<<cw)|1
    ks=cw*h; cpmask=(1<<ks)-1
    layers=[{} for _ in range(n+1)]
    layers[0][full]={cp0|(rp0<<ks)}
    expanded=0; peak=0; forced_n=0; rsi_n=0; found=False
    cache={}
    pp=p; dd=d; ss=succ; rr_rep=rep; rw_rw=rw; rmask_r=rmask
    def rdy_of(mask):
        r=cache.get(mask)
        if r is None:
            r=0; mm=mask
            while mm:
                b=mm&-mm; i=b.bit_length()-1; mm^=b
                if not (predm[i]&mask): r|=b
            cache[mask]=r
        return r
    for k in range(n):
        cur=layers[k]
        if not cur: continue
        L=sum(len(v) for v in cur.values())
        if L>peak: peak=L
        for mask0,bag in cur.items():
            ready=rdy_of(mask0)
            for ckey in bag:
                expanded+=1
                if expanded>nodecap: raise TimeoutError
                cp=ckey&cpmask; rp=ckey>>ks; mask=mask0
                while True:
                    if mask==0: found=True; break
                    av=cp
                    s=1
                    while s<cw:
                        av|=cp>>s; s+=1
                    av&=ones
                    cand=[]; fi=-1
                    r=ready if mask==mask0 else rdy_of(mask)
                    while r:
                        lb=r&-r; i=lb.bit_length()-1; r^=lb
                        pi=pp[i]; ri=(rp>>(rw_rw*i))&rmask_r; last=dd[i]-pi
                        t=-1
                        if last>=ri:
                            x=av>>(cw*ri)
                            if x:
                                rrr=x; LL=1; ok=True
                                while 2*LL<=pi:
                                    rrr&=rrr>>(cw*LL)
                                    if not rrr: ok=False; break
                                    LL<<=1
                                if ok and LL<pi: rrr&=rrr>>(cw*(pi-LL))
                                if ok and rrr:
                                    t=ri+(((rrr&-rrr).bit_length()-1)//cw)
                                    if t>last: t=-1
                        if t<0:
                            if rsi: rsi_n+=1
                            cand=None; break
                        cand.append((i,t))
                        if t==last: fi=i; break
                    if cand is None: break
                    if not force or fi<0:
                        for i,t in cand:
                            pi=pp[i]
                            ncp=cp-(rr_rep[pi]<<(cw*t))
                            nrp=rp & ~(rmask_r<<(rw_rw*i)); bad=False
                            for j in ss[i]:
                                if (mask>>j)&1:
                                    old=(nrp>>(rw_rw*j))&rmask_r; new=t+pi
                                    if new>old:
                                        nrp+=(new-old)<<(rw_rw*j)
                                        if new+pp[j]>dd[j]: bad=True
                            if bad: continue
                            nmask=mask^(1<<i)
                            nk=n-nmask.bit_count()
                            layers[nk].setdefault(nmask,set()).add(ncp|(nrp<<ks))
                        break
                    i=fi; t=dd[i]-pp[i]; pi=pp[i]
                    cp=cp-(rr_rep[pi]<<(cw*t))
                    nrp=rp & ~(rmask_r<<(rw_rw*i)); bad=False
                    for j in ss[i]:
                        if (mask>>j)&1:
                            old=(nrp>>(rw_rw*j))&rmask_r; new=t+pi
                            if new>old:
                                nrp+=(new-old)<<(rw_rw*j)
                                if new+pp[j]>dd[j]: bad=True
                    if bad:
                        rsi_n+=1; break
                    rp=nrp; mask^=(1<<i); forced_n+=1
        layers[k]=None
    ok=found or any(bool(v) for v in layers[n].values())
    if stats is not None: stats.update(expanded=expanded,peak=peak,forced=forced_n,rsi=rsi_n)
    return ok,None

def solve(inst,h,dir='backward',est_in=None,q_in=None,**kw):
    if dir=='forward': return lfp_solve(inst,h,est_in=est_in,q_in=q_in,**kw)
    n=inst['n']; z=dict(inst)
    z['pred']=[list(inst['succ'][i]) for i in range(n)]
    z['succ']=[list(inst['pred'][i]) for i in range(n)]
    if est_in is None: est,q=po.heads_tails(inst,0,[0]*n)
    else: est,q=est_in,q_in
    return lfp_solve(z,h,est_in=q,q_in=est,**kw)
