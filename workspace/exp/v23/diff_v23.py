"""Differential test v2.0 vs v3.0 (Pi + CBC), with the gates forced on."""
import sys,random,json,time,argparse
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v23']
import po,pace_v20,pace_v23
def gen(rng,n,m,het):
    p=[rng.randint(2,9) for _ in range(n)]; pred=[[] for _ in range(n)]
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
        assert k in inst['elig'][i]; assert t+inst['p'][i]<=h
        bym[k].append((t,t+inst['p'][i])); end[i]=t
    assert all(seen)
    for i in range(n):
        for j in inst['pred'][i]: assert end[j]+inst['p'][j]<=end[i]
    for k,v in bym.items():
        v.sort()
        for a,b in zip(v,v[1:]): assert a[1]<=b[0]
    return True
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--N',type=int,default=3000)
    ap.add_argument('--seed',type=int,default=2026); ap.add_argument('--het',action='store_true')
    ap.add_argument('--nmax',type=int,default=10); a=ap.parse_args()
    rng=random.Random(a.seed); bad=0; yes=0; nrun=0; nb=nn=0; pi=0; cbc=0; t0=time.time()
    for trial in range(a.N):
        n=rng.randint(5,a.nmax); m=rng.choice([2,3]); inst=gen(rng,n,m,a.het)
        tot=sum(inst['p']); lo=max(1,tot//m-2); hi=min(tot,lo+10); h=rng.randint(lo,hi)
        fe=all(len(set(inst['elig'][i]))==m for i in range(n))
        base=dict(mode='pot',nodecap=500000,omd=fe,hpack_on=True,dcd=True)
        (b,bo),sb=pace_v20.decide(inst,h,dhd=True,**base)
        (d,do),sd=pace_v23.decide(inst,h,dhd=True,pi=True,pi_depth=0,pi_ncap=16,
                                  pi_tau=10**9,pi_gap=10**9,cbc=True,cbc_ncap=40,
                                  pi_wcap=14,**base)
        nrun+=1; yes+=1 if b else 0; nb+=sb['nodes']; nn+=sd['nodes']
        pi+=sd.get('pi_prunes',0); cbc+=sd.get('cbc_prunes',0)
        if b: validate(inst,h,bo)
        if d: validate(inst,h,do)
        if b!=d:
            bad+=1; print('MISMATCH',trial,'n',n,'m',m,'h',h,'v20',b,'v23',d)
            print(' p',inst['p']); print(' pred',inst['pred']); print(' elig',inst['elig'])
            if bad>=3: break
    out=dict(N=nrun,seed=a.seed,het=a.het,yes=yes,bad=bad,pi_prunes=pi,cbc_prunes=cbc,
             nodes={'v20':nb,'v23':nn},ratio=round(nb/max(1,nn),4),time=round(time.time()-t0,2))
    json.dump(out,open(f'exp/v23/res_diff_{a.seed}.json','w'),indent=1); print(out)
if __name__=='__main__': main()
