import sys, random, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14')
import po, pace
from diff_test import gen

rng=random.Random(2027)
bad=0; cases=0; t0=time.time()
for it in range(120):
    n=rng.randint(10,13); m=rng.choice([2,3])
    inst=gen(rng,n,m,ep=rng.choice([0.12,0.2,0.35]),elig_p=rng.choice([1.0,0.7]))
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),
           (sum(inst['p'])+m-1)//m, max(inst['p']))
    for h in range(lo, lo+5):
        (r1,_),s1=po.decide(inst,h,mode='sub',nodecap=400000)
        (r2,_),s2=pace.decide(inst,h,mode='pot',pot_depth=0)
        cases+=1
        if r1!=r2 or s1.get('timeout') or s2.get('timeout'):
            bad+=1; print('MISMATCH',it,n,m,h,r1,r2,flush=True)
    if it%20==0: print('..',it,'cases',cases,'bad',bad,'t',round(time.time()-t0,1),flush=True)
print('DONE cases',cases,'bad',bad,'t',round(time.time()-t0,1))
