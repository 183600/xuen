import sys, random, json, time, pickle
sys.path.insert(0,'exp/v13')
import po

def gen(rng, n, m, pmax=10, ep=0.18, elig_p=1.0):
    p=[rng.randint(2,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep:
                pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7:
            pred[j].append(rng.randrange(j))
    if elig_p>=1.0:
        elig=[list(range(m)) for _ in range(n)]
    else:
        elig=[]
        for i in range(n):
            e=[k for k in range(m) if rng.random()<elig_p]
            if not e: e=[rng.randrange(m)]
            elig.append(e)
    return po.make_inst(p,m,pred,elig)

if __name__=='__main__':
    rng=random.Random(2024)
    out=[]
    while len(out)<12:
        n=rng.randint(12,16); m=3
        inst=gen(rng,n,m)
        est,q=po.heads_tails(inst,0,[0]*n)
        lo=max(est[i]+inst['p'][i]+q[i] for i in range(n))
        lo=max(lo,(sum(inst['p'])+m-1)//m,max(inst['p']))
        # quick feasibility at lo
        opt=None
        for h in range(lo,lo+8):
            (ok,_),st=po.decide(inst,h,mode='plain',nodecap=400_000)
            if st.get('timeout'): break
            if ok: opt=h; break
        if opt is None: continue
        # only keep if proving opt-1 is nontrivial
        (ok,_),st=po.decide(inst,opt-1,mode='plain',nodecap=400_000)
        if st.get('timeout') or st['nodes']<3000: continue
        out.append((inst,opt,st['nodes']))
        print('kept',len(out),'n',n,'opt',opt,'nodes',st['nodes'],flush=True)
    pickle.dump(out,open('v13/hard3.pkl','wb'))
    print('saved')
