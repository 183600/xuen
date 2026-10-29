import sys, random, json, time, pickle
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14')
import po, pace

def gen(rng,n,m,pmax=10,ep=0.2,elig_p=1.0):
    p=[rng.randint(2,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7: pred[j].append(rng.randrange(j))
    if elig_p>=1.0:
        elig=[list(range(m)) for _ in range(n)]
    else:
        elig=[]
        for i in range(n):
            e=[k for k in range(m) if rng.random()<elig_p]
            if not e: e=[rng.randrange(m)]
            elig.append(e)
    return po.make_inst(p,m,pred,elig)

def opt_of(inst, lo, hi, mode='sub', cap=300000):
    best=None
    for h in range(lo,hi+1):
        (ok,_),st=po.decide(inst,h,mode=mode,nodecap=cap)
        if st.get('timeout'): return None,None
        if ok: return h,st['nodes']
    return None,None

if __name__=='__main__':
    seed=int(sys.argv[1]); nlo=int(sys.argv[2]); nhi=int(sys.argv[3]); target=int(sys.argv[4])
    ep=float(sys.argv[5]); out=sys.argv[6]
    rng=random.Random(seed); res=[]
    t0=time.time()
    tries=0
    while len(res)<target and tries<400 and time.time()-t0<600:
        tries+=1
        n=rng.randint(nlo,nhi); m=3
        inst=gen(rng,n,m,ep=ep)
        est,q=po.heads_tails(inst,0,[0]*n)
        lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),
               (sum(inst['p'])+m-1)//m, max(inst['p']))
        opt,_=opt_of(inst,lo,lo+12)
        if opt is None: continue
        (ok,_),st=po.decide(inst,opt-1,mode='sub',nodecap=300000)
        if st.get('timeout'): continue
        pot=pace.potential(inst,inst['full'],(0,)*m,tuple(est),q,opt-1,
                           slack_cap=10**9) if False else None
        e2,q2=po.heads_tails(inst,0,[0]*n)
        pok,phi,wit=pace.potential(inst,inst['full'],(0,)*m,tuple(e2),q2,opt-1,slack_cap=10**9)
        res.append({'inst':inst,'opt':opt,'sub_nodes':st['nodes'],'pot_root':(not pok),
                    'wit':wit if not pok else None,'n':n,'ep':ep})
        print('kept',len(res),'n',n,'opt',opt,'sub',st['nodes'],'potroot',not pok,
              't',round(time.time()-t0,1),flush=True)
    pickle.dump(res,open(out,'wb'))
    print('saved',len(res),'tries',tries)
