import sys, random, time, json
sys.path.insert(0,'exp/v10')
from profile import profile_dec
rng=random.Random(3); rows=[]
for m in (2,3,4,5):
    for (n,H) in ((10,40),(50,40),(200,40),(50,100),(10,200),(200,200)):
        cap=(m*H)//n
        if cap<1: continue
        if m>=4 and H==200: continue
        p=[rng.randint(1,max(1,cap)) for _ in range(n)]
        t=time.time(); ok,layers,ns=profile_dec(p,[H]*m); dt=time.time()-t
        rows.append(dict(m=m,n=n,H=H,ok=ok,states=ns,layers=len(layers),t=round(dt,4)))
        print(m,n,H,'ok',ok,'states',ns,'t',round(dt,4),flush=True)
json.dump(rows,open('exp/v10/e3.json','w'),indent=1)
