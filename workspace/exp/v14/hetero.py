import sys, random, time
sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v13')
import sp, po, lls, hybrid
rng=random.Random(2025)
rows=[]
for t in range(6):
    n=rng.randint(10,12); m=3
    inst=hybrid.rand_inst(rng,n,m,pmax=10,ep=0.2,elig_p=0.65)
    est,q=sp.heads_tails(inst,0,[0]*n)
    lb=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),max(inst['p']))
    opt=None
    for h in range(lb,lb+18):
        (ok,_),st=sp.decide(inst,h,mode='sub',nodecap=200000)
        if ok: opt=h; break
    if opt is None:
        print('no opt',t); continue
    h=opt-1
    out={}
    for name,fn in [('dfs_fixed',lambda: sp.decide(inst,h,mode='sub',nodecap=1000000)),
                    ('dfs_buggy',lambda: po.decide(inst,h,mode='sub',nodecap=1000000)),
                    ('lls',lambda: lls.decide_lls(inst,h,labelcap=1000000))]:
        t0=time.time(); (ok,sch),st=fn(); dt=time.time()-t0
        out[name]=dict(ok=ok,t=round(dt,3),nodes=st.get('nodes'),labels=st.get('labels'))
    print(t,'n',n,'opt',opt,out,flush=True)
    rows.append(dict(t=t,n=n,opt=opt,**out))
import json; json.dump(rows,open('exp/v14/hetero.json','w'),indent=1)
