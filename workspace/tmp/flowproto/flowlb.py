import sys
from collections import deque
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from po import heads_tails

class Dinic:
    __slots__=('n','g')
    def __init__(self,n): self.n=n; self.g=[[] for _ in range(n)]
    def add(self,u,v,c):
        self.g[u].append([v,c,len(self.g[v])]); self.g[v].append([u,0,len(self.g[u])-1])
    def flow(self,s,t):
        res=0
        while True:
            lvl=[-1]*self.n; lvl[s]=0; q=deque([s])
            while q:
                u=q.popleft()
                for v,c,r in self.g[u]:
                    if c>0 and lvl[v]<0: lvl[v]=lvl[u]+1; q.append(v)
            if lvl[t]<0: return res
            it=[0]*self.n
            def dfs(u,f):
                if u==t: return f
                gu=self.g[u]
                while it[u]<len(gu):
                    e=gu[it[u]]; v,c,r=e
                    if c>0 and lvl[v]==lvl[u]+1:
                        d=dfs(v,min(f,c))
                        if d>0: e[1]-=d; self.g[v][r][1]+=d; return d
                    it[u]+=1
                return 0
            while True:
                f=dfs(s,10**9)
                if not f: break
                res+=f
    def reach(self,s):
        seen=[False]*self.n; seen[s]=True; st=[s]
        while st:
            u=st.pop()
            for v,c,r in self.g[u]:
                if c>0 and not seen[v]: seen[v]=True; st.append(v)
        return seen

def build(inst,h,est,q,parallel=False):
    n,m,p=inst['n'],inst['m'],inst['p']
    T=h
    S=0; off=1; toff=off+n; moff=toff+n*T; sink=moff+m*T
    din=Dinic(sink+1); tot=0
    for i in range(n):
        din.add(S,off+i,p[i]); tot+=p[i]
        lo=max(0,est[i]); hi=min(T,h-q[i])
        for t in range(lo,hi):
            din.add(off+i,toff+i*T+t,1)
            for k in inst['elig'][i]:
                din.add(toff+i*T+t,moff+k*T+t,1)
    for k in range(m):
        for t in range(T):
            din.add(moff+k*T+t,sink,1)
    return din,S,sink,tot

def flowbound(inst, maxtries=200):
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q=heads_tails(inst,0,[0]*n)
    lo=max(est[i]+p[i]+q[i] for i in range(n))
    # energy lb
    lo=max(lo,(sum(p)+m-1)//m)
    def feasible(h):
        if h<=0: return False
        din,S,t,tot=build(inst,h,est,q)
        return din.flow(S,t)==tot
    hi=lo
    while not feasible(hi) and hi<maxtries: hi+=1
    if hi>=maxtries: return lo,None
    while lo<hi:
        mid=(lo+hi)//2
        if feasible(mid): hi=mid
        else: lo=mid+1
    return lo,est

def check_cut(inst,h,est,q,S_reach):
    # S_reach is set of node ids reachable from source in residual graph
    n,m,p=inst['n'],inst['m'],inst['p']; T=h
    off=1; toff=off+n; moff=toff+n*T; sink=moff+m*T
    A=set(S_reach)
    if 0 not in A or sink in A: return False
    cap=0; tot=sum(p); edges=[]
    for i in range(n):
        if 0 in A and off+i not in A: cap+=p[i]
        lo=max(0,est[i]); hi=min(T,h-q[i])
        for t in range(lo,hi):
            u=toff+i*T+t
            if (off+i in A) and (u not in A): cap+=1
            for k in inst['elig'][i]:
                v=moff+k*T+t
                if u in A and v not in A: cap+=1
    for k in range(m):
        for t in range(T):
            v=moff+k*T+t
            if v in A and sink not in A: cap+=1
    return cap<tot,cap,tot

if __name__=='__main__':
    import statistics,time
    rows=[]
    for tag,fn in [('base',base_corpus),('pert',pert_corpus),('stress',stress_corpus)]:
        for row in fn():
            if len(row)==4: name,idx,inst,known=row
            else: idx,known,inst=row; name=tag
            t0=time.time()
            Lf,est=flowbound(inst)
            rows.append((tag,name,idx,inst,known,Lf,time.time()-t0))
    print('n',len(rows))
    diffs=[(known-Lf) for *_,known,Lf,t in rows]
    from collections import Counter
    print('OPT-Lflow',Counter(diffs))
    print('exact',sum(d==0 for d in diffs),'diff1',sum(d==1 for d in diffs),'worse',sum(d>1 for d in diffs))
    print('time',round(sum(r[-1] for r in rows),2))
    # check at opt-1
    bad=0; infeas=0; certok=0
    for tag,name,idx,inst,known,Lf,t in rows:
        h=known-1
        est,q=heads_tails(inst,0,[0]*inst['n'])
        din,S,sink,tot=build(inst,h,est,q)
        f=din.flow(S,sink)
        if f<tot:
            infeas+=1
            R=din.reach(S)
            ok=check_cut(inst,h,est,q,R)
            if ok is True: certok+=1
            else: bad+=1; print('bad cert',tag,name,idx,ok)
    print('at OPT-1 infeas',infeas,'certok',certok,'bad',bad)
