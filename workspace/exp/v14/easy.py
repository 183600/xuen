import sys, random, time
sys.path.insert(0,'exp/v14')
import sp, lls, hybrid
rng=random.Random(31)
rows=[]
for t in range(40):
    n=rng.randint(10,12); m=3
    inst=hybrid.rand_inst(rng,n,m)
    est,q=sp.heads_tails(inst,0,[0]*n)
    lb=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),max(inst['p']))
    h=lb+8
    t0=time.time(); (ok,s),st=sp.decide(inst,h,mode='sub',nodecap=500000); td=time.time()-t0
    t0=time.time(); (ok2,_),st2=lls.decide_lls(inst,h,labelcap=200000); tl=time.time()-t0
    rows.append((n,st['nodes'],td,st2['labels'],tl,st2['timeout'],ok,ok2))
    print(t,'n',n,'DFS',st['nodes'],round(td,4),'LLS',st2['labels'],round(tl,3),'to',st2['timeout'],flush=True)
print('DFS total',round(sum(r[2] for r in rows),3),'LLS total',round(sum(r[4] for r in rows),3))
