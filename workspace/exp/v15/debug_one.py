import sys, pickle
sys.path.insert(0,'exp/v13')
import po

def load(path):
    d=pickle.load(open(path,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]
rec=load('exp/v13/hard3.pkl')[2]; inst=rec['inst']; h=rec['opt']-1; n=inst['n']
est0,q0=po.heads_tails(inst,0,[0]*n)
p=inst['p']
print('n',n,'OPT',rec['opt'],'h',h)
for i in range(n):
    print(i,'p',p[i],'r',est0[i],'q',q0[i],'d',h-q0[i],'window',est0[i],h-q0[i]-p[i],
          'viol' if est0[i]+p[i]+q0[i]>h else '')
a,b=14,15
tot=0
for i in range(n):
    r=est0[i]; d=h-q0[i]; pi=p[i]
    v=min(pi,b-a,r+pi-a,b-d+pi)
    v=max(0,v)
    if v: print('  task',i,'alpha',v,'r+p-a',r+pi-a,'b-d+p',b-d+pi)
    tot+=v
print('W',tot,'cap',3*(b-a))

print('--- cells ---')
pts=set([0,h])
for i in range(n):
    for v in (est0[i], h-q0[i], est0[i]+p[i], h-q0[i]-p[i]):
        if 0<=v<=h: pts.add(v)
pts=sorted(pts); P=len(pts)-1
C=[pts[c+1]-pts[c] for c in range(P)]
cap=[sum(max(0, pts[c+1]-max(pts[c],0)) for k in range(3)) for c in range(P)]
for c in range(P):
    if pts[c] in (13,14,15,16,17): print(c,pts[c],pts[c+1],'len',C[c],'cap',cap[c])
