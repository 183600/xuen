import sys,pickle,random,time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
import po, mint, pace_i, order_sop as sop

def get_mint(inst,h):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    (ok,out),st=pace_i.decide(inst,h,mode='pot',nodecap=2000000,
                              mint_on=True,mint_depth=0,packset_on=False)
    w=st.get('root_wit')
    if not w or w[0]!='mint': return None
    S,W,cp=w[1],w[2],w[3]
    r=list(est); d=[h-q[i] for i in range(n)]; ps=inst['p']
    beta=[mint.beta(i,ps,r,d,S) for i in range(n)]
    return S,beta,cp

def walk(inst,h,S,beta,cap0,rng,steps=40):
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q0=po.heads_tails(inst,0,[0]*n)
    r0=list(est); d0=[h-q0[i] for i in range(n)]
    rem=inst['full']; A=[0]*m; est=list(est); sched=[]
    bad=0; checks=0
    for _ in range(steps):
        if rem==0: break
        q=po.tails(inst,rem)
        ready=[i for i in po.bititer(rem) if not (inst['pmask'][i]&rem)]
        opts=[]
        for i in ready:
            for k in inst['elig'][i]:
                t=max(A[k],est[i])
                if t+p[i]+q[i]<=h: opts.append((i,k,t))
        if not opts: break
        i,k,t=rng.choice(opts)
        sched.append((i,k,t))
        A=list(A); A[k]=t+p[i]
        nest=list(est)
        for j in inst['succ'][i]:
            if (rem>>j)&1 and t+p[i]>nest[j]: nest[j]=t+p[i]
        est=nest; rem&=~(1<<i)
        # invariant
        L=0.0
        for (j,kj,tj) in sched:
            L+=sum(max(0,min(tj+p[j],b)-max(tj,a)) for a,b in S)
        for j in po.bititer(rem):
            # beta at the current state (r=est_j, d=d0_j)
            bj=mint.beta(j,p,list(est),d0,S)
            if bj+1e-9<beta[j]:
                bad+=1
            L+=bj
        cap=sum(max(0,b-max(a,A[k])) for a,b in S for k in range(m))
        checks+=1
        if L<=cap+1e-9: bad+=1
    return checks,bad

if __name__=='__main__':
    rng=random.Random(5)
    d=pickle.load(open('exp/v13/hard3.pkl','rb'))
    tot=0; bad=0
    for idx in [3,10]:
        rec=d[idx]; inst,opt=rec[0],rec[1]; h=opt-1
        got=get_mint(inst,h)
        if not got:
            print('no mint',idx); continue
        S,beta,cap0=got
        print('hard3#%d S=%s cap=%d beta_sum=%d'%(idx,S,cap0,sum(beta)))
        for trial in range(300):
            c,b=walk(inst,h,S,beta,cap0,rng)
            tot+=c; bad+=b
    print('carry checks',tot,'violations',bad)
