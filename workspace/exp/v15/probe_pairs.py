import sys, pickle
sys.path.insert(0,'exp/v13')
import po

def load(path):
    d=pickle.load(open(path,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

def slacks(inst,h):
    n=inst['n']; p=inst['p']; m=inst['m']
    est,q=po.heads_tails(inst,0,[0]*n)
    r=[est[i] for i in range(n)]; d=[h-q[i] for i in range(n)]; ps=p
    pts=set([0,h])
    for i in range(n):
        for v in (r[i],d[i],r[i]+ps[i],d[i]-ps[i]):
            if 0<=v<=h: pts.add(v)
    pts=sorted(pts)
    def slack(a,b):
        L=b-a; cap=m*L; W=0
        for i in range(n):
            v=min(ps[i],L,r[i]+ps[i]-a,b-d[i]+ps[i]); W+=max(0,v)
        return cap-W
    return pts,slack

for name,path,k,S in [('hard3#3','exp/v13/hard3.pkl',3,[(22,23),(28,31)]),
                      ('hard3#10','exp/v13/hard3.pkl',10,[(22,23),(26,27)])]:
    rec=load(path)[k]; inst=rec['inst']; h=rec['opt']-1
    pts,sl=slacks(inst,h)
    print(name,'components',[(a,b,sl(a,b)) for a,b in S])
    allsl=sorted(((sl(a,b),a,b) for i,a in enumerate(pts) for b in pts[i+1:]))[:12]
    print('   tightest single:',allsl[:8])
