import sys,pickle,itertools
sys.path.insert(0,'exp/v13')
import po

def ov(s,p,a,b):
    lo=max(s,a); hi=min(s+p,b); return max(0,hi-lo)
def ou(s,p,S): return sum(ov(s,p,a,b) for a,b in S)

def argmin(r,d,p,S):
    lo,hi=r,d-p
    if hi<lo: return []
    vals=[(ou(s,p,S),s) for s in range(lo,hi+1)]
    m=min(v for v,s in vals)
    return [s for v,s in vals if v==m]

def binpack(items,caps):
    items=sorted(items,reverse=True)
    bins=[0]*len(caps)
    def dfs(i):
        if i==len(items): return True
        seen=set()
        for k in range(len(caps)):
            if bins[k]+items[i]<=caps[k] and bins[k] not in seen:
                seen.add(bins[k]); bins[k]+=items[i]
                if dfs(i+1): return True
                bins[k]-=items[i]
        return False
    return dfs(0)

# hard3#2 root
d=pickle.load(open('exp/v13/hard3.pkl','rb')); rec=d[2]; inst,opt=rec[0],rec[1]
n,m,p=inst['n'],inst['m'],inst['p']; h=opt-1
est,q=po.heads_tails(inst,0,[0]*n); r=list(est); dd=[h-q[i] for i in range(n)]
print('h',h,'slack_i',[h-(est[i]+p[i]+q[i]) for i in range(n)])
# zero slack chain 0,1,5,7,10,11: fixed starts
chain=[0,1,5,7,10,11]
starts={}; t=0
for i in chain:
    starts[i]=t; t+=p[i]
print('chain starts',starts,'end',t)
# tight window
a,b=11,28; S=[(a,b)]
# forced unique argmin
forced={}
for i in range(n):
    ar=argmin(r[i],dd[i],p[i],S)
    if len(ar)==1 and ar[0]>r[i] or (len(ar)==1 and ar[0]<dd[i]-p[i]):
        forced[i]=ar[0]
print('unique argmin',forced)
# obstacles = chain blocks inside window + forced blocks intersecting
obs=[]
for i in chain:
    s=starts[i]
    if s+p[i]>a and s<b:
        obs.append((i,max(s,a),min(s+p[i],b)))
for i,s in forced.items():
    if s+p[i]>a and s<b and i not in chain:
        obs.append((i,max(s,a),min(s+p[i],b)))
print('obstacles',obs)
# items fully inside window, not obstacles/chain
items=[i for i in range(n) if i not in starts and i not in forced and r[i]>=a and dd[i]<=b]
print('items',[(i,p[i]) for i in items], 'sum',sum(p[i] for i in items))
# enumerate assignments of obstacles to machines, invalid if overlap on same machine
el=inst['elig']
cnt=0; feas=0
for ass in itertools.product(range(m),repeat=len(obs)):
    ok=True; caps=[b-a]*m; load=[[] for _ in range(m)]
    for (i,x,y),k in zip(obs,ass):
        if k not in el[i]: ok=False;break
        for (x2,y2) in load[k]:
            if x<y2 and x2<y: ok=False;break
        if not ok: break
        load[k].append((x,y)); caps[k]-=(y-x)
    if not ok: continue
    cnt+=1
    if binpack([p[i] for i in items],caps):
        feas+=1
        if feas==1: print('FEASIBLE assignment',ass,'caps',caps)
print('valid assignments',cnt,'feasible packings',feas)
