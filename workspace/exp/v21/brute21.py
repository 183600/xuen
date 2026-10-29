"""Independent brute force for tiny instances (all topological orders x machine assignments)."""
import sys,random,itertools,json,time
sys.path[:0]=['exp/v13','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v21']
import po,pace_v20,pace_v21
def brute(inst,h):
    n,m,p=inst['n'],inst['m'],inst['p']; pred=inst['pred']
    for perm in itertools.permutations(range(n)):
        pos={t:j for j,t in enumerate(perm)}
        if any(pos[j]>pos[i] for i in range(n) for j in pred[i]): continue
        for asg in itertools.product(*[inst['elig'][i] for i in perm]):
            A=[0]*m; fin=[0]*n; ok=True
            for idx,i in enumerate(perm):
                k=asg[idx]
                t=A[k]
                for j in pred[i]:
                    if fin[j]>t: t=fin[j]
                if t+p[i]>h: ok=False; break
                fin[i]=t+p[i]; A[k]=t+p[i]
            if ok: return True
    return False
def gen(rng,n,m,het):
    p=[rng.randint(2,6) for _ in range(n)]; pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<rng.choice([0.2,0.35,0.5]): pred[j].append(i)
    elig=None
    if het:
        elig=[]
        for i in range(n):
            k=rng.randint(1,m); elig.append(sorted(rng.sample(range(m),k)))
    return po.make_inst(p,m,pred,elig)
rng=random.Random(90210); bad=0; cases=0; t0=time.time(); yes=0
for trial in range(400):
    n=rng.randint(3,5); m=rng.choice([2,3]); inst=gen(rng,n,m,True)
    tot=sum(inst['p']); lo=max(1,tot//m-1)
    for h in range(lo,min(tot,lo+4)+1):
        b=brute(inst,h)
        fe=all(len(set(inst['elig'][i]))==m for i in range(n))
        cfg=dict(mode='pot',nodecap=200000,omd=fe,hpack_on=False,dcd=True)
        (a,ao),_=pace_v20.decide(inst,h,dhd=True,**cfg)
        (c,co),_=pace_v21.decide(inst,h,dhd=True,dpl=True,**cfg)
        cases+=1; yes+=1 if b else 0
        if a!=b or c!=b:
            bad+=1; print('MISMATCH',trial,'n',n,'m',m,'h',h,'brute',b,'v20',a,'v21',c)
            print(' p',inst['p']); print(' pred',inst['pred']); print(' elig',inst['elig'])
            if bad>=5: break
    if bad>=5: break
out=dict(cases=cases,yes=yes,bad=bad,sec=round(time.time()-t0,2))
print(out); json.dump(out,open('exp/v21/res_brute.json','w'),indent=1)
