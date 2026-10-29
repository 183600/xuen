import sys,random,json,time,math,statistics
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v23']
import po,pace_q,pi_fast,cbc
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def gen(rng,n,m):
    p=[rng.randint(2,9) for _ in range(n)]; pred=[[] for _ in range(n)]
    ep=rng.choice([0.18,0.22,0.28,0.35])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j]: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
def opt_of(inst):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3)
    for h in range(lo,lo+18):
        (ok,_),_=pace_q.decide(inst,h,odom=False,hpack_on=False,omd=True,**CFG)
        if ok: return h
    return None
def feats(inst,h):
    n=inst['n']; m=inst['m']; p=inst['p']; est,q=po.heads_tails(inst,0,[0]*n)
    sl=[h-(est[i]+p[i]+q[i]) for i in range(n)]
    ms=min(sl); sp=sum(p); mp=max(p)
    tasks,adj=cbc.incompat_graph(inst,inst['full'],est,q,h)
    C=cbc.clique_at_least(tasks,adj,m+1)
    # exact max clique size up to m+1 via greedy (cheap upper proxy)
    deg=[adj[i].bit_count() for i in range(len(tasks))]
    dens=[p[i]/max(1,h-q[i]-est[i]) for i in range(n)]
    return [n, m, h, ms, sp/(m*h), mp/h, sum(1 for x in sl if x<=1)/n,
            sum(1 for x in sl if x<=2)/n, statistics.pstdev(p)/max(1,statistics.mean(p)),
            max(deg)/max(1,n-1), sum(deg)/max(1,len(tasks)*(len(tasks)-1)),
            statistics.pstdev(dens), max(dens), len(C) if C else 0]
def label(inst,h):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    b,_=pi_fast.beta(inst,h,inst['full'],est,q)
    return 1 if b>inst['m'] else 0
if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--N',type=int,default=300); ap.add_argument('--seed',type=int,default=7001)
    ap.add_argument('--out',default='exp/v23/gate_train.json'); a=ap.parse_args()
    rng=random.Random(a.seed); rows=[]; tried=0; t0=time.time()
    while len(rows)<a.N and tried<4000:
        tried+=1
        n=rng.randint(12,16); inst=gen(rng,n,3)
        opt=opt_of(inst)
        if opt is None: continue
        h=opt-1
        est,q=po.heads_tails(inst,0,[0]*n)
        ms=min(h-(est[i]+inst['p'][i]+q[i]) for i in range(n))
        if ms>4: continue
        y=label(inst,h); x=feats(inst,h)
        rows.append(dict(x=x,y=y,n=n,ms=ms))
    pos=sum(r['y'] for r in rows)
    print('rows',len(rows),'pos',pos,'neg',len(rows)-pos,'tried',tried,'sec',round(time.time()-t0,1))
    json.dump(rows,open(a.out,'w'),indent=1)
