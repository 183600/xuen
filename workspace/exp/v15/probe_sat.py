import sys,pickle
sys.path.insert(0,'exp/v13')
import po

def ov(s,p,a,b):
    lo=max(s,a); hi=min(s+p,b); return max(0,hi-lo)

def overlap_union(s,p,S):
    return sum(ov(s,p,a,b) for a,b in S)

def argmin(r,d,p,S):
    lo,hi=r,d-p
    if hi<lo: return [],None
    vals=[(overlap_union(s,p,S),s) for s in range(lo,hi+1)]
    m=min(v for v,s in vals)
    return [s for v,s in vals if v==m],m

def cap(S,A,m):
    return sum(max(0,b-max(a,A[k])) for a,b in S for k in range(m))

def energy(r,d,p,m,A,S):
    W=0; mand=[]
    for i in range(len(p)):
        ar,_=argmin(r[i],d[i],p[i],S)
        v=min(overlap_union(s,p[i],S) for s in ar) if ar else 0
        mand.append(v); W+=v
    return W,cap(S,A,m)-W,mand

def all_windows(r,d,p,h):
    starts=sorted(set(r+[d[i]-p[i] for i in range(len(p))]+[0]))
    ends=sorted(set(d+[r[i]+p[i] for i in range(len(p))]+[h]))
    out=[]
    for a in starts:
        for b in ends:
            if b>a: out.append((a,b))
    return out

def propagate(r,d,p,m,A,h,verbose=True,maxit=50):
    r=list(r); d=list(d)
    for it in range(maxit):
        tight=[]
        for (a,b) in all_windows(r,d,p,h):
            S=[(a,b)]; W,sl,mand=energy(r,d,p,m,A,S)
            if W>cap(S,A,m):
                return ('OVERLOAD',it,a,b,W,cap(S,A,m),mand)
            if sl==0: tight.append((a,b,W))
        if not tight: return ('FIX',it,r,d,None)
        changed=False
        for (a,b,W) in tight:
            S=[(a,b)]
            for i in range(len(p)):
                ar,mn=argmin(r[i],d[i],p[i],S)
                if not ar: continue
                lo,hi=min(ar),max(ar)
                if lo>r[i] or hi<d[i]-p[i]:
                    r[i]=max(r[i],lo); d[i]=min(d[i],hi+p[i]); changed=True
        if not changed:
            return ('FIX-NOCHANGE',it,r,d,tight)
    return ('MAXIT',it,r,d,None)

SETS=[('hard3','exp/v13/hard3.pkl',[2,5]),('large_het','exp/v14/large_het.pkl',[1])]
for tag,path,idxs in SETS:
    dd=pickle.load(open(path,'rb'))
    for k in idxs:
        rec=dd[k]
        inst,opt=(rec[0],rec[1]) if isinstance(rec,tuple) else (rec['inst'],rec['opt'])
        n,m,p=inst['n'],inst['m'],inst['p']; h=opt-1
        est,q=po.heads_tails(inst,0,[0]*n)
        r=list(est); d=[h-q[i] for i in range(n)]
        print('='*60); print(tag,k,'h',h,'OPT',opt)
        res=propagate(r,d,p,m,[0]*m,h)
        print(res[0],'it',res[1])
        if res[0]=='OVERLOAD':
            print('  window',res[2],res[3],'W',res[4],'cap',res[5]); print('  mand',res[6])
        else:
            print('  r',res[2]); print('  d',res[3])
