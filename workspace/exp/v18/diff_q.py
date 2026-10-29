import sys, random, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16'); sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18')
import po, pace_dbg

CFG=dict(mode='pot',mint_on=True,mint_depth=0,packset_on=True,packset_depth=0,
         sop_on=True,sop_nodecap=200000)

def gen(rng,n,m,pmax=9,ep=0.25,full=True):
    p=[rng.randint(2,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7: pred[j].append(rng.randrange(j))
    if full:
        elig=None
    else:
        elig=[]
        for i in range(n):
            e=[k for k in range(m) if rng.random()<0.72]
            if not e: e=[rng.randrange(m)]
            elig.append(e)
    return po.make_inst(p,m,pred,elig)

def check_sched(inst,h,out):
    n,p,m=inst['n'],inst['p'],inst['m']
    if out is None: return True
    if len(out)!=n: return False
    seen=set(); mach=[[] for _ in range(m)]; done={}
    for (i,k,t) in out:
        if i in seen: return False
        seen.add(i)
        if k not in inst['elig'][i]: return False
        if t<0 or t+p[i]>h: return False
        for j in inst['pred'][i]:
            if j not in done or done[j]>t: return False
        mach[k].append((t,t+p[i])); done[i]=t+p[i]
    for k in range(m):
        iv=sorted(mach[k])
        for a,b in zip(iv,iv[1:]):
            if a[1]>b[0]: return False
    return len(seen)==n

def solve(inst,h,q,cap=300000):
    fe=all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
    kw=dict(omd=fe)
    if q: kw.update(odom=True,hpack_on=True)
    (ok,out),st=pace_dbg.decide(inst,h,nodecap=cap,**CFG,**kw)
    return ok,out,st

def main(N=3000,seed=999,full=True):
    rng=random.Random(seed); t0=time.time(); tested=0; bad=0; to=0
    while tested<N:
        n=rng.randint(5,10); m=rng.choice([2,3])
        inst=gen(rng,n,m,full=full)
        est,q=po.heads_tails(inst,0,[0]*n)
        lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),
               (sum(inst['p'])+m-1)//m,max(inst['p']))
        opt=None
        for h in range(lo,lo+9):
            ok,_,st=solve(inst,h,False)
            if st.get('timeout'): break
            if ok: opt=h; break
        if opt is None: to+=1; continue
        for h in (opt-1,opt):
            b,bo,sb=solve(inst,h,False)
            q2,qo,sq=solve(inst,h,True)
            if sb.get('timeout') or sq.get('timeout'): to+=1; continue
            okq = q2 and check_sched(inst,h,qo)
            if b!=q2 or (q2 and not okq):
                bad+=1
                print('MISMATCH full=%s n=%d m=%d h=%d base=%s q=%s schedok=%s'%(full,n,m,h,b,q2,okq))
                print('p',inst['p']); print('pred',inst['pred']); print('elig',inst['elig'])
                print('base_out',bo); print('q_out',qo); print('opt',opt)
                if bad>=3: return
        tested+=1
        if tested%500==0:
            print('tested',tested,'bad',bad,'to',to,'t',round(time.time()-t0,1),flush=True)
    print('DONE tested',tested,'bad',bad,'timeouts',to,'t',round(time.time()-t0,1))

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--N',type=int,default=3000)
    ap.add_argument('--seed',type=int,default=999); ap.add_argument('--het',action='store_true')
    a=ap.parse_args(); main(a.N,a.seed,not a.het)
