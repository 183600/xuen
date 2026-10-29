import sys, random, time
sys.path.insert(0,'exp/v14')
import sp, lls
from verify import brute, rand_inst

rng=random.Random(99)
bad=0; tot=0; t0=time.time()
for trial in range(500):
    n=rng.randint(4,7); m=rng.choice([2,3])
    inst=rand_inst(rng,n,m)
    est,q=sp.heads_tails(inst,0,[0]*n)
    lb=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),max(inst['p']))
    h=rng.randint(lb,lb+5)
    b=brute(inst,h)
    (ok,_),st=lls.decide_lls(inst,h,labelcap=2_000_000)
    tot+=1
    if ok!=b:
        bad+=1
        print('MISMATCH',n,m,h,ok,b,inst['p'],inst['pred'],inst['elig'],st['labels'])
        if bad>5: break
print('lls brute checks',tot,'mismatch',bad,'time',round(time.time()-t0,2))
