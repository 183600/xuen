import sys,random,time,json
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v23']
import po,pace_q,pace_v20,pace_v23
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def gen(rng,n,m):
    p=[rng.randint(2,9) for _ in range(n)]; pred=[[] for _ in range(n)]
    ep=rng.choice([0.18,0.22,0.28,0.35])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j]: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
rng=random.Random(424242); cases=[]; tried=0
while len(cases)<50 and tried<3000:
    tried+=1; n=rng.randint(12,16); inst=gen(rng,n,3)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3)
    opt=None
    for h in range(lo,lo+18):
        (ok,_),_=pace_q.decide(inst,h,odom=False,hpack_on=False,omd=True,**CFG)
        if ok: opt=h; break
    if opt is None: continue
    (b,_),sb=pace_q.decide(inst,opt-1,odom=False,hpack_on=False,omd=True,**CFG)
    if sb['nodes']<15: continue
    cases.append((inst,opt))
for cbc in [False,True]:
    tot=0; tt=0; cp=0; rows=[]
    for inst,opt in cases:
        t=time.time(); (b,o),st=pace_v23.decide(inst,opt-1,hpack_on=True,omd=True,dcd=True,dhd=True,
            pi=True,pi_depth=0,pi_ncap=16,pi_tau=4,pi_gap=4,pi_wcap=15,cbc=cbc,cbc_ncap=40,**CFG); tt+=time.time()-t; tot+=st['nodes']; cp+=st.get('cbc_prunes',0)
        rows.append((st['nodes'],st.get('cbc_prunes',0),st.get('pi_beta')))
    print('cbc',cbc,'nodes',tot,'time',round(tt,3),'cbc_prunes',cp)
    if cbc:
        print([r for r in rows if r[0]>1])
