import sys,random,json,time
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v22']
import po,pace_v20,pi_bound
CFG=dict(mode='pot',nodecap=3000000,mint_on=True,mint_depth=0,packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000,odom=False,dcd=True,dhd=True,hpack_on=True)
def gen(rng,n,m):
    p=[rng.randint(1,7) for _ in range(n)]; pred=[[] for _ in range(n)]
    ep=rng.choice([0.15,0.25,0.4])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
    elig=[]
    for i in range(n):
        if rng.random()<0.5:
            sz=rng.randint(1,m); elig.append(sorted(rng.sample(range(m),sz)))
        else: elig.append(list(range(m)))
    return po.make_inst(p,m,pred,elig)
rng=random.Random(20261022); bad=0; yes=0; cert=0; t0=time.time(); rows=[]
for it in range(2500):
    n=rng.randint(6,12); m=rng.randint(2,3); inst=gen(rng,n,m)
    h=rng.randint(max(inst['p']),sum(inst['p'])+2)
    ((b,o),st)=pace_v20.decide(inst,h,omd=all(len(set(inst['elig'][i]))==m for i in range(n)),**CFG)
    beta,_=pi_bound.pi_beta(inst,h)
    if b: yes+=1
    if beta>m: cert+=1
    if b and beta>m:
        bad+=1; print('UNSOUND',n,m,h,beta,inst['p'],inst['pred'],inst['elig']); break
    if b:
        # independent validation
        seen=[False]*n; bym={k:[] for k in range(m)}; end=[None]*n
        for i,k,t in o:
            assert not seen[i] and k in inst['elig'][i] and t+inst['p'][i]<=h
            seen[i]=True; bym[k].append((t,t+inst['p'][i])); end[i]=t
        assert all(seen)
        for i in range(n):
            for j in inst['pred'][i]: assert end[j]+inst['p'][j]<=end[i]
        for k,v in bym.items():
            v.sort()
            for a,c in zip(v,v[1:]): assert a[1]<=c[0]
print('cases',2500,'yes',yes,'certs',cert,'bad',bad,'sec',round(time.time()-t0,2))
json.dump(dict(cases=2500,yes=yes,certs=cert,bad=bad,sec=round(time.time()-t0,2)),open('exp/v22/res_diff.json','w'),indent=1)
