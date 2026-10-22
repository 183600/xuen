import sys, pickle, random
sys.path.insert(0,'exp/v13')
import po

def load(path):
    d=pickle.load(open(path,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

def setup(inst, rem, A, est, q, h):
    p=inst['p']; m=inst['m']
    tasks=list(po.bititer(rem))
    r={i:est[i] for i in tasks}; d={i:h-q[i] for i in tasks}; ps={i:p[i] for i in tasks}
    pts=set([0,h])
    for i in tasks:
        for v in (r[i], d[i], r[i]+ps[i], d[i]-ps[i]):
            if 0<=v<=h: pts.add(v)
    pts=sorted(pts); P=len(pts)-1
    C=[pts[c+1]-pts[c] for c in range(P)]
    cap=[sum(max(0, pts[c+1]-max(pts[c],A[k])) for k in range(m)) for c in range(P)]
    return tasks,r,d,ps,pts,C,cap

def ov(s,p,t0,t1):
    lo=max(s,t0); hi=min(s+p,t1)
    return hi-lo if hi>lo else 0

def best_response(tasks,r,d,ps,pts,C,cap,x):
    P=len(C); starts={}; D=[0]*P
    for i in tasks:
        lo=r[i]; hi=d[i]-ps[i]
        cands=sorted(set([s for s in pts if lo<=s<=hi]+[lo,hi]))
        bv=None; bs=lo
        for s in cands:
            v=0
            for c in range(P):
                if x[c]: v+=ov(s,ps[i],pts[c],pts[c+1])
            if bv is None or v<bv: bv=v; bs=s
        starts[i]=bs
        for c in range(P): D[c]+=ov(bs,ps[i],pts[c],pts[c+1])
    return starts,D

def V_of(tasks,r,d,ps,pts,C,cap,x):
    starts,D=best_response(tasks,r,d,ps,pts,C,cap,x)
    return sum(D[c]-cap[c] for c in range(len(x)) if x[c]), starts, D

def search(tasks,r,d,ps,pts,C,cap,inits,iters=100):
    P=len(C); best=(-10**9,None)
    for x in inits:
        x=x[:] 
        for it in range(iters):
            v,starts,D=V_of(tasks,r,d,ps,pts,C,cap,x)
            if v>best[0]: best=(v,x[:])
            nx=[1 if D[c]>cap[c] else 0 for c in range(P)]
            if nx==x: break
            x=nx
    return best

six={'hard3#2':('exp/v13/hard3.pkl',2),'hard3#3':('exp/v13/hard3.pkl',3),
 'hard3#5':('exp/v13/hard3.pkl',5),'hard3#10':('exp/v13/hard3.pkl',10),
 'large_a#6':('exp/v14/large_a.pkl',6),'large_het#1':('exp/v14/large_het.pkl',1)}
random.seed(2)
for name,(path,k) in six.items():
    rec=load(path)[k]; inst=rec['inst']; h=rec['opt']-1; n=inst['n']
    est0,q0=po.heads_tails(inst,0,[0]*n)
    tasks,r,d,ps,pts,C,cap=setup(inst,inst['full'],(0,)*inst['m'],tuple(est0),q0,h)
    P=len(C)
    inits=[[1]*P]+[[1 if c==j else 0 for c in range(P)] for j in range(P)]
    v,x=search(tasks,r,d,ps,pts,C,cap,inits,iters=100)
    sup=[(pts[c],pts[c+1]) for c in range(P) if x[c]]
    print(f"{name} n={n} OPT={rec['opt']} MW value={v} support={sup[:6]}{'...' if len(sup)>6 else ''}")
