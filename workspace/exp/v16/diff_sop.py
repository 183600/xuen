import sys,random,time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
import po, pace_i, pace_sop
sys.path.insert(0,'exp/v15')
from diff_i import gen, brute

if __name__=='__main__':
    rng=random.Random(int(sys.argv[1]) if len(sys.argv)>1 else 17)
    reps=int(sys.argv[2]) if len(sys.argv)>2 else 200
    bad=0; cnt=0; hits=0; t0=time.time()
    for it in range(reps):
        n=rng.randint(5,9); m=rng.choice([2,3])
        ep=rng.choice([0.15,0.3,0.5]); elig_p=rng.choice([1.0,0.7,0.5])
        inst=gen(rng,n,m,ep=ep,elig_p=elig_p)
        est,q=po.heads_tails(inst,0,[0]*n)
        lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),
               (sum(inst['p'])+m-1)//m, max(inst['p']))
        for h in range(lo, lo+5):
            b=brute(inst,h)
            (r,s)=pace_sop.decide(inst,h,mode='pot',slack_cap=10**9,
                                  mint_on=True,mint_depth=10**9,
                                  packset_on=True,packset_depth=10**9,
                                  packset_maxslack=10**9,
                                  sop_on=True,sop_nodecap=200000)
            cnt+=1
            if s.get('sop_prunes'): hits+=1
            if r[0]!=b or s.get("timeout"):
                bad+=1
                print('MISMATCH it',it,'n',n,'m',m,'h',h,'brute',b,'sop',r,
                      'ep',ep,'eligp',elig_p,'sop_wit',s.get('root_wit'),flush=True)
                if bad>5: raise SystemExit
    print('cases',cnt,'mismatch',bad,'sop_hits',hits,'time',round(time.time()-t0,1))
