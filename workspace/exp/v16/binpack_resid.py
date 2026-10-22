import itertools

def free_intervals(obs, a, b):
    """obs sorted disjoint; return lengths of free gaps in [a,b]."""
    out=[]; cur=a
    for x,y in sorted(obs):
        if x>cur: out.append(x-cur)
        cur=max(cur,y)
    if cur<b: out.append(b-cur)
    return [z for z in out if z>0]

def binpack(items,caps,nodecap=200000):
    items=sorted(items,reverse=True)
    caps=sorted(caps,reverse=True)
    bins=[0]*len(caps); nodes=[0]
    def dfs(i):
        nodes[0]+=1
        if nodes[0]>nodecap: raise TimeoutError
        if i==len(items): return True
        seen=set()
        for k in range(len(caps)):
            if bins[k]+items[i]<=caps[k] and bins[k] not in seen:
                seen.add(bins[k]); bins[k]+=items[i]
                if dfs(i+1): return True
                bins[k]-=items[i]
        return False
    try: return dfs(0),nodes[0]
    except TimeoutError: return None,nodes[0]

def capacity_pack(n,m,p,el,forced,a,b,nodecap=200000):
    """Sound relaxation: after assigning fixed blocks, items must fit into the
    free interval lengths (release/deadline inside the window ignored)."""
    obs=[]
    for i,s in forced.items():
        x,y=max(s,a),min(s+p[i],b)
        if x<y: obs.append((i,x,y))
    items=[i for i in range(n) if i not in forced]
    # Only items fully inside [a,b] are forced to use this window; others ignored.
    # Caller must pass the right item set; here assume all non-forced are inside.
    total=0; nodes=0
    for ass in itertools.product(range(m),repeat=len(obs)):
        good=True; per=[[] for _ in range(m)]
        for (i,x,y),k in zip(obs,ass):
            if k not in el[i]: good=False;break
            if any(x<y2 and x2<y for x2,y2 in per[k]): good=False;break
            per[k].append((x,y))
        if not good: continue
        bins=[]
        for k in range(m): bins+=free_intervals(per[k],a,b)
        if sum(p[i] for i in items)>sum(bins): continue
        ok,nd=binpack([p[i] for i in items],bins,nodecap); nodes+=nd
        if ok: return 'YES',nodes
        if ok is None: return 'UNKNOWN',nodes
    return 'NO',nodes
