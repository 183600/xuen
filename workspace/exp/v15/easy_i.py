import sys, random, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v15')
import po, pace, pace_i
from diff_i import gen

rng=random.Random(4242)
rows=[]
while len(rows)<60:
    n=rng.randint(10,14); m=3
    inst=gen(rng,n,m,ep=rng.choice([0.15,0.25]),elig_p=1.0)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+m-1)//m,max(inst['p']))
    opt=None
    for h in range(lo,lo+14):
        (ok,_),st=po.decide(inst,h,mode='sub',nodecap=200000)
        if st.get('timeout'): break
        if ok: opt=h; break
    if opt is None: continue
    h=opt+5
    r={}
    t=time.time(); (ok1,_),s1=po.decide(inst,h,mode='sub',nodecap=400000); r['sub']=(s1['nodes'],time.time()-t)
    t=time.time(); (ok2,_),s2=pace.decide(inst,h,mode='pot'); r['v13']=(s2['nodes'],time.time()-t)
    t=time.time(); (ok3,_),s3=pace_i.decide(inst,h,mode='pot',mint_depth=0,packset_depth=0); r['v14']=(s3['nodes'],time.time()-t)
    assert ok1==ok2==ok3
    rows.append((n,r))
tot={k:(sum(x[1][k][0] for x in rows),sum(x[1][k][1] for x in rows)) for k in ('sub','v13','v14')}
print('instances',len(rows))
for k,v in tot.items(): print(k,'nodes',v[0],'time',round(v[1],4))
print('v14/sub time ratio',round(tot['v14'][1]/tot['sub'][1],2),'v13/sub',round(tot['v13'][1]/tot['sub'][1],2))
