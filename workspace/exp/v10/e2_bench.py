import sys, json, pickle, time
sys.path.insert(0,'exp/v10'); sys.path.insert(0,'exp/v08'); sys.path.insert(0,'exp/v07'); sys.path.insert(0,'exp')
import exp_da as E
from profile import profile_dec

R=json.load(open('exp/v08/results.json'))
pool=pickle.load(open('exp/pool30.pkl','rb'))

def dppack(p,m,H,est=None,q=None):
    """profile DP on the capacity layer; eligibility from est/q if given."""
    n=len(p)
    if est is None:
        return profile_dec(p,[H]*m)
    elig=[]
    caps=[H]*m
    for i in range(n):
        el=[k for k in range(m) if max(0,est[i])+p[i]+q[i]<=H]
        elig.append(el)
        if not el: return False,[set()],0
    # uniform A=0 -> single symmetry block if all elig equal
    blocks=[(0,m)]
    from profile import _canon
    cur={_canon(tuple(caps),blocks)}; layers=[cur]; tot=1
    idx=sorted(range(n), key=lambda i:(-p[i],i))
    for i in idx:
        nxt=set()
        for r in cur:
            for k in elig[i]:
                if r[k]>=p[i]:
                    t=list(r); t[k]-=p[i]; nxt.add(_canon(t,blocks))
        layers.append(nxt); cur=nxt; tot+=len(nxt)
        if not cur: return False,layers,tot
    return True,layers,tot

rows=[]
for fam in ('dense','part2','part3'):
    for r in R[fam]:
        p=r['p']; m=r['m']; n=len(p); OPT=r['OPT']
        if fam=='dense':
            inst=pool[r['k']][0]
            S=0; A=(0,)*m; c=(-1,)*n
            est,q=E.heads_tails(inst,S,c)
        else:
            est=[0]*n; q=[0]*n
        # L_PACK by profile DP binary search
        lo=r['L0']; hi=OPT
        t0=time.time()
        def feas(H): return dppack(p,m,H,est,q)[0]
        if feas(lo): LP=lo
        elif not feas(hi): LP=hi+1
        else:
            a,b=lo,hi
            while a<b:
                mid=(a+b)//2
                if feas(mid): b=mid
                else: a=mid+1
            LP=a
        dt=time.time()-t0
        ok,layers,ns=dppack(p,m,OPT-1,est,q)
        rows.append(dict(fam=fam,k=r['k'],n=n,m=m,OPT=OPT,LPACK=r['LPACK'],DP=LP,
                         agree=(LP==r['LPACK']),t=round(dt,5),states_root=ns,
                         t_pack=r['t_packlb'],base_nodes=r['base']['nodes'],pack_nodes=r['pack']['nodes']))
json.dump(rows,open('exp/v10/e2.json','w'),indent=1)
for fam in ('dense','part2','part3'):
    rs=[x for x in rows if x['fam']==fam]
    print('==',fam,len(rs),'agree',sum(x['agree'] for x in rs),
          'max states',max(x['states_root'] for x in rs),
          'median states',sorted(x['states_root'] for x in rs)[len(rs)//2],
          'max t',round(max(x['t'] for x in rs),4))
    print('   base nodes median',sorted(x['base_nodes'] for x in rs)[len(rs)//2],
          'max',max(x['base_nodes'] for x in rs))
