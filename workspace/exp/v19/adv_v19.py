"""Adversarial suites for v1.9.

A. distinct-p : all processing times distinct -> DCD's p_i=p_j test is never
   true, so every DCD drop is zero by construction.  Tests RHD alone.
B. fan-chains : one root -> k private chains, p distinct.  At depth 1 all
   heads have the same est (synchronised), so RHD cannot fire either; this is
   the tight worst case of the composed quotient.
"""
import sys,random,json,time,statistics
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v15');sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19')
import po,pace_q,pace_v18,pace_v19
CFG=dict(mode='pot',nodecap=1_500_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def run(mod,inst,h,**kw):
    dcd=kw.pop('dcd',False); omd=kw.pop('omd',True)
    base=dict(odom=kw.pop('odom',False),hpack_on=kw.pop('hp',True),omd=omd)
    if mod is not pace_q: base['dcd']=dcd
    return mod.decide(inst,h,**base,**CFG,**kw)
def opt_of(inst):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3)
    for h in range(lo,lo+20):
        (ok,_),st=run(pace_q,inst,h,hp=False)
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
        ((b,_),sb)=run(pace_q,inst,h,hp=False)
        if b or sb['nodes']<12: continue
        ((d18,_),s18)=run(pace_v18,inst,h,dcd=True)
        ((d19,_),s19)=run(pace_v19,inst,h,dcd=True,rhd=True)
        ((ok,_),_)=run(pace_v19,inst,opt,dcd=True,rhd=True)
        if d18 or d19 or not ok: continue
        rows.append(dict(n=inst['n'],k=max(1,len([i for i in range(inst['n']) if not inst['pred'][i]])),
                         opt=opt,base=sb['nodes'],v18=s18['nodes'],v19=s19['nodes'],
                         dcd_skips=s19.get('dcd_skips',0),rhd_drops=s19.get('rhd_drops',0),
                         rhd_before=s19.get('rhd_fan_before',0),rhd_after=s19.get('rhd_fan_after',0)))
    out=dict(name=name,tried=tried,count=len(rows),
             nodes={k:sum(r[k] for r in rows) for k in ('base','v18','v19')},
             ratio=round(sum(r['v18'] for r in rows)/max(1,sum(r['v19'] for r in rows)),3),
             wins=sum(1 for r in rows if r['v19']<r['v18']),
             ties=sum(1 for r in rows if r['v19']==r['v18']),
             losses=sum(1 for r in rows if r['v19']>r['v18']),
             dcd_skips=sum(r['dcd_skips'] for r in rows),
             rows=rows,sec=round(time.time()-t0,1))
    print(json.dumps({k:v for k,v in out.items() if k!='rows'})); [print(r) for r in rows]
    return out
if __name__=='__main__':
    A=measure('distinct_p',gen_distinct,9001,20)
    B=measure('fan_chains',gen_fan,9002,20)
    json.dump(dict(distinct_p=A,fan_chains=B),open('exp/v19/res_adv_v19.json','w'),indent=1)
