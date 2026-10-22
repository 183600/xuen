import sys,random,json,time
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v15');sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19');sys.path.insert(0,'exp/v20')
import po,pace_q,pace_v19,pace_v20
CFG=dict(mode='pot',nodecap=1_500_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def run(mod,inst,h,**kw):
    hp=kw.pop('hpack_on',True)
    return mod.decide(inst,h,odom=False,hpack_on=hp,omd=True,**CFG,**kw)
def opt_of(inst):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3)
    for h in range(lo,lo+20):
        (ok,_),st=run(pace_q,inst,h,hpack_on=False)
        if st.get('timeout'): return None
        if ok: return h
    return None
def gen_distinct(rng):
    n=rng.randint(13,16); m=3
    p=rng.sample(range(3,3+4*n),n)
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
    rng=random.Random(seed); rows=[]; tried=0; t0=time.time()
    while len(rows)<count and tried<400:
        tried+=1; inst=genfn(rng)
        opt=opt_of(inst)
        if opt is None: continue
        h=opt-1
        ((b,_),sb)=run(pace_q,inst,h,hpack_on=False)
        if b or sb['nodes']<12: continue
        ((d19,_),s19)=run(pace_v19,inst,h,dcd=True,rhd=True)
        ((d20,_),s20)=run(pace_v20,inst,h,dcd=True,dhd=True)
        ((ok,_),_)=run(pace_v20,inst,opt,dcd=True,dhd=True)
        if d19 or d20 or not ok: continue
        rows.append(dict(n=inst['n'],base=sb['nodes'],v19=s19['nodes'],v20=s20['nodes'],
                         dcd=s20.get('dcd_skips',0),drops=s20.get('rhd_drops',0)))
    out=dict(name=name,tried=tried,count=len(rows),
             nodes={k:sum(r[k] for r in rows) for k in ('base','v19','v20')},
             ratio=round(sum(r['v19'] for r in rows)/max(1,sum(r['v20'] for r in rows)),4),
             wins=sum(1 for r in rows if r['v20']<r['v19']),
             ties=sum(1 for r in rows if r['v20']==r['v19']),
             losses=sum(1 for r in rows if r['v20']>r['v19']),
             dcd=sum(r['dcd'] for r in rows),rows=rows,sec=round(time.time()-t0,1))
    print({k:v for k,v in out.items() if k!='rows'}); [print(' ',r) for r in rows]
    return out
if __name__=='__main__':
    A=measure('distinct_p',gen_distinct,9001,20)
    B=measure('fan_chains',gen_fan,9002,20)
    json.dump(dict(distinct_p=A,fan_chains=B),open('exp/v20/res_adv.json','w'),indent=1)
