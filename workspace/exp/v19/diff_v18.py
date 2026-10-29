"""Differential soundness test for v1.8 DCD.

base : same engine, dcd=False
test : same engine, dcd=True  (and optionally + HPACK)

Compares decisions on random instances over many horizons, and validates
every returned schedule independently.
"""
import sys, random, json, time, argparse
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18'); sys.path.insert(0,'exp/v19')
import po, pace_v18

def gen(rng,n,m,het):
    p=[rng.randint(2,9) for _ in range(n)]
    pred=[[] for _ in range(n)]
    ep=rng.choice([0.15,0.25,0.35,0.5])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j] and rng.random()<0.5:
            pred[j].append(rng.randrange(j))
    elig=None
    if het:
        elig=[]
        for i in range(n):
            k=rng.randint(1,m)
            elig.append(sorted(rng.sample(range(m),k)))
    return po.make_inst(p,m,pred,elig)

def validate(inst,h,out):
    n=inst['n']
    seen=[False]*n; bym={k:[] for k in range(inst['m'])}
    end=[None]*n
    for i,k,t in out:
        assert 0<=i<n and not seen[i]; seen[i]=True
        assert k in inst['elig'][i]
        assert t+inst['p'][i]<=h
        bym[k].append((t,t+inst['p'][i]))
        end[i]=t
    assert all(seen)
    for i in range(n):
        for j in inst['pred'][i]:
            assert end[j]+inst['p'][j]<=end[i]
    for k,v in bym.items():
        v.sort()
        for a,b in zip(v,v[1:]):
            assert a[1]<=b[0]
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--N',type=int,default=3000)
    ap.add_argument('--seed',type=int,default=2026)
    ap.add_argument('--het',action='store_true')
    ap.add_argument('--plain',action='store_true')
    ap.add_argument('--hpack',action='store_true')
    ap.add_argument('--nmax',type=int,default=10)
    a=ap.parse_args()
    rng=random.Random(a.seed)
    mode='plain' if a.plain else 'pot'
    bad=0; yes=0; nrun=0; t0=time.time()
    node_b=node_d=0
    for trial in range(a.N):
        n=rng.randint(5,a.nmax); m=rng.choice([2,3])
        inst=gen(rng,n,m,a.het)
        tot=sum(inst['p'])
        lo=max(1,tot//m-2); hi=min(tot,lo+14)
        h=rng.randint(lo,hi)
        fe=all(len(set(inst['elig'][i]))==m for i in range(n))
        (b,bo),sb=pace_v18.decide(inst,h,mode=mode,nodecap=400000,odom=False,dcd=False,
                                  hpack_on=False,omd=fe)
        (d,do),sd=pace_v18.decide(inst,h,mode=mode,nodecap=400000,odom=False,dcd=True,
                                  hpack_on=a.hpack,omd=fe)
        nrun+=1; yes+= 1 if b else 0
        node_b+=sb['nodes']; node_d+=sd['nodes']
        if b: validate(inst,h,bo)
        if d: validate(inst,h,do)
        if b!=d:
            bad+=1
            print('MISMATCH trial',trial,'n',n,'m',m,'h',h,'base',b,'dcd',d)
            print(' p    =',inst['p']); print(' pred =',inst['pred'])
            print(' elig =',inst['elig'])
            if bad>=5: break
    out=dict(N=nrun,seed=a.seed,mode=mode,het=a.het,hpack=a.hpack,yes=yes,bad=bad,
             nodes={'base':node_b,'dcd':node_d},
             node_ratio=round(node_b/max(1,node_d),3),
             time=round(time.time()-t0,3))
    json.dump(out,open(f'exp/v19/res_diff_{a.seed}.json','w'),indent=1)
    print(out)

if __name__=='__main__':
    main()
