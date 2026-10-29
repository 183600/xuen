import sys,random,time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
import po, order_sop as sop
from diff_i import gen, brute
rng=random.Random(int(sys.argv[1]) if len(sys.argv)>1 else 23)
reps=int(sys.argv[2]) if len(sys.argv)>2 else 300
bad=0; cnt=0; hits=0; t0=time.time()
for it in range(reps):
    n=rng.randint(5,10); m=rng.choice([2,3])
    ep=rng.choice([0.15,0.3,0.5]); elig_p=rng.choice([1.0,0.7,0.5])
    inst=gen(rng,n,m,ep=ep,elig_p=elig_p)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),
           (sum(inst['p'])+m-1)//m, max(inst['p']))
    for h in range(lo, lo+5):
        v,st=sop.root_gate(inst,h)
        cnt+=1
        if v=='NO':
            hits+=1
            b=brute(inst,h)
            if b:
                bad+=1
                print('FALSE NO it',it,'n',n,'m',m,'h',h,'chain',st['cert']['chain'],
                      'reason',st['cert']['reason'],'forced',st['cert']['forced'],flush=True)
                if bad>3: raise SystemExit
            ok=sop.check_cert(inst,h,st['cert'])
            if not ok:
                print('BAD CERT',it,h); bad+=1
print('cases',cnt,'NO hits',hits,'false NO/bad cert',bad,'time',round(time.time()-t0,1))
