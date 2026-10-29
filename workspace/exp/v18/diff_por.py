import sys, random, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18')
import po, pace_dbg

def gen(rng,n,m,pmax=9,ep=0.25,full=True):
    p=[rng.randint(2,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7: pred[j].append(rng.randrange(j))
    elig=None if full else [[k for k in range(m) if rng.random()<0.75] or [rng.randrange(m)] for _ in range(n)]
    return po.make_inst(p,m,pred,elig)

def check_sched(inst,h,out):
    n,p,m=inst['n'],inst['p'],inst['m']
    if out is None: return True
    if len(out)!=n: return False
    seen=set(); mach=[[] for _ in range(m)]
    done={}
    for (i,k,t) in out:
        if i in seen: return False
        seen.add(i)
        if k not in inst['elig'][i]: return False
        if t<0 or t+p[i]>h: return False
        for j in inst['pred'][i]:
            if j not in done or done[j] > t: return False
        mach[k].append((t,t+p[i],i))
        done[i]=t+p[i]
    for k in range(m):
        iv=sorted(mach[k])
        for a,b in zip(iv,iv[1:]):
            if a[1]>b[0]: return False
    return len(seen)==n

def solve(inst,h,**kw):
    try:
        (ok,out),st=pace_dbg.decide(inst,h,mode='pot',nodecap=200000,
            mint_on=False,packset_on=False,sop_on=False,**kw)
    except TimeoutError:
        return None,None
    if st.get('timeout'): return None,None
    return ok,out

def main(N=4000,seed=12345,full=True,verbose=True):
    rng=random.Random(seed)
    t0=time.time(); tested=0; bad=0; timeouts=0
    while tested<N:
        n=rng.randint(5,10); m=rng.choice([2,3])
        inst=gen(rng,n,m,full=full)
        est,q=po.heads_tails(inst,0,[0]*n)
        lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),
               (sum(inst['p'])+m-1)//m,max(inst['p']))
        opt=None
        for h in range(lo,lo+8):
            ok,_=solve(inst,h)
            if ok is None: break
            if ok: opt=h; break
        if opt is None:
            timeouts+=1; continue
        for h in (opt-1,opt):
            b,bo=solve(inst,h,omd=True,por=False)
            r,ro=solve(inst,h,omd=True,por=True,tsym=True)
            if b is None or r is None:
                timeouts+=1; continue
            if b!=r or (r and not check_sched(inst,h,ro)):
                bad+=1
                print('MISMATCH full=%s n=%d m=%d h=%d base=%s por=%s'%(full,n,m,h,b,r))
                print('p',inst['p']); print('pred',inst['pred']); print('opt',opt)
                print('base_out',bo); print('por_out',ro)
                if bad>=5: return
        tested+=1
        if verbose and tested%500==0:
            print('tested',tested,'bad',bad,'timeouts',timeouts,'t',round(time.time()-t0,1),flush=True)
    print('DONE tested',tested,'bad',bad,'timeouts',timeouts,'t',round(time.time()-t0,1))

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--N',type=int,default=4000)
    ap.add_argument('--seed',type=int,default=12345); ap.add_argument('--het',action='store_true')
    a=ap.parse_args(); main(a.N,a.seed,not a.het)
