import sys, pickle
sys.path.insert(0,'exp/v13')
import po

def load(path):
    d=pickle.load(open(path,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

def ov(s,p,S):
    t=0
    for a,b in S:
        lo=max(s,a); hi=min(s+p,b)
        if hi>lo: t+=hi-lo
    return t

for name,path,k,S in [
  ('hard3#3','exp/v13/hard3.pkl',3,[(20,23),(28,31)]),
  ('hard3#10','exp/v13/hard3.pkl',10,[(22,23),(26,27)])]:
    rec=load(path)[k]; inst=rec['inst']; h=rec['opt']-1; n=inst['n']; p=inst['p']; m=inst['m']
    est0,q0=po.heads_tails(inst,0,[0]*n)
    W=0; det=[]
    for i in range(n):
        r=est0[i]; dm=h-q0[i]; lo=r; hi=dm-p[i]
        vals=[ov(s,p[i],S) for s in range(lo,hi+1)] if hi>=lo else [10**9]
        a=min(vals); W+=a
        if a: det.append((i,p[i],r,dm,a))
    cap=0
    for a,b in S:
        for kk in range(m):
            lo=max(a,0)
            if b>lo: cap+=b-lo
    print(name,'S',S,'W',W,'cap',cap,'slack',cap-W)
    for x in det: print('   ',x)
