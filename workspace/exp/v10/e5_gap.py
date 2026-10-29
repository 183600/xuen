import sys, random, json, time
sys.path.insert(0,'exp/v10')
from profile import profile_dec
from lp import frac_pack
rng=random.Random(99); t0=time.time(); gaps=[]; no=0; trials=0
for tr in range(20000):
    m=rng.choice([3,4,5]); H=rng.randint(8,26); n=rng.randint(5,12)
    cap=max(1,(m*H)//n)
    p=[rng.randint(1,min(H,cap+2)) for _ in range(n)]
    if sum(p)>m*H: continue
    trials+=1
    ok,layers,ns=profile_dec(p,[H]*m)
    if ok: continue
    no+=1
    tau,w,info=frac_pack(p,[H]*m)
    if tau<=m+1e-7:
        gaps.append(dict(m=m,H=H,p=p,tau=tau)); print('GAP',m,H,p,round(tau,3),flush=True)
        if len(gaps)>=5: break
print('trials',trials,'pack-NO',no,'gaps',len(gaps),'time',round(time.time()-t0,1))
json.dump(gaps,open('exp/v10/e5.json','w'),indent=1)
