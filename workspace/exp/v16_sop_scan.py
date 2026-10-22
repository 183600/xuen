import sys,pickle,time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15')
import po
SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]

def tight_chains(inst,h,cap=100):
    n=inst['n']; p=inst['p']
    est,q=po.heads_tails(inst,0,[0]*n)
    slack=[h-(est[i]+p[i]+q[i]) for i in range(n)]
    zero=[i for i in range(n) if slack[i]==0]
    zs=set(zero)
    succ={i:[j for j in inst['succ'][i] if j in zs and est[j]==est[i]+p[i] and q[i]==p[j]+q[j]] for i in zero}
    chains=[]
    def dfs(path):
        if len(chains)>=cap: return
        i=path[-1]
        if not succ[i]:
            chains.append(tuple(path)); return
        for j in succ[i]: dfs(path+[j])
    for i in zero:
        if not any(i in succ[j] for j in zero):  # source in tight subgraph
            dfs([i])
    return chains,est,q,slack

def load(p):
    d=pickle.load(open(p,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]

for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst,opt=rec['inst'],rec['opt']; h=opt-1
        ch,est,q,slack=tight_chains(inst,h)
        if ch:
            print(tag,k,'n',inst['n'],'opt',opt,'chains',len(ch),'first',ch[0],'len',sum(inst['p'][i] for i in ch[0]))
