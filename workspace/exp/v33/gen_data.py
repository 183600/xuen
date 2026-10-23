import sys, random, time, pickle
sys.path[:0]=['exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v25']
import po, wos

def gen(rng,n,m):
    p=[rng.randint(2,9) for _ in range(n)]
    pred=[[] for _ in range(n)]
    ep=rng.choice([0.18,0.22,0.28,0.35])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j]: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)

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

def run(inst,h,cap=200000):
    st={}; ok,_=wos.sgs_solve(inst,h,nodecap=cap,stats=st)
    return ok, st

def opt_wos(inst,cap=200000):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(est[i]+inst['p'][i]+q[i] for i in range(n)); hi=lo+sum(inst['p'])
    def ok(h):
        st={}; r,_=wos.sgs_solve(inst,h,nodecap=cap,stats=st); return r is True
    h=lo
    while h<=hi:
        if ok(h): break
        h=lo+(h-lo+1)*2 if h>lo else lo+1
    if h>hi: return None
    lo2,hi2=lo,h
    while lo2<hi2:
        mid=(lo2+hi2)//2
        if ok(mid): hi2=mid
        else: lo2=mid+1
    return lo2

def feats(inst,h,est,q,sf,sb):
    n=inst['n']; m=inst['m']; p=inst['p']
    xs=[]
    for x in (n,m):
        xs.append(x)
    for arr in (p,est,q):
        xs += [sum(arr)/n, (sum((v-sum(arr)/n)**2 for v in arr)/n)**0.5, max(arr), min(arr)]
    xs += [sum(len(inst['pred'][i]) for i in range(n))/n,
           sum(1 for i in range(n) if not inst['pred'][i]),
           sum(1 for i in range(n) if not inst['succ'][i]),
           max(est[i]+p[i]+q[i] for i in range(n)),
           h,
           h-max(est[i]+p[i]+q[i] for i in range(n))]
    return xs

rng=random.Random(20261023)
rows=[]; t0=time.time(); tried=0
while len(rows)<600 and tried<5000:
    tried+=1
    n=rng.randint(10,16); inst=gen(rng,n,3)
    o=opt_wos(inst)
    if o is None: continue
    if o<3: continue
    r=rev(inst)
    for hmod in (-1,0):
        h=o+hmod
        if h<1: continue
        okf,sf=run(inst,h); okb,sb=run(r,h)
        if okf!=okb: continue
        if sf['nodes']>=200000 or sb['nodes']>=200000: continue
        rows.append(dict(n=n,opt=o,h=h,hmod=hmod,f=sf['nodes'],b=sb['nodes'],
                         mf=sf.get('memo'),mb=sb.get('memo'),
                         rf=sf.get('rsi_hits'),rb=sb.get('rsi_hits'),
                         ff=sf.get('forced'),fb=sb.get('forced'),
                         nnf=sf.get('nodes'),nnb=sb.get('nodes'),
                         feat=feats(inst,h,po.heads_tails(inst,0,[0]*n)[0],po.heads_tails(inst,0,[0]*n)[1],sf,sb)))
print('rows',len(rows),'tried',tried,'time',round(time.time()-t0,2))
pickle.dump(rows,open('exp/v33/train.pkl','wb'))
print('NO fwd/bwd',sum(x['f'] for x in rows if x['hmod']==-1),sum(x['b'] for x in rows if x['hmod']==-1))
print('YES fwd/bwd',sum(x['f'] for x in rows if x['hmod']==0),sum(x['b'] for x in rows if x['hmod']==0))
