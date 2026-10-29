"""Chronological complete placement for the SOP residual check."""
def fits(occ,s,p):
    e=s+p
    for x,y in occ:
        if s<y and x<e: return False
    return True

def place_chrono(items,r,d,p,el,obs_by,m,a,b,nodecap=200000):
    order=list(items)
    full=(1<<len(order))-1
    nodes=[0]
    def dfs(mask,occ,frontier):
        nodes[0]+=1
        if nodes[0]>nodecap: raise TimeoutError
        if mask==full: return True
        for idx,i in enumerate(order):
            if (mask>>idx)&1: continue
            lo=max(r[i],a,frontier); hi=min(d[i]-p[i],b-p[i])
            if hi<lo: continue
            for k in el[i]:
                blocks=occ[k]+obs_by[k]
                cand={lo}
                for (x,y) in blocks:
                    if lo<=y<=hi: cand.add(y)
                    if lo<=x-p[i]<=hi: cand.add(x-p[i])
                for s in sorted(cand):
                    if fits(blocks,s,p[i]):
                        occ[k].append((s,s+p[i]))
                        if dfs(mask|(1<<idx),occ,s): return True
                        occ[k].pop()
        return False
    try:
        return dfs(0,[[] for _ in range(m)],a),nodes[0]
    except TimeoutError:
        return None,nodes[0]
