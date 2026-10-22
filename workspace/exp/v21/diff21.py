"""Differential: v2.0 (DHD) vs v2.1 (DHD + rigid RPD), same core."""
import sys,random,json,time
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v21']
import po,pace_v20,pace_v21
def gen(rng,n,m,het):
    p=[rng.randint(2,9) for _ in range(n)]
    pred=[[] for _ in range(n)]
    ep=rng.choice([0.15,0.25,0.35,0.5])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j] and rng.random()<0.5: pred[j].append(rng.randrange(j))
    elig=None
    if het:
        elig=[]
        for i in range(n):
            k=rng.randint(1,m); elig.append(sorted(rng.sample(range(m),k)))
    return po.make_inst(p,m,pred,elig)
def validate(inst,h,out):
    n=inst['n']; seen=[False]*n; bym={k:[] for k in range(inst['m'])}; end=[None]*n
    for i,k,t in out:
        assert 0<=i<n and not seen[i]; seen[i]=True
        assert k in inst['elig'][i]; assert t>=0 and t+inst['p'][i]<=h
        bym[k].append((t,t+inst['p'][i])); end[i]=t
    assert all(seen)
    for i in range(n):
        for j in inst['pred'][i]: assert end[j]+inst['p'][j]<=end[i]
    for k,v in bym.items():
        v.sort()
        for a,b in zip(v,v[1:]): assert a[1]<=b[0]
    return True
def one(seed,N,het):
    rng=random.Random(seed); bad=0; yes=0; t0=time.time(); nb=nn=0
    for trial in range(N):
        n=rng.randint(4,10); m=rng.choice([2,3]); inst=gen(rng,n,m,het)
        tot=sum(inst['p']); lo=max(1,tot//m-2); hi=min(tot,lo+12); h=rng.randint(lo,hi)
        fe=all(len(set(inst['elig'][i]))==m for i in range(n))
        base=dict(mode='pot',nodecap=400000,omd=fe,hpack_on=True,dcd=True)
        (b,bo),sb=pace_v20.decide(inst,h,dhd=True,**base)
        (d,do),sd=pace_v21.decide(inst,h,dhd=True,dpl=True,**base)
        nb+=sb['nodes']; nn+=sd['nodes']; yes+=1 if b else 0
        if b: validate(inst,h,bo)
        if d: validate(inst,h,do)
        if b!=d:
            bad+=1; print('MISMATCH',trial,'n',n,'m',m,'h',h,'v20',b,'v21',d)
            print(' p',inst['p']); print(' pred',inst['pred']); print(' elig',inst['elig'])
            if bad>=5: break
    return dict(N=N,seed=seed,het=het,yes=yes,bad=bad,nodes={'v20':nb,'v21':nn},
                ratio=round(nb/max(1,nn),3),sec=round(time.time()-t0,2))
if __name__=='__main__':
    A=one(2026,3000,False); print(A)
    B=one(555,3000,True); print(B)
    C=one(31337,2000,False); print(C)
    json.dump(dict(hom=A,het=B,plain=C),open('exp/v21/res_diff.json','w'),indent=1)
