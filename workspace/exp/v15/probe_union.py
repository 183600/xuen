import sys, pickle, itertools
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14')
import po, pace

def load(path):
    d=pickle.load(open(path,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

def overlap(s,p,S):
    # measure of [s,s+p] cap S, S list of (a,b) disjoint
    tot=0
    for a,b in S:
        lo=max(s,a); hi=min(s+p,b)
        if hi>lo: tot+=hi-lo
    return tot

def union_slack(inst,rem,A,est,q,h,intervals):
    tasks=list(po.bititer(rem)); n=len(tasks); m=inst['m']; p=inst['p']
    r=[est[i] for i in tasks]; ps=[p[i] for i in tasks]; d=[h-q[i] for i in tasks]
    cap=0
    for a,b in intervals:
        for k in range(m):
            lo=max(a,A[k])
            if b>lo: cap+=b-lo
    W=0
    for i in range(n):
        best=min(overlap(s,ps[i],intervals) for s in range(r[i], d[i]-ps[i]+1)) if d[i]-ps[i]>=r[i] else 0
        W+=best
    return cap-W

six={'hard3#2':('exp/v13/hard3.pkl',2),'hard3#3':('exp/v13/hard3.pkl',3),
 'hard3#5':('exp/v13/hard3.pkl',5),'hard3#10':('exp/v13/hard3.pkl',10),
 'large_a#6':('exp/v14/large_a.pkl',6),'large_het#1':('exp/v14/large_het.pkl',1)}
for name,(path,k) in six.items():
    rec=load(path)[k]; inst=rec['inst']; h=rec['opt']-1; n=inst['n']; p=inst['p']
    est0,q0=po.heads_tails(inst,0,[0]*n)
    rem=inst['full']; A=(0,)*inst['m']
    tasks=list(po.bititer(rem))
    r=[est0[i] for i in tasks]; ps=[p[i] for i in tasks]; d=[h-q0[i] for i in tasks]
    pts=sorted(set(r)|set(d)|set(d[i]-ps[i] for i in range(n))|set(r[i]+ps[i] for i in range(n)))
    pts=[x for x in pts if 0<=x<=h]
    best1=10**9; best2=10**9; arg2=None
    ones=[[(pts[i],pts[j])] for i in range(len(pts)) for j in range(i+1,len(pts))]
    for S in ones:
        v=union_slack(inst,rem,A,est0,q0,h,S)
        if v<best1: best1=v
    # two disjoint intervals
    for i in range(len(pts)):
        for j in range(i+1,len(pts)):
            for k2 in range(j+1,len(pts)):
                for l in range(k2+1,len(pts)):
                    S=[(pts[i],pts[j]),(pts[k2],pts[l])]
                    v=union_slack(inst,rem,A,est0,q0,h,S)
                    if v<best2: best2=v; arg2=S
    print(f"{name} n={n} OPT={rec['opt']}  min slack single={best1}  union2={best2} {arg2}")
