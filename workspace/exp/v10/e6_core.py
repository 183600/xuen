import sys, json, pickle, time, random
sys.path.insert(0,'exp/v10'); sys.path.insert(0,'exp/v08'); sys.path.insert(0,'exp/v07'); sys.path.insert(0,'exp')
import exp_da as E, ip
from profile import profile_dec

R=json.load(open('exp/v08/results.json'))
pool=pickle.load(open('exp/pool30.pkl','rb'))

def core_greedy(p,m,H,est=None,q=None):
    """minimal infeasible subset by deletion; DP decides."""
    n=len(p); C=list(range(n))
    def feas(sub):
        if est is None:
            return profile_dec([p[i] for i in sub],[H]*m)[0]
        # eligibility depends on est/q; for uniform A=0
        pp=[p[i] for i in sub]
        el=[[k for k in range(m) if max(0,est[i])+p[i]+q[i]<=H] for i in sub]
        if any(not e for e in el): return False
        from profile import _canon
        cur={_canon(tuple([H]*m),[(0,m)])}; 
        order=sorted(range(len(sub)),key=lambda j:(-pp[j],j))
        for j in order:
            nxt=set()
            for r in cur:
                for k in el[j]:
                    if r[k]>=pp[j]:
                        t=list(r); t[k]-=pp[j]; nxt.add(_canon(t,[(0,m)]))
            cur=nxt
            if not cur: return False
        return True
    if feas(C): return None
    for i in list(C):
        C2=[j for j in C if j!=i]
        if C2 and not feas(C2): C=C2
    return C

rows=[]
for fam in ('dense','part2','part3'):
    for r in R[fam]:
        p=r['p']; m=r['m']; n=len(p); H=r['OPT']-1
        if fam=='dense':
            inst=pool[r['k']][0]; S=0; A=(0,)*m; c=(-1,)*n
            est,q=E.heads_tails(inst,S,c)
        else:
            est=[0]*n; q=[0]*n
        t=time.time(); C=core_greedy(p,m,H,est,q); dt=time.time()-t
        rows.append(dict(fam=fam,k=r['k'],n=n,m=m,kappa=len(C) if C else 0,
                         core=[p[i] for i in C] if C else [],t=round(dt,5)))
json.dump(rows,open('exp/v10/e6.json','w'),indent=1)
for fam in ('dense','part2','part3'):
    rs=[x for x in rows if x['fam']==fam]
    ks=sorted(x['kappa'] for x in rs)
    print('==',fam,len(rs),'kappa min/med/max',ks[0],ks[len(ks)//2],ks[-1],
          'sum t',round(sum(x['t'] for x in rs),3))
    for x in rs[:3]: print('   ',x['n'],x['m'],'core',x['core'])
