import sys, random, time, json, statistics as S
sys.path.insert(0,'v13'); sys.path.insert(0,'v11')
import po, plib

def rand_inst(rng,n,m,pmax=10,ep=0.18,elig_p=1.0):
    p=[rng.randint(2,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.7: pred[j].append(rng.randrange(j))
    elig=[]
    for i in range(n):
        if elig_p>=1.0: elig.append(list(range(m)))
        else:
            e=[k for k in range(m) if rng.random()<elig_p]
            if not e: e=[rng.randrange(m)]
            elig.append(e)
    return po.make_inst(p,m,pred,elig)

out={}
# ---------- E5 overhead on easy instances
rng=random.Random(31)
over=[]
for trial in range(120):
    n=rng.randint(10,14); m=3
    inst=rand_inst(rng,n,m)
    est,q=po.heads_tails(inst,0,[0]*n)
    lb=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),max(inst['p']))
    h=lb+8   # loose
    tp=[]; ts=[]
    for mode in ['plain','sub']:
        t=time.time()
        for _ in range(3):
            (ok,_),st=po.decide(inst,h,mode=mode,nodecap=2_000_000)
        dt=(time.time()-t)/3
        (tp if mode=='plain' else ts).append(dt)
    over.append((sum(tp),sum(ts)))
out['easy_overhead']=dict(plain=sum(a for a,b in over),sub=sum(b for a,b in over),
                          ratio=sum(b for a,b in over)/sum(a for a,b in over),
                          n=len(over))
print('E5 overhead',out['easy_overhead'],flush=True)

# ---------- E6 cache microbenchmark: table build vs front query
rng=random.Random(77)
rows=[]
for nrem in [20,40,80,120]:
    H=100; m=3; caps=[H]*m
    p=[rng.randint(1,10) for _ in range(nrem)]
    t=time.time(); ok,tot=plib.profile_bitset(p,caps); t_table=time.time()-t
    if ok is None: continue
    # front query cost with |F|=1,2,4,8
    for K in [1,2,4,8]:
        F=[tuple(80-2*j for _ in range(m)) for j in range(K)]
        q=tuple([95]*m)
        t=time.time()
        for _ in range(20000):
            any(all(a[k]<=q[k] for k in range(m)) for a in F)
        tq=(time.time()-t)/20000
        rows.append(dict(n=nrem,H=H,K=K,t_table=t_table,t_query=tq,
                         ratio=t_table/tq, rho_star=tq/(t_table+tq)))
    print('E6 n',nrem,'table',round(t_table,4),flush=True)
out['cache_micro']=rows

# ---------- E7 heterogeneous eligibility m=3
rng=random.Random(555)
hard=[]
while len(hard)<6:
    n=rng.randint(12,15); m=3
    inst=rand_inst(rng,n,m,elig_p=0.65)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),max(inst['p']))
    opt=None
    for h in range(lo,lo+8):
        (ok,_),st=po.decide(inst,h,mode='plain',nodecap=400_000)
        if st.get('timeout'): break
        if ok: opt=h; break
    if opt is None: continue
    (ok,_),st=po.decide(inst,opt-1,mode='plain',nodecap=400_000)
    if st.get('timeout') or st['nodes']<2000: continue
    hard.append((inst,opt,st['nodes']))
    print('E7 kept',len(hard),'nodes',st['nodes'],flush=True)
het=[]
for idx,(inst,opt,_) in enumerate(hard):
    row={'opt':opt,'bench':{}}
    for mode in ['plain','canon','sub']:
        t=time.time(); (ok,_),st=po.decide(inst,opt-1,mode=mode,nodecap=2_000_000); dt=time.time()-t
        row['bench'][mode]=dict(nodes=st['nodes'],t=round(dt,4),tables=st['tables'],
                                packfh=st['pack_front_hits'],subfh=st['sub_front_hits'],
                                fmax=max(st['front_sizes']) if st['front_sizes'] else 0)
    het.append(row)
    print('E7 inst',idx,{k:(v['nodes'],v['t']) for k,v in row['bench'].items()},flush=True)
out['hetero']=het
json.dump(out,open('v13/extra.json','w'),indent=1)
print('saved')
