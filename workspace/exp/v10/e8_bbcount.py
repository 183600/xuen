import sys, json, time
sys.path.insert(0,'exp/v10')
R=json.load(open('exp/v08/results.json'))

def pack_nodes(p,m,H):
    sizes=sorted(p,reverse=True); bins=[0]*m; cnt=[0]
    def dfs(i):
        cnt[0]+=1
        if i==len(sizes): return True
        s=sizes[i]; seen=set()
        for k in range(m):
            if bins[k]+s<=H and bins[k] not in seen:
                seen.add(bins[k]); bins[k]+=s
                if dfs(i+1): return True
                bins[k]-=s
        return False
    ok=dfs(0); return ok,cnt[0]

for fam in ('part2','part3'):
    ns=[]; ts=[]
    for r in R[fam]:
        t=time.time(); ok,c=pack_nodes(r['p'],r['m'],r['OPT']-1); ts.append(time.time()-t)
        ns.append(c); assert not ok
    ns.sort()
    print(fam,'B&B nodes min/med/max',ns[0],ns[len(ns)//2],ns[-1],'time med',round(sorted(ts)[len(ts)//2],4))
