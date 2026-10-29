"""Hard eligibility-constrained benchmark: rigid pairs are the only disjunctions."""
import sys,random,json,time,pickle
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v21']
import po,pace_v20,pace_v21
CFG=dict(mode='pot',nodecap=2_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def run(mod,inst,h,**kw): return mod.decide(inst,h,odom=False,dcd=True,hpack_on=True,omd=False,**CFG,**kw)
def gen(rng,n,m):
    p=[rng.randint(3,9) for _ in range(n)]
    pred=[[] for _ in range(n)]
    ep=rng.choice([0.2,0.3,0.4])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j]: pred[j].append(rng.randrange(j))
    elig=[]
    for i in range(n):
        sz=rng.choice([1,1,1,2,2])
        elig.append(sorted(rng.sample(range(m),sz)))
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
def build(seed,count,want):
    rng=random.Random(seed); rows=[]; tried=0; t0=time.time()
    while len(rows)<count and tried<4000:
        tried+=1; n=rng.randint(11,15); m=3; inst=gen(rng,n,m)
        est,q=po.heads_tails(inst,0,[0]*n)
        lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+m-1)//m)
        opt=None
        for h in range(lo,lo+16):
            (ok,_),_=run(pace_v20,inst,h)
            if ok: opt=h; break
        if opt is None: continue
        (b,_),s20=run(pace_v20,inst,opt-1)
        if s20['nodes']<want: continue
        (b21,_),s21=run(pace_v21,inst,opt-1,dpl=True)
        (ok,o),_=run(pace_v21,inst,opt,dpl=True)
        assert b is False and b21 is False and ok
        validate(inst,opt,o)
        rows.append(dict(n=n,opt=opt,v20=s20['nodes'],v21=s21['nodes'],
                         edges=s21.get('dpl_edges',0),probes=s21.get('dpl_probes',0),
                         t20=round(s20['t_run'],5),t21=round(s21['t_run'],5)))
    return dict(seed=seed,tried=tried,count=len(rows),
                nodes={k:sum(r[k] for r in rows) for k in ('v20','v21')},
                ratio=round(sum(r['v20'] for r in rows)/max(1,sum(r['v21'] for r in rows)),4),
                wins=sum(1 for r in rows if r['v21']<r['v20']),
                ties=sum(1 for r in rows if r['v21']==r['v20']),
                losses=sum(1 for r in rows if r['v21']>r['v20']),
                edges=sum(r['edges'] for r in rows),rows=rows,
                sec=round(time.time()-t0,1))
A=build(777001,24,20); print('A',{k:v for k,v in A.items() if k!='rows'},flush=True)
B=build(777002,20,20); print('B',{k:v for k,v in B.items() if k!='rows'},flush=True)
json.dump(dict(A=A,B=B),open('exp/v21/res_rigid.json','w'),indent=1)
