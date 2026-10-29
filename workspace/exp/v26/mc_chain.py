import pickle,sys,random,time
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v24','exp/v25']
import po,cps_lib
C=pickle.load(open('exp/v20/holdout_cases50.pkl','rb'))

def topo(inst,rem):
    n=inst['n']; indeg=[0]*n; nodes=[i for i in range(n) if (rem>>i)&1]
    for i in nodes:
        for j in inst['succ'][i]:
            if (rem>>j)&1: indeg[j]+=1
    q=[i for i in nodes if indeg[i]==0]; out=[]
    while q:
        u=q.pop(); out.append(u)
        for v in inst['succ'][u]:
            if (rem>>v)&1:
                indeg[v]-=1
                if indeg[v]==0: q.append(v)
    return out

def rand_chain(inst,rem,rng,lam=1.0):
    order=topo(inst,rem); w={i:rng.random()*lam+0.001*inst['p'][i] for i in order}
    best={}; par={}
    for u in order:
        best[u]=w[u]; par[u]=None
        for v in inst['pred'][u]:
            if (rem>>v)&1 and best[v]+w[u]>best[u]:
                best[u]=best[v]+w[u]; par[u]=v
    end=max(order,key=lambda i:best[i]); path=[]
    while end is not None: path.append(end); end=par[end]
    return path[::-1]

def placements(inst,rem,A,est,q,h,chain):
    S=h-(est[chain[0]]+sum(inst['p'][i] for i in chain)+q[chain[-1]])
    out=[]
    if S<0: return out
    for g in cps_lib._compositions(S,len(chain)+1):
        s=[]; t=est[chain[0]]+g[0]; ok=True
        for a,i in enumerate(chain):
            if a>0: t=s[-1]+inst['p'][chain[a-1]]+g[a]
            if t<est[i] or t+inst['p'][i]>h-q[i]: ok=False; break
            s.append(t)
        if ok: out.append(tuple(s))
    return out

def eval_chain(inst,rem,A,est,q,h,chain,nodecap):
    ps=placements(inst,rem,A,est,q,h,chain); mx=0; tot=0; anyunk=False
    for s in ps:
        st={}
        rr=cps_lib._residual_feasible(inst,rem,A,est,q,h,list(chain),list(s),nodecap=nodecap,stats=st)
        nd=st.get('cps_res_nodes',0); mx=max(mx,nd); tot+=nd
        if rr is True: return dict(v='FEAS',mx=mx,tot=tot,np=len(ps))
        if rr is None: anyunk=True
    return dict(v='UNK' if anyunk else 'NO',mx=mx,tot=tot,np=len(ps))

for idx in [21,47]:
    inst,opt=C[idx]; h=opt-1; n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n); A=tuple([0]*inst['m']); rem=inst['full']
    rng=random.Random(1234); hits=0; tries=30; best=None
    t0=time.time()
    for k in range(tries):
        ch=rand_chain(inst,rem,rng,lam=2.0)
        r=eval_chain(inst,rem,A,tuple(est),q,h,ch,4000)
        if r['v']=='NO':
            hits+=1
            if best is None or r['mx']<best[1]['mx']: best=(ch,r)
    print('idx',idx,'random chains NO under cap4000',hits,'/',tries,'best',best,'sec',round(time.time()-t0,2),flush=True)
