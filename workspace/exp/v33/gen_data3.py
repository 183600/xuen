import sys, random, time, pickle
sys.path[:0]=['exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v25']
import po, wos
from gen_data import gen, topo, rev, run, opt_wos, feats

rng=random.Random(20261023)
rows=[]; tried=0; t0=time.time()
while len(rows)<3000 and tried<20000:
    tried+=1
    n=rng.randint(10,16); inst=gen(rng,n,3)
    o=opt_wos(inst)
    if o is None or o<3: continue
    r=rev(inst)
    for hmod in (-1,0):
        h=o+hmod
        if h<1: continue
        okf,sf=run(inst,h); okb,sb=run(r,h)
        if okf!=okb or sf['nodes']>=200000 or sb['nodes']>=200000: continue
        okpf,pf=run(inst,h,100); okpb,pb=run(r,h,100)
        x=feats(inst,h,po.heads_tails(inst,0,[0]*n)[0],po.heads_tails(inst,0,[0]*n)[1],sf,sb)
        x += [pf.get('memo',100),pb.get('memo',100),pf.get('rsi_hits',0),pb.get('rsi_hits',0),
              pf.get('forced',0),pb.get('forced',0),pf.get('nodes',100),pb.get('nodes',100)]
        rows.append(dict(inst=inst,opt=o,h=h,hmod=hmod,f=sf['nodes'],b=sb['nodes'],x=x))
print('rows',len(rows),'tried',tried,'time',round(time.time()-t0,2))
pickle.dump(rows,open('exp/v33/train3.pkl','wb'))
print('NO',sum(x['f'] for x in rows if x['hmod']==-1),sum(x['b'] for x in rows if x['hmod']==-1))
print('YES',sum(x['f'] for x in rows if x['hmod']==0),sum(x['b'] for x in rows if x['hmod']==0))
