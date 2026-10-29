import sys, pickle, itertools
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15')
import po, mint

def load(p):
    d=pickle.load(open(p,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

def allints(inst,h):
    n=inst['n']; p=inst['p']; m=inst['m']
    est,q=po.heads_tails(inst,0,[0]*n)
    r=[est[i] for i in range(n)]; d=[h-q[i] for i in range(n)]; ps=p
    pts=set([0,h])
    for i in range(n):
        for v in (r[i],d[i],r[i]+ps[i],d[i]-ps[i]):
            if 0<=v<=h: pts.add(v)
    pts=sorted(pts)
    out=[]
    for ia in range(len(pts)):
        for ib in range(ia+1,len(pts)):
            a,b=pts[ia],pts[ib]; L=b-a; cap=m*L; W=0
            for i in range(n):
                W+=max(0,min(ps[i],L,r[i]+ps[i]-a,b-d[i]+ps[i]))
            out.append((a,b,cap-W))
    return r,d,ps,out

for name,path,k in [('hard3#2','exp/v13/hard3.pkl',2),('hard3#5','exp/v13/hard3.pkl',5),('large_het#1','exp/v14/large_het.pkl',1)]:
    rec=load(path)[k]; inst=rec['inst']; h=rec['opt']-1; n=inst['n']
    r,d,ps,ints=allints(inst,h)
    for tau in (1,2,3,4):
        cand=[x for x in ints if x[2]<=tau]
        # greedy disjoint subset by endpoint
        cand=sorted(cand,key=lambda t:t[2])
        # enumerate disjoint triples
        best=0; arg=None; cnt=0
        for x,y,z in itertools.combinations(cand,3):
            S=[(x[0],x[1]),(y[0],y[1]),(z[0],z[1])]
            S=sorted(S)
            if not (S[0][1]<=S[1][0] and S[1][1]<=S[2][0]): continue
            cnt+=1
            if cnt>20000: break
            sl,W=mint.union_slack(S,n,ps,r,d,(0,)*inst['m'],inst['m'])
            if -sl>best: best=-sl; arg=(S,W)
        print(name,'tau',tau,'|cand|',len(cand),'triples',cnt,'best violation',best,arg)
