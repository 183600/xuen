import sys, json, pickle, random, time
sys.path.insert(0,'exp/v10'); sys.path.insert(0,'exp/v08'); sys.path.insert(0,'exp/v07'); sys.path.insert(0,'exp')
import exp_da as E
from profile import profile_dec, check_profile_cert
R=json.load(open('exp/v08/results.json')); pool=pickle.load(open('exp/pool30.pkl','rb'))
rows=[]
for fam in ('dense','part2','part3'):
    for r in R[fam]:
        p=r['p']; m=r['m']; H=r['OPT']-1
        if fam=='dense':
            inst=pool[r['k']][0]; S=0; A=(0,)*m; c=(-1,)*len(p)
            est,q=E.heads_tails(inst,S,c)
            # eligibility filter: tasks not eligible anywhere -> still NO via DP with empty moves
        else:
            est=[0]*len(p); q=[0]*len(p)
        ok,layers,ns=profile_dec(p,[H]*m)
        acc,msg=check_profile_cert(p,[H]*m,layers) if not ok else (None,'feasible')
        rows.append(dict(fam=fam,n=len(p),m=m,states=ns,cert_nums=ns*m,ok=ok,
                         bbnodes=r['pack']['nodes'],base=r['base']['nodes'],acc=acc))
json.dump(rows,open('exp/v10/e4.json','w'),indent=1)
for fam in ('dense','part2','part3'):
    rs=[x for x in rows if x['fam']==fam and not x['ok']]
    print(fam,'NO cells',len(rs),'accepted',sum(x['acc'] for x in rs),'/',len(rs),
          'cert nums med',sorted(x['cert_nums'] for x in rs)[len(rs)//2],
          'max',max(x['cert_nums'] for x in rs),'| bbnodes med',sorted(x['bbnodes'] for x in rs)[len(rs)//2],
          'max',max(x['bbnodes'] for x in rs))

# tamper tests
rng=random.Random(5); rej=tot=0
for _ in range(300):
    x=rng.choice([z for z in rows if not z['ok']]); fam=x['fam']
    rr=[q for q in R[fam] if len(q['p'])==x['n'] and q['m']==x['m']][0]
    p=rr['p']; m=rr['m']; H=rr['OPT']-1
    ok,layers,ns=profile_dec(p,[H]*m)
    L=[set(s) for s in layers]
    kind=rng.choice(['drop','add','swap'])
    j=rng.randrange(len(L))
    if kind=='drop' and L[j]: L[j].discard(next(iter(L[j])))
    elif kind=='add': L[j].add((999,)*m)
    else:
        k=rng.randrange(len(L)); L[j],L[k]=L[k],L[j]
    acc,msg=check_profile_cert(p,[H]*m,L); tot+=1; rej+= (not acc)
print('tamper rejected',rej,'/',tot)
