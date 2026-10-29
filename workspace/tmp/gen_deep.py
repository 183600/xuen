import sys, random, pickle, time
sys.path[:0]=['exp/v61','exp/v60','exp/v13']
sys.setrecursionlimit(50000)
from alc import ALC
from po import heads_tails
from gen_hard3 import gen

rng=random.Random(777)
kept=[]; stats=[]; t0=time.time()
for trial in range(60):
    n=rng.randint(18,24); m=rng.choice([3,4])
    inst=gen(rng,n,m,pmax=rng.choice([6,8,10]),ep=rng.choice([0.12,0.18]))
    est,q=heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),
           (sum(inst['p'])+m-1)//m, max(inst['p']))
    opt=None
    for h in range(lo,lo+15):
        a=ALC(inst,h,cert_on=False)
        try: v,st=a.decide(nodecap=1500)
        except RecursionError: v=None
        if v is True: opt=h; break
        if v is None: break
    if opt is None: continue
    a=ALC(inst,opt-1,cert_on=False)
    try: v,st=a.decide(nodecap=1500)
    except RecursionError: continue
    stats.append((n,m,opt,st['nodes'],st['lp_solves']))
    print('trial',trial,'n',n,'m',m,'opt',opt,'nodes',st['nodes'],'lp',st['lp_solves'],'t',round(time.time()-t0,1),flush=True)
    if st['nodes']>=5:
        kept.append((inst,opt,st['nodes']))
pickle.dump(kept,open('tmp/deep_gen.pkl','wb'))
print('kept',len(kept),'of',len(stats))
