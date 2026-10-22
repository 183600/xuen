import sys,pickle,itertools
sys.path.insert(0,'exp/v13')
import po

def fits(occ,s,p):
    e=s+p
    for x,y in occ:
        if s<y and x<e: return False
    return True

def place(items,r,d,el,obs_by,m,a,b,nodecap=300000):
    order=sorted(items,key=lambda i:(r[i],d[i]))
    nodes=[0]
    def dfs(pos,occ):
        nodes[0]+=1
        if nodes[0]>nodecap: raise TimeoutError
        if pos==len(order): return True
        i=order[pos]
        lo=max(r[i],a); hi=min(d[i]-p[i],b-p[i])
        for k in el[i]:
            for s in range(lo,hi+1):
                if fits(occ[k]+obs_by[k],s,p[i]):
                    occ[k].append((s,s+p[i]))
                    if dfs(pos+1,occ): return True
                    occ[k].pop()
        return False
    return dfs(0,[[] for _ in range(m)]),nodes[0]

def chain_scheds(chain,p,est,q,h,delta):
    # enumerate start vectors with total span <= sum p + delta
    out=[]
    def dfs(j,prev_end,starts,span):
        if j==len(chain):
            i=chain[-1]
            if starts[-1]+p[i] <= h-q[i]: out.append(tuple(starts))
            return
        i=chain[j]
        lo=est[i] if j==0 else prev_end
        hi=h-q[i]-p[i]-(sum(p[x] for x in chain[j+1:]))  # leave room for rest
        for s in range(lo,min(hi,h)+1):
            if s-prev_end + span > delta: continue
            dfs(j+1,s+p[i],starts+[s],span+s-prev_end)
    dfs(0,est[chain[0]],(h*0)*0+[],0) if False else None
    # simpler: enumerate recursively with base est[first]
    out=[]
    def rec(j,prev_end,starts,gap):
        if j==len(chain):
            out.append(tuple(starts)); return
        i=chain[j]
        lo=est[chain[0]] if j==0 else prev_end
        # total span constraint: last end <= est[first]+L+delta roughly
        maxend=est[chain[0]]+sum(p[x] for x in chain)+delta
        hi=min(maxend-p[i], h-q[i]-p[i])
        for s in range(lo,hi+1):
            g=gap+(s-prev_end if j>0 else s-est[chain[0]])
            if g>delta: continue
            rec(j+1,s+p[i],starts+[s],g)
    rec(0,est[chain[0]],[],0)
    return out

def residual_infeasible(inst,h,chain,sched,a,b,forced,nodecap=300000):
    n,m,p=inst['n'],inst['m'],inst['p']; el=inst['elig']
    est,q=po.heads_tails(inst,0,[0]*n); r=list(est); d=[h-q[i] for i in range(n)]
    obs=[]
    for i,s in zip(chain,sched):
        x,y=max(s,a),min(s+p[i],b)
        if x<y: obs.append((i,x,y))
    for i,s in forced.items():
        x,y=max(s,a),min(s+p[i],b)
        if x<y: obs.append((i,x,y))
    items=[i for i in range(n) if i not in chain and i not in forced and r[i]>=a and d[i]<=b]
    # quick capacity
    tot=sum(p[i] for i in items)+sum(y-x for _,x,y in obs)
    if tot>m*(b-a): return True,0
    if not items: return False,0
    nodes=0
    for ass in itertools.product(range(m),repeat=len(obs)):
        ok=True; ob=[[] for _ in range(m)]
        for (i,x,y),k in zip(obs,ass):
            if k not in el[i]: ok=False;break
            if any(x<y2 and x2<y for x2,y2 in ob[k]): ok=False;break
            ob[k].append((x,y))
        if not ok: continue
        try:
            good,nd=place(items,r,d,el,ob,m,a,b,nodecap)
        except TimeoutError:
            return None,nodes
        nodes+=nd
        if good: return False,nodes
    return True,nodes

if __name__=='__main__':
    d=pickle.load(open('exp/v13/hard3.pkl','rb')); rec=d[5]; inst,opt=rec[0],rec[1]
    h=opt-1; n,m,p=inst['n'],inst['m'],inst['p']
    est,q=po.heads_tails(inst,0,[0]*n)
    print('h',h,'est',est,'q',q)
    chain=[0,2,4,10,11]
    print('chain len',sum(p[i] for i in chain),'slack',h-(est[chain[0]]+sum(p[i] for i in chain)+q[chain[-1]]))
    sch=chain_scheds(chain,p,est,q,h,1)
    print('schedules',len(sch),sch[:10])
    # candidate windows
    starts=sorted(set(est+[h-q[i]-p[i] for i in range(n)]))
    ends=sorted(set([h-q[i] for i in range(n)]+[est[i]+p[i] for i in range(n)]))
    cands=[]
    for a in starts:
        for b in ends:
            if b-a<10: continue
            cands.append((a,b))
    best=None
    for (a,b) in cands:
        for si,s in enumerate(sch):
            res,nd=residual_infeasible(inst,h,chain,s,a,b,{},nodecap=60000)
            if res:
                print('INFEASIBLE window',a,b,'sched',s,'nodes',nd); best=(a,b,s,nd); break
        if best: break
    print('best',best)
