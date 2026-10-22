"""Where does the search wall sit? n = 18/20/22, m=3, OPT by upward scan."""
import sys,random,time,pickle,json
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v15');sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19');sys.path.insert(0,'exp/v20')
import po,pace_v19,pace_v20
CFG=dict(mode='pot',nodecap=500_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=100000)
def gen(rng,n,m,pvals,ep):
    p=[rng.choice(pvals) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.75: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
def run(ver,inst,h,cap=500_000):
    base=dict(odom=False,dcd=True,hpack_on=True,omd=True,**{**CFG,'nodecap':cap})
    f=pace_v19.decide if ver=='v19' else pace_v20.decide
    kw={'rhd':True} if ver=='v19' else {'dhd':True}
    (b,_),st=f(inst,h,**base,**kw)
    return b,st
def getopt(inst,cap=300_000):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3,max(inst['p']))
    for h in range(lo,lo+25):
        b,st=run('v19',inst,h,cap)
        if st.get('timeout'): return None,st
        if b: return h,st
    return None,st
rng=random.Random(777001); out=[]
for n in (18,20,22):
    for rep in range(3):
        inst=gen(rng,n,3,[3,4,5,6],rng.choice([0.2,0.25,0.3]))
        t0=time.time(); opt,st=getopt(inst)
        if opt is None:
            print('n',n,'rep',rep,'OPT timeout',round(time.time()-t0,1),flush=True); continue
        h=opt-1
        t1=time.time(); b19,s19=run('v19',inst,h)
        t2=time.time(); b20,s20=run('v20',inst,h)
        rec=dict(n=n,rep=rep,opt=opt,v19=s19['nodes'],v20=s20['nodes'],
                 to19=round(t2-t1,2),to20=round(time.time()-t2,2),
                 tmo19=bool(s19.get('timeout')),tmo20=bool(s20.get('timeout')),
                 neg19=s19['nodes'],neg20=s20['nodes'])
        out.append(rec); print(rec,flush=True)
        pickle.dump(out,open('exp/v20/res_scale.json','wb'))
