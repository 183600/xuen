import sys, pickle
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15')
import po, pace_i, mint

def load(p):
    d=pickle.load(open(p,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

def root_state(inst,h):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    rem=inst['full']; A=(0,)*inst['m']
    return rem,A,est,q

def exact_pack_indep(items,caps,elig=None,m=None):
    # independent DFS, no symmetry breaking at all
    items=sorted(items,reverse=True); bins=[0]*len(caps)
    def dfs(j):
        if j==len(items): return True
        s=items[j]
        for k in range(len(caps)):
            if elig is not None and k not in elig: continue
            if bins[k]+s<=caps[k]:
                bins[k]+=s
                if dfs(j+1): return True
                bins[k]-=s
        return False
    return dfs(0)

for tag,path,k in [('hard3#3','exp/v13/hard3.pkl',3),('hard3#10','exp/v13/hard3.pkl',10),
                   ('large_a#6','exp/v14/large_a.pkl',6)]:
    rec=load(path)[k]; inst=rec['inst']; opt=rec['opt']; h=opt-1
    (ok,_),st=pace_i.decide(inst,h,mode='pot',mint_depth=0,packset_depth=0)
    w=st['root_wit']
    rem,A,est,q=root_state(inst,h)
    tasks=list(po.bititer(rem)); n=len(tasks)
    r=[est[i] for i in tasks]; d=[h-q[i] for i in tasks]; ps=[inst['p'][i] for i in tasks]
    print('==',tag,'h',h,'NO',not ok,'witness',w[0] if w else None)
    if w[0]=='mint':
        _,S,W,cap=w
        W2=sum(mint.beta(j,ps,r,d,S) for j in range(n))
        cap2=mint.cap_union(S,A,inst['m'])
        print('   S',S,'W',W,'cap',cap,'recomputed',W2,cap2,'valid',mint.check_mint(S,n,ps,r,d,A,inst['m'],W,cap),
              'ratios',round(W/cap,4))
        print('   beta vector',[mint.beta(j,ps,r,d,S) for j in range(n)])
    if w[0]=='packset':
        a,b,items,caps,tn=w[1]
        om=[i for i in range(n) if r[i]>=a and d[i]<=b]
        print('   window',a,b,'omega local',om,'items',items,'caps',caps,'tree',tn)
        print('   volume',sum(items),'cap',sum(caps),'independent feasible?',exact_pack_indep(items,caps))
    # YES at OPT
    (ok2,out),st2=pace_i.decide(inst,opt,mode='pot',mint_depth=0,packset_depth=0)
    print('   YES at OPT:',ok2,'nodes',st2['nodes'])
