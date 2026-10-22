import sys, pickle
sys.path.insert(0,'exp/v13')
import po

def load(p):
    d=pickle.load(open(p,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

def e_rule_closes(inst,h):
    n=inst['n']; p=inst['p']; m=inst['m']
    est,q=po.heads_tails(inst,0,[0]*n)
    r=[est[i] for i in range(n)]; d=[h-q[i] for i in range(n)]
    pts=set([0,h])
    for i in range(n):
        for v in (r[i],d[i],r[i]+p[i],d[i]-p[i]):
            if 0<=v<=h: pts.add(v)
    pts=sorted(pts)
    for ia in range(len(pts)):
        for ib in range(ia+1,len(pts)):
            a,b=pts[ia],pts[ib]; L=b-a; cap=m*L
            tot=0
            for i in range(n):
                if d[i]<r[i]+p[i]: return True
                ov=max(0,min(d[i],b)-max(r[i],a))
                tot+=max(0,p[i]-(d[i]-r[i])+ov)
            if tot>cap: return True
    return False

tot=0; pre=0
for tag,path in [('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
                 ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]:
    for k,rec in enumerate(load(path)):
        inst=rec['inst']; h=rec['opt']-1
        e=e_rule_closes(inst,h)
        tot+=1; pre+=e
        if e: print('preemptive-close',tag,k,'OPT',rec['opt'])
print('instances',tot,'closed by preemptive e-rule',pre)
