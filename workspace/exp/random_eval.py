import sys, random, json
sys.path.insert(0,'.')
import exp_da as E
from proto_tent_root import tent_thresh
rng=random.Random(31415)
rows=[]; tries=0
while len(rows)<60 and tries<400:
    tries+=1
    n=9
    inst=E.gen_instance(n,rng.choice([0.15,0.2,0.25,0.3]),rng.choice([6,8,10,12]),rng,2)
    opt,nd,ok=E.exact_opt(inst,cap=1_500_000)
    if not ok: continue
    S0,A0,c0=0,(0,0),(-1,)*n
    L0=E.lower_L0(inst,S0,A0,c0); U=E.guide(inst,S0,A0,c0)
    old,_=E.thresh(inst,S0,A0,c0,U,L0,'full')
    new,_,_=tent_thresh(inst,S0,A0,c0,U,L0)
    if new>opt: print('UNSOUND',len(rows),new,opt); break
    rows.append(dict(opt=opt,L0=L0,U=U,old=old,new=new,gap=opt-L0,
                     d_old=old-L0,d_new=new-L0))
print('n',len(rows))
print('gap0',sum(1 for r in rows if r['gap']==0))
print('new>L0',sum(1 for r in rows if r['new']>r['L0']),
      'old>L0',sum(1 for r in rows if r['old']>r['L0']),
      'new>old',sum(1 for r in rows if r['new']>r['old']),
      'new<old',sum(1 for r in rows if r['new']<r['old']))
print('sum gap',sum(r['gap'] for r in rows),'d_old',sum(r['d_old'] for r in rows),'d_new',sum(r['d_new'] for r in rows))
print('max new-opt',max(r['new']-r['opt'] for r in rows))
json.dump(rows,open('random_eval.json','w'),indent=1)
