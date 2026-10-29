import sys, pickle, time
sys.path[:0]=['exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v25']
import po, wos

def topo(inst):
    n=inst['n']; indeg=[len(inst['pred'][i]) for i in range(n)]
    st=[i for i in range(n) if indeg[i]==0]; out=[]
    while st:
        i=st.pop(); out.append(i)
        for j in inst['succ'][i]:
            indeg[j]-=1
            if indeg[j]==0: st.append(j)
    return out

def rev(inst):
    n=inst['n']; m=inst['m']; o=topo(inst); pos={v:k for k,v in enumerate(o)}
    rp={i:n-1-pos[i] for i in range(n)}
    pr=[[] for _ in range(n)]
    for i in range(n): pr[rp[i]]=sorted(rp[j] for j in inst['succ'][i])
    pp=[0]*n; E=[None]*n
    for i in range(n): pp[rp[i]]=inst['p'][i]; E[rp[i]]=inst['elig'][i]
    return po.make_inst(pp,m,pr,E)

def run(inst,h,cap):
    st={}; ok,_=wos.sgs_solve(inst,h,nodecap=cap,stats=st)
    return ok,st

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

def one(inst,h):
    est,q=po.heads_tails(inst,0,[0]*inst['n']); r=rev(inst)
    okf,sf=run(inst,h,10**7); okb,sb=run(r,h,10**7)
    okpf,pf=run(inst,h,100); okpb,pb=run(r,h,100)
    x=static_feats(inst,h,est,q)
    # probe derived
    x += [pf.get('memo',0),pb.get('memo',0),pf.get('rsi_hits',0),pb.get('rsi_hits',0),
          pf.get('forced',0),pb.get('forced',0),pf.get('nodes',100),pb.get('nodes',100)]
    return dict(f=sf['nodes'],b=sb['nodes'],h=h,okf=okf,okb=okb,x=x)

if __name__=='__main__':
    D=pickle.load(open('exp/v20/holdout_cases50.pkl','rb'))
    out=[]
    for inst,opt in D:
        for hmod in (-1,0):
            out.append(one(inst,opt+hmod))
    pickle.dump(out,open('exp/v33/holdout_feats.pkl','wb'))
    print('done',len(out))
    print('NO totals',sum(x['f'] for x in out if x['h']==sum([])), 'n', len(out))
