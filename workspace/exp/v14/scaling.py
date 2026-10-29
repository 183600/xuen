import sys, random, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14')
import po, pace
rng=random.Random(5)
print('n,instances,ms_per_check,intervals,closed')
for n in (20,40,60,80,120,160):
    ts=[]; cls=0
    for rep in range(12):
        p=[rng.randint(2,10) for _ in range(n)]
        pred=[[] for _ in range(n)]
        for j in range(n):
            if rng.random()<0.2 and j: pred[j].append(rng.randrange(j))
        inst=po.make_inst(p,3,pred)
        est,q=po.heads_tails(inst,0,[0]*n)
        h=max(max(est[i]+p[i]+q[i] for i in range(n)),(sum(p)+2)//3)
        t=time.time(); ok,phi,w=pace.potential(inst,inst['full'],(0,0,0),tuple(est),q,h,slack_cap=10**9)
        ts.append((time.time()-t)*1000); cls+= (not ok)
    print(n,len(ts),round(sum(ts)/len(ts),3),'~',4*n*n,'closed',cls,flush=True)
