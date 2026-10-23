import pickle,sys,time
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v24','exp/v25']
import po,cps_lib

def longest_chain(inst,rem,est,q):
    # longest path by number of vertices, tie-break by sum p, then est+p+q
    n=inst['n']; order=[]
    indeg={i:0 for i in range(n) if (rem>>i)&1}
    for i in indeg:
        for j in inst['succ'][i]:
            if (rem>>j)&1: indeg[j]+=1
    stack=[i for i in indeg if indeg[i]==0]
    while stack:
        u=stack.pop(); order.append(u)
        for v in inst['succ'][u]:
            if (rem>>v)&1:
                indeg[v]-=1
                if indeg[v]==0: stack.append(v)
    L={}; best={}
    for u in order:
        L[u]=1; best[u]=u
        for v in inst['pred'][u]:
            if (rem>>v)&1:
                if L[v]+1>L[u] or (L[v]+1==L[u] and inst['p'][v]+inst['p'][u]>0):
                    L[u]=L[v]+1; best[u]=v
    end=max((i for i in order), key=lambda i:(L[i], inst['p'][i]))
    path=[]; u=end
    while u is not None:
        path.append(u); u=best[u] if L[u]>1 else None
    path.reverse()
    return path

def eval_chain(inst,rem,A,est,q,h,chain,nodecap=300000,cap_places=100000):
    S=h-(est[chain[0]]+sum(inst['p'][i] for i in chain)+q[chain[-1]])
    if S<0: return dict(NO=True,S=S,nplace=0,nodes=0,feas=False,unk=False,time=0)
    nplace=0; nodes=0; feas=False; unk=False; t0=time.time()
    for g in cps_lib._compositions(S,len(chain)+1):
        s=[]; t=est[chain[0]]+g[0]; ok=True
        for a,i in enumerate(chain):
            if a>0: t=s[-1]+inst['p'][chain[a-1]]+g[a]
            if t<est[i] or t+inst['p'][i]>h-q[i]: ok=False; break
            s.append(t)
        if not ok: continue
        nplace+=1
        if nplace>cap_places: unk=True; break
        st={}
        rr=cps_lib._residual_feasible(inst,rem,A,est,q,h,chain,s,nodecap=nodecap,stats=st)
        nodes+=st.get('cps_res_nodes',0)
        if rr is True: feas=True; break
        if rr is None: unk=True
    return dict(NO=(not feas and not unk),S=S,nplace=nplace,nodes=nodes,feas=feas,unk=unk,time=time.time()-t0)

C=pickle.load(open('exp/v20/holdout_cases50.pkl','rb'))
for idx in [5,21,32,42,47]:
    inst,opt=C[idx]; h=opt-1; n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n); A=tuple([0]*inst['m']); rem=inst['full']
    crit,cp=cps_lib.critical_path(inst,rem,tuple(est),q)
    long=longest_chain(inst,rem,est,q)
    print('idx',idx,'n',n,'h',h,'cp',cp,'S_crit',h-cp,'crit L',len(crit),crit)
    print('   long L',len(long),'S',h-(est[long[0]]+sum(inst['p'][i] for i in long)+q[long[-1]]),long)
    for name,ch in [('crit',crit),('long',long)]:
        r=eval_chain(inst,rem,A,tuple(est),q,h,ch)
        print('   ',name,r)
