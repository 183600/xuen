"""Exhaustive soundness for DHD: all DAGs n<=5, p in {1,2}^n, all h in a window."""
import sys, itertools, json, time
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v15');sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19');sys.path.insert(0,'exp/v20')
import po, pace_v20 as pace_w

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

def run(n,m,maxh):
    edges=[(i,j) for j in range(n) for i in range(j)]
    nrun=bad=0; t0=time.time()
    for mask in range(1<<len(edges)):
        pred=[[] for _ in range(n)]
        for b,(i,j) in enumerate(edges):
            if mask>>b&1: pred[j].append(i)
        for pv in itertools.product((1,2),repeat=n):
            inst=po.make_inst(list(pv),m,pred)
            est,q=po.heads_tails(inst,0,[0]*n)
            lb=max(max(est[i]+pv[i]+q[i] for i in range(n)),(sum(pv)+m-1)//m,max(pv))
            for h in range(lb,min(sum(pv),lb+maxh)+1):
                fe=all(len(set(inst['elig'][i]))==m for i in range(n))
                cfg=dict(mode='pot',nodecap=200000,odom=False,dcd=True,hpack_on=False,omd=fe)
                (a,ao),sa=pace_w.decide(inst,h,rhd=False,dhd=False,**cfg)
                (b,bo),sb=pace_w.decide(inst,h,rhd=False,dhd=True,**cfg)
                nrun+=1
                if a!=b:
                    bad+=1
                    print('MISMATCH n',n,'m',m,'p',pv,'pred',pred,'h',h,'base',a,'dhd',b)
                    if bad>=5: return nrun,bad,time.time()-t0
                if a: validate(inst,h,ao)
                if b: validate(inst,h,bo)
    return nrun,bad,time.time()-t0

if __name__=='__main__':
    n=int(sys.argv[1]) if len(sys.argv)>1 else 5
    m=int(sys.argv[2]) if len(sys.argv)>2 else 2
    maxh=int(sys.argv[3]) if len(sys.argv)>3 else 8
    nrun,bad,dt=run(n,m,maxh)
    print(json.dumps(dict(n=n,m=m,maxh=maxh,cases=nrun,bad=bad,sec=round(dt,2))))
    json.dump(dict(n=n,m=m,maxh=maxh,cases=nrun,bad=bad,sec=round(dt,2)),
              open(f'exp/v20/res_exh_{n}_{m}.json','w'),indent=1)
