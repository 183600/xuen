import sys,random,json,time
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v23']
import po,pi_fast,cbc
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v11')
import verify2
def rand_inst(rng,n,m):
    p=[rng.randint(1,7) for _ in range(n)]; pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<0.25: pred[j].append(i)
        if j and not pred[j] and rng.random()<0.5: pred[j].append(rng.randrange(j))
    elig=[]
    for i in range(n):
        e=[k for k in range(m) if rng.random()<0.8]
        if not e: e=[rng.randrange(m)]
        elig.append(e)
    return po.make_inst(p,m,pred,elig)
rng=random.Random(20261022); bad=0; nrun=0; pi_no=0; cbc_no=0; t0=time.time()
for trial in range(600):
    n=rng.randint(4,7); m=rng.choice([2,3]); inst=rand_inst(rng,n,m)
    est,q=po.heads_tails(inst,0,[0]*n)
    lb=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),max(inst['p']),(sum(inst['p'])+m-1)//m)
    for h in range(lb,lb+4):
        bf=verify2.brute(inst,h)
        beta,_=pi_fast.beta(inst,h,inst['full'],est,q)
        if beta>m:
            pi_no+=1
            if bf:
                bad+=1; print('PI UNSOUND',trial,n,m,h,beta,inst['p'],inst['pred'],inst['elig'])
                if bad>=3: break
        tasks,adj=cbc.incompat_graph(inst,inst['full'],est,q,h)
        C=cbc.clique_at_least(tasks,adj,m+1)
        if C:
            cbc_no+=1
            if bf:
                bad+=1; print('CBC UNSOUND',trial,n,m,h,C,inst['p'],inst['pred'],inst['elig'])
                if bad>=3: break
        nrun+=1
    if bad>=3: break
out=dict(cases=nrun,pi_no=pi_no,cbc_no=cbc_no,bad=bad,sec=round(time.time()-t0,2))
print(out); json.dump(out,open('exp/v23/res_brute_pi.json','w'),indent=1)
