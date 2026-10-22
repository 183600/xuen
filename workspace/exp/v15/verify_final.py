import sys, pickle
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15')
import po, pace_i, mint
def load(p):
    d=pickle.load(open(p,'rb')); return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]
def state(inst,h):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    return est,q,[est[i] for i in range(n)],[h-q[i] for i in range(n)]
for tag,path,k in [('hard3#3','exp/v13/hard3.pkl',3),('hard3#10','exp/v13/hard3.pkl',10),('large_a#6','exp/v14/large_a.pkl',6)]:
    rec=load(path)[k]; inst=rec['inst']; h=rec['opt']-1; n=inst['n']
    (ok,_),st=pace_i.decide(inst,h,mode='pot',mint_depth=0,packset_depth=0)
    w=st['root_wit']
    if w[0]=='mint':
        _,S,W,cap=w; est,q,r,d=state(inst,h)
        ps=inst['p']
        okc=mint.check_mint(S,n,ps,r,d,(0,)*inst['m'],inst['m'],W,cap)
        print(tag,'MINT S',S,'W',W,'cap',cap,'valid',okc,'betas',sum(1 for j in range(n) if mint.beta(j,ps,r,d,S)))
    else:
        cert=w[1]; est,q,r,d=state(inst,h)
        okc=mint.check_packset(cert,n,inst['p'],r,d,inst['elig'],inst['m'])
        print(tag,'PACKSET window',cert['a'],cert['b'],'items',cert['items'],'caps',cert['caps'],
              'tree',cert['nodes'],'valid',okc)
