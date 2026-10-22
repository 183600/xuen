import sys,random,json,time
sys.path[:0]=['exp/v13','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v21']
import po,pace_q,pace_v19,pace_v20,pace_v21
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def gen(rng,n,m,pmax=10,ep=0.22):
    p=[rng.randint(2,pmax) for _ in range(n)]; pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
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
# ---- easy 60 ----
rng=random.Random(8080); tot={k:0 for k in ('v20','v21')}; tt={k:0.0 for k in ('v20','v21')}; n_inst=0
while n_inst<60:
    n=rng.randint(10,14); inst=gen(rng,n,3)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3,max(inst['p']))
    opt=None
    for h in range(lo,lo+10):
        ok,_=pace_q.decide(inst,h,odom=True,hpack_on=False,omd=True,**CFG)
        if ok: opt=h; break
    if opt is None: continue
    h=opt+5
    (a,o20),s20=pace_v20.decide(inst,h,odom=False,dcd=True,dhd=True,hpack_on=True,omd=True,**CFG)
    (b,o21),s21=pace_v21.decide(inst,h,odom=False,dcd=True,dhd=True,dpl=True,hpack_on=True,omd=True,**CFG)
    assert a==b==True
    validate(inst,h,o21)
    tot['v20']+=s20['nodes']; tot['v21']+=s21['nodes']
    tt['v20']+=s20['t_run']; tt['v21']+=s21['t_run']; n_inst+=1
easy=dict(count=n_inst,nodes=tot,time={k:round(v,4) for k,v in tt.items()},
          ratio=round(tot['v20']/max(1,tot['v21']),4))
print('easy',easy,flush=True)
# ---- adv ----
def run(inst,h,**kw): return pace_v20.decide(inst,h,odom=False,hpack_on=True,omd=True,**CFG,**kw)
def opt_of(inst):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3)
    for h in range(lo,lo+20):
        (ok,_),_=pace_q.decide(inst,h,odom=False,hpack_on=False,omd=True,**CFG)
        if ok: return h
    return None
def gen_distinct(rng):
    n=rng.randint(13,16); m=3; p=rng.sample(range(3,3+4*n),n)
    pred=[[] for _ in range(n)]
    ep=rng.choice([0.2,0.28])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j]: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
def gen_fan(rng):
    n=rng.randint(13,16); m=3; p=rng.sample(range(3,3+4*n),n)
    k=rng.randint(4,6); L=(n-1)//k
    pred=[[] for _ in range(n)]
    idx=1
    for _ in range(k):
        prev=0
        for _ in range(L):
            if idx>=n: break
            pred[idx]=[prev]; prev=idx; idx+=1
        if idx>=n: break
    while idx<n:
        pred[idx]=[0]; idx+=1
    return po.make_inst(p,m,pred)
def measure(name,genfn,seed,count):
    rng=random.Random(seed); rows=[]; tried=0
    while len(rows)<count and tried<400:
        tried+=1; inst=genfn(rng); opt=opt_of(inst)
        if opt is None: continue
        h=opt-1
        (b,_),sb=pace_q.decide(inst,h,odom=False,hpack_on=False,omd=True,**CFG)
        if b or sb['nodes']<12: continue
        (d20,_),s20=pace_v20.decide(inst,h,odom=False,dcd=True,dhd=True,hpack_on=True,omd=True,**CFG)
        (d21,o21),s21=pace_v21.decide(inst,h,odom=False,dcd=True,dhd=True,dpl=True,hpack_on=True,omd=True,**CFG)
        (ok,o),_=pace_v21.decide(inst,opt,odom=False,dcd=True,dhd=True,dpl=True,hpack_on=True,omd=True,**CFG)
        if d20 or d21 or not ok: continue
        validate(inst,opt,o)
        rows.append(dict(v20=s20['nodes'],v21=s21['nodes'],edges=s21.get('dpl_edges',0)))
    return dict(name=name,count=len(rows),nodes={k:sum(r[k] for r in rows) for k in ('v20','v21')},
                ratio=round(sum(r['v20'] for r in rows)/max(1,sum(r['v21'] for r in rows)),4),
                wins=sum(1 for r in rows if r['v21']<r['v20']),
                ties=sum(1 for r in rows if r['v21']==r['v20']),
                losses=sum(1 for r in rows if r['v21']>r['v20']),
                edges=sum(r['edges'] for r in rows),rows=rows)
A=measure('distinct_p',gen_distinct,9001,20); print('distinct',{k:v for k,v in A.items() if k!='rows'},flush=True)
B=measure('fan_chains',gen_fan,9002,20); print('fan',{k:v for k,v in B.items() if k!='rows'},flush=True)
json.dump(dict(easy=easy,distinct_p=A,fan_chains=B),open('exp/v21/res_easy_adv.json','w'),indent=1)
