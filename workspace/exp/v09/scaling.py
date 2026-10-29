import sys, random, math, time, json
sys.path.insert(0,'.'); sys.path.insert(0,'v09')
from lp import frac_pack

def bb_feasible(sizes,m,C):
    sizes=sorted(sizes,reverse=True); bins=[0]*m; nodes=[0]
    def dfs(i):
        nodes[0]+=1
        if i==len(sizes): return True
        s=sizes[i]; seen=set()
        for k in range(m):
            if bins[k]+s<=C and bins[k] not in seen:
                seen.add(bins[k]); bins[k]+=s
                if dfs(i+1): return True
                bins[k]-=s
        return False
    ok=dfs(0); return ok,nodes[0]

def lpt(sizes,m):
    b=[0]*m
    for s in sorted(sizes,reverse=True):
        k=min(range(m),key=lambda x:b[x]); b[k]+=s
    return max(b)

rng=random.Random(2026)
out=[]
for n in range(9,15):
    got=0; tries=0
    while got<6 and tries<4000:
        tries+=1
        p=[rng.randint(2,9) for _ in range(n)]
        if sum(p)%3: continue
        H=sum(p)//3
        if max(p)>H: continue
        if lpt(p,3)<=H: continue          # integer feasible at H -> skip
        ok,nodes=bb_feasible(p,3,H)
        if ok: continue
        t0=time.time(); tau,w,info=frac_pack(p,[H]*3); tlp=time.time()-t0
        out.append(dict(n=n,p=p,H=H,bb_nodes=nodes,lp_iters=info.get('iters'),
                        t_lp=round(tlp,4),tau=tau,lp_no=(tau>3+1e-9)))
        got+=1
        print('n',n,'H',H,'bb_nodes',nodes,'lp_iters',info.get('iters'),'t_lp',round(tlp,4),'tau',round(tau,3),flush=True)
json.dump(out,open('scaling.json','w'),indent=1)
for n in range(9,15):
    rs=[r for r in out if r['n']==n]
    print('N',n,'bb_nodes med',sorted(r['bb_nodes'] for r in rs)[len(rs)//2],
          'lp_iters med',sorted(r['lp_iters'] for r in rs)[len(rs)//2],
          't_lp med',sorted(r['t_lp'] for r in rs)[len(rs)//2])
