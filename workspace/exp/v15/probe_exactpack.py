import sys, pickle
sys.path.insert(0,'exp/v13')
import po

def load(path):
    d=pickle.load(open(path,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

def min_bins(items, cap, ub):
    """exact: can items fit in <=m bins of capacity cap? returns True/False."""
    items=sorted(items, reverse=True)
    n=len(items)
    if not items: return True
    if sum(items)>ub*cap: return False
    bins=[0]*ub
    def dfs(j):
        if j==n: return True
        s=items[j]; seen=set()
        for k in range(ub):
            if bins[k]+s<=cap and bins[k] not in seen:
                seen.add(bins[k]); bins[k]+=s
                if dfs(j+1): return True
                bins[k]-=s
            if bins[k]==0: break
        return False
    return dfs(0)

res={
 'hard3#2':('exp/v13/hard3.pkl',2),'hard3#3':('exp/v13/hard3.pkl',3),
 'hard3#5':('exp/v13/hard3.pkl',5),'hard3#10':('exp/v13/hard3.pkl',10),
 'large_a#6':('exp/v14/large_a.pkl',6),'large_het#1':('exp/v14/large_het.pkl',1)}
for name,(path,k) in res.items():
    rec=load(path)[k]; inst=rec['inst']; opt=rec['opt']; h=opt-1
    n=inst['n']; p=inst['p']; m=inst['m']
    est0,q0=po.heads_tails(inst,0,[0]*n)
    tasks=list(po.bititer(inst['full']))
    r=[est0[i] for i in tasks]; d=[h-q0[i] for i in tasks]; ps=[p[i] for i in tasks]
    starts=sorted(set(r)|set(d[i]-ps[i] for i in range(n)))
    ends=sorted(set(d)|set(r[i]+ps[i] for i in range(n)))
    found=[]
    for a in starts:
        for b in ends:
            C=b-a
            if C<=0: continue
            idx=[i for i in range(n) if r[i]>=a and d[i]<=b]
            if len(idx)<2: continue
            items=[ps[i] for i in idx]
            if sum(items)>m*C: continue          # already INT
            if not min_bins(items,C,m):
                found.append((a,b,C,len(idx),sum(items),items))
    print(name,'n',n,'OPT',opt,'windows with volume-fit but unpackable:',len(found))
    for f in found[:3]: print('   ',f[:5],f[5])
