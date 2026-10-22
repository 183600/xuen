import sys, pickle, random
sys.path.insert(0,'exp/v13')
import po

def load(path):
    d=pickle.load(open(path,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

def setup(inst, rem, A, est, q, h):
    n=inst['n']; p=inst['p']; m=inst['m']
    tasks=list(po.bititer(rem))
    r={}; d={}; ps={}
    for i in tasks:
        r[i]=est[i]; d[i]=h-q[i]; ps[i]=p[i]
    pts=set([0,h])
    for i in tasks:
        for v in (r[i], d[i], r[i]+ps[i], d[i]-ps[i]):
            if 0<=v<=h: pts.add(v)
    pts=sorted(pts)
    P=len(pts)-1
    # cells
    C=[pts[c+1]-pts[c] for c in range(P)]
    cap=[sum(max(0, pts[c+1]-max(pts[c],A[k])) for k in range(m)) for c in range(P)]
    return tasks, r, d, ps, pts, C, cap

def overlap(s,p,t0,t1):
    lo=max(s,t0); hi=min(s+p,t1)
    return hi-lo if hi>lo else 0

def best_response(tasks,r,d,ps,pts,C,cap,x):
    P=len(C); starts={}
    D=[0]*P
    for i in tasks:
        lo=r[i]; hi=d[i]-ps[i]
        # candidate starts: critical values in [lo,hi]
        cands=[s for s in pts if lo<=s<=hi]
        # add lo, hi
        cands=sorted(set(cands+[lo,hi]))
        bestv=None; bests=None
        for s in cands:
            v=0
            for c in range(P):
                if x[c]:
                    v+=overlap(s,ps[i],pts[c],pts[c+1])
            if bestv is None or v<bestv:
                bestv=v; bests=s
        starts[i]=bests
        for c in range(P):
            D[c]+=overlap(bests,ps[i],pts[c],pts[c+1])
    return starts,D

def value(x,D,cap):
    return sum((D[c]-cap[c]) for c in range(len(x)) if x[c])

def local_search(inst,rem,A,est,q,h,init_x,inits=1,iters=60):
    tasks,r,d,ps,pts,C,cap=setup(inst,rem,A,est,q,h)
    P=len(C)
    best=(-10**9,None)
    for rep in range(inits):
        x=init_x[:] if rep==0 else [1 if (random.random()<0.25) else 0 for _ in range(P)]
        cur=-10**9
        for it in range(iters):
            starts,D=best_response(tasks,r,d,ps,pts,C,cap,x)
            # given starts, best x = threshold
            nx=[1 if D[c]>cap[c] else 0 for c in range(P)]
            v=value(nx,D,cap)
            if v>cur: cur=v
            if v>best[0]: best=(v,nx[:])
            if nx==x: break
            x=nx
        if best[0]>0: break
    return best

six={'hard3#2':('exp/v13/hard3.pkl',2),'hard3#3':('exp/v13/hard3.pkl',3),
 'hard3#5':('exp/v13/hard3.pkl',5),'hard3#10':('exp/v13/hard3.pkl',10),
 'large_a#6':('exp/v14/large_a.pkl',6),'large_het#1':('exp/v14/large_het.pkl',1)}
random.seed(1)
for name,(path,k) in six.items():
    rec=load(path)[k]; inst=rec['inst']; h=rec['opt']-1; n=inst['n']
    est0,q0=po.heads_tails(inst,0,[0]*n)
    tasks,r,d,ps,pts,C,cap=setup(inst,inst['full'],(0,)*inst['m'],tuple(est0),q0,h)
    P=len(C)
    # init from all-ones and from each single cell
    best=(-10**9,None)
    for init in [[1]*P]+[[1 if c==j else 0 for c in range(P)] for j in range(P)]:
        v,x=local_search(inst,inst['full'],(0,)*inst['m'],tuple(est0),q0,h,init,inits=1,iters=80)
        if v>best[0]: best=(v,x)
    supports=[(pts[c],pts[c+1]) for c in range(P) if best[1] and best[1][c]]
    print(f"{name} n={n} OPT={rec['opt']} best MW value={best[0]} support={supports}")
