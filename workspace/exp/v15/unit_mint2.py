import sys, random, math
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15')
import po, pace_i
from unit_mint import brute_beta, rand_state

rng=random.Random(13); fired=0; bad=0; checked=0
for it in range(3000):
    inst,rem,A,est,q=rand_state(rng,rng.randint(5,10),rng.choice([2,3]))
    if rem==0: continue
    tasks=list(po.bititer(rem)); n=inst['n']
    sump=sum(inst['p'][i] for i in tasks)
    lb=max(max(est[i]+inst['p'][i]+q[i] for i in tasks),
           (sump+sum(A)+inst['m']-1)//inst['m'], max(inst['p'][i] for i in tasks))
    for h in (lb,lb+1,lb+2):
        checked+=1
        ok,phi,w=pace_i.potential(inst,rem,A,est,q,h,mint_on=True,mint_tau=5,
                                  packset_on=False)
        if (not ok) and w and w[0]=='mint':
            fired+=1
            _,S,W,cap=w; S=sorted(S)
            if not all(S[j][1]<=S[j+1][0] for j in range(len(S)-1)):
                bad+=1; print('overlap',S); continue
            W2=sum(brute_beta(inst['p'][i],est[i],h-q[i],S) for i in tasks)
            cap2=sum((b-max(a,A[k])) for a,b in S for k in range(inst['m']) if b>max(a,A[k]))
            if not (W2==W and cap2==cap and W2>cap):
                bad+=1
                if bad<5: print('BAD',n,h,S,W,cap,W2,cap2)
print('checked',checked,'mint fired',fired,'bad',bad)
