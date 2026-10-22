import sys, random, time, json
sys.path.insert(0,'.')
import pcb, exp_da as E

def dfs_c(inst, budget=200000):
    n,m,full=inst['n'],inst['m'],inst['full']
    qs=inst['q_static']
    U=[pcb.upper_bound(inst)]
    memo=set(); cnt=[0]
    def rec(S,A,c):
        cnt[0]+=1
        if cnt[0]>budget: raise RuntimeError
        key=(S,A,c)
        if key in memo: return
        memo.add(key)
        if S==full:
            if max(A)<U[0]: U[0]=max(A)
            return
        if E.point_avail(inst,S,A,c,U[0])>=U[0]: return
        ch=E.gen_children(inst,S,A,c)
        def sc(z):
            i=(z[0]^S).bit_length()-1
            return (-qs[i], max(z[1]), i)
        ch.sort(key=sc)
        for (S2,A2,c2) in ch:
            if max(A2)>=U[0]: continue
            rec(S2,A2,c2)
    try:
        rec(0,(0,)*m,(-1,)*n); ok=True
    except RuntimeError:
        ok=False
    return U[0],cnt[0],ok,len(memo)

def iface_dfs(inst,budget=200000):
    s=pcb.Solver(inst,front='off',memo=True)
    r=s.search(budget)
    return r['U'],r['nodes'],r['exhausted']

if __name__=='__main__':
    rng=random.Random(7)
    pool=[]
    tries=0
    while len(pool)<10 and tries<600:
        tries+=1
        n=rng.choice([9,10])
        inst=pcb.gen_instance(n,rng.choice([0.2,0.3,0.4]),rng.choice([6,8,10]),rng,2)
        s=pcb.Solver(inst); s.dom=True
        rb=s.search_bf(200000)
        if rb['nodes']>=40:
            opt,nd,ok=E.exact_opt(inst,cap=800000)
            if ok:
                pool.append((inst,opt,rb['nodes'],nd))
    print('pool',len(pool))
    rows=[]
    for k,(inst,opt,bfn,exnd) in enumerate(pool):
        t=time.time(); ui,ni,oki=iface_dfs(inst); ti=time.time()-t
        t=time.time(); uc,nc,okc,ms=dfs_c(inst); tc=time.time()-t
        uaco,tau=pcb.aco(inst,iters=10,ants=8,seed=k)
        ug=pcb.upper_bound(inst)
        row=dict(opt=opt,bf=bfn,exnd=exnd,iface=ni,iface_t=round(ti,3),c= nc,c_t=round(tc,3),
                 memo=ms,u_g=ug,u_aco=uaco,ok=(ui==opt and uc==opt))
        rows.append(row); print(k,row)
    print('sum iface',sum(r['iface'] for r in rows),'sum c',sum(r['c'] for r in rows),'sum bf',sum(r['bf'] for r in rows))
    print('aco better',sum(1 for r in rows if r['u_aco']<r['u_g']),'of',len(rows))
    json.dump(rows,open('bench1.json','w'),indent=1)
