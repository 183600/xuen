import sys, pickle
sys.path.insert(0,'exp/v13')
import po

def load(p):
    d=pickle.load(open(p,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

def rules(inst,h):
    n=inst['n']; p=inst['p']; m=inst['m']
    est,q=po.heads_tails(inst,0,[0]*n)
    r=[est[i] for i in range(n)]; d=[h-q[i] for i in range(n)]
    dead=any(r[i]+p[i]>d[i] for i in range(n))
    pts=set([0,h])
    for i in range(n):
        for v in (r[i],d[i],r[i]+p[i],d[i]-p[i]):
            if 0<=v<=h: pts.add(v)
    pts=sorted(pts)
    eclose=False; aclose=False
    for ia in range(len(pts)):
        for ib in range(ia+1,len(pts)):
            a,b=pts[ia],pts[ib]; L=b-a; cap=m*L
            we=0; wa=0
            for i in range(n):
                if d[i]<r[i]: continue
                ov=max(0,min(d[i],b)-max(r[i],a))
                we+=max(0,p[i]-(d[i]-r[i])+ov)
                wa+=max(0,min(p[i],L,r[i]+p[i]-a,b-d[i]+p[i]))
            if we>cap: eclose=True
            if wa>cap: aclose=True
    return dead,eclose,aclose

rows=[]
for tag,path in [('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
                 ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]:
    for k,rec in enumerate(load(path)):
        inst=rec['inst']; h=rec['opt']-1
        dead,e,a=rules(inst,h)
        rows.append((tag,k,dead,e,a))
print('dead',sum(x[2] for x in rows),'e-close',sum(x[3] for x in rows),'a-close',sum(x[4] for x in rows))
print('e but not a:',[(t,k) for t,k,d,e,a in rows if e and not a])
print('a but not e:',[(t,k) for t,k,d,e,a in rows if a and not e])
print('neither:',[(t,k) for t,k,d,e,a in rows if not d and not a])
