"""Held-out 50: regenerate with the v2.0 seed/procedure, compare v2.0 vs v2.1."""
import sys,random,json,time
sys.path[:0]=['exp/v13','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v21']
import po,pace_q,pace_v20,pace_v21
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def gen(rng,n,m):
    p=[rng.randint(2,9) for _ in range(n)]; pred=[[] for _ in range(n)]
    ep=rng.choice([0.18,0.22,0.28,0.35])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j]: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
def run(mod,inst,h,**kw):
    return mod.decide(inst,h,odom=False,hpack_on=True,omd=True,**CFG,**kw)
def runq(inst,h):
    return pace_q.decide(inst,h,odom=False,hpack_on=False,omd=True,**CFG)
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
rng=random.Random(424242); rows=[]; tried=0
while len(rows)<50 and tried<3000:
    tried+=1; n=rng.randint(12,16); inst=gen(rng,n,3)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3)
    opt=None
    for h in range(lo,lo+18):
        (ok,_),_=runq(inst,h); 
        if ok: opt=h; break
    if opt is None: continue
    h=opt-1
    (b,_),sb=runq(inst,h)
    if sb['nodes']<15: continue
    (d20,_),s20=run(pace_v20,inst,h,dcd=True,dhd=True)
    (d21,_),s21=run(pace_v21,inst,h,dcd=True,dhd=True,dpl=True)
    (ok,o),_=run(pace_v21,inst,opt,dcd=True,dhd=True,dpl=True)
    assert d20 is False and d21 is False and ok
    validate(inst,opt,o)
    rows.append(dict(base=sb['nodes'],v20=s20['nodes'],v21=s21['nodes'],
                     edges=s21.get('dpl_edges',0),probes=s21.get('dpl_probes',0)))
tot={k:sum(r[k] for r in rows) for k in ('base','v20','v21')}
out=dict(count=len(rows),nodes=tot,ratio=round(tot['v20']/max(1,tot['v21']),4),
         wins=sum(1 for r in rows if r['v21']<r['v20']),
         ties=sum(1 for r in rows if r['v21']==r['v20']),
         losses=sum(1 for r in rows if r['v21']>r['v20']),
         edges=sum(r['edges'] for r in rows),probes=sum(r['probes'] for r in rows),rows=rows)
print({k:v for k,v in out.items() if k!='rows'})
print('changed',[ (i,r) for i,r in enumerate(rows) if r['v21']!=r['v20']])
json.dump(out,open('exp/v21/res_holdout.json','w'),indent=1)
