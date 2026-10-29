import sys, json, pickle, time, math
sys.path.insert(0,'.'); sys.path.insert(0,'v08'); sys.path.insert(0,'v07')
import exp_da as E, ip
from lp import frac_pack, frac_lb, check_witness

R = json.load(open('v08/results.json'))
pool = pickle.load(open('pool30.pkl','rb'))

def mk(p,m):
    n=len(p); pred=[[] for _ in range(n)]; succ=[[] for _ in range(n)]
    inst={'n':n,'m':m,'p':p,'pred':pred,'succ':succ,'ep':0.0,'pmax':max(p)}
    E.compute_desc(inst); inst['pmask']=[0]*n
    return inst

def dff(sizes,m):
    best=0
    for t in range(1,max(sizes)+1):
        b=sum(s//t for s in sizes)
        best=max(best,t*((b+m-1)//m))
    return best

def pack_opt(sizes,m):
    # exact bin packing optimum via load-vector DP
    states={(0,)*m}
    for s in sizes:
        ns=set()
        for L in states:
            for k in range(m):
                t=list(L); t[k]+=s; ns.add(tuple(sorted(t)))
        states=ns
    return min(max(L) for L in states)

rows=[]
for fam in ('dense','part2','part3'):
    for r in R[fam]:
        if fam=='dense':
            inst=pool[r['k']][0]
        else:
            inst=mk(r['p'],r['m'])
        p=inst['p']; m=inst['m']; n=inst['n']; OPT=r['OPT']
        S=0; A=(0,)*m; c=(-1,)*n
        L0=E.lower_L0(inst,S,A,c)
        LD=dff(p,m)
        LP=ip.pack_lb(inst,S,A,c,L0,OPT)
        t0=time.time(); LC=frac_lb(p,m,L0,OPT); t_lp=time.time()-t0
        tau,w,info=frac_pack(p,[OPT-1]*m)
        ok,msg=check_witness(p,[OPT-1]*m,[set(range(n)) for _ in range(m)],w,m)
        sup=sum(1 for x in w if x>1e-9)
        rows.append(dict(fam=fam,k=r['k'],n=n,m=m,OPT=OPT,p=p,L0=L0,LDFF=LD,
                         LPACK=LP,LCFG=LC,tau=tau,supp=sup,t_lp=round(t_lp,5),
                         cert_ok=ok,cert_msg=msg,tau_gt=(tau>m+1e-9)))
json.dump(rows,open('study.json','w'),indent=1)

for fam in ('dense','part2','part3'):
    rs=[x for x in rows if x['fam']==fam]
    print('==',fam,len(rs))
    for key in ('L0','LDFF','LCFG','LPACK'):
        c=sum(1 for x in rs if x[key]>=x['OPT'])
        print('  %-6s closes %2d/%d'%(key,c,len(rs)))
    lpcl=[x for x in rs if x['LCFG']>=x['OPT']]
    print('  LP closes, support size:',sorted(x['supp'] for x in lpcl))
    print('  LP closed but DFF did not:',sum(1 for x in lpcl if x['LDFF']<x['OPT']))
    bad=[x for x in lpcl if not x['cert_ok']]
    print('  witness failures:',len(bad), bad[:2])
    print('  sum t_lp %.3fs'%sum(x['t_lp'] for x in rs))
    for x in rs:
        if x['LCFG']<x['OPT']:
            print('   gap',x['k'],'n',x['n'],'m',x['m'],'OPT',x['OPT'],'L0',x['L0'],'DFF',x['LDFF'],'CFG',x['LCFG'],'PACK',x['LPACK'],'tau',round(x['tau'],3))
