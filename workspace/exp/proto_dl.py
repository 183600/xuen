import sys, time, random
sys.path.insert(0,'/home/runner/work/xuen/xuen/workspace/exp')
import exp_da as E

def ch_list(inst,S,A,c):
    n,p,pred=inst['n'],inst['p'],inst['pred']
    d={}
    for i in range(n):
        if (S>>i)&1: continue
        ok=True; base=0
        for j in pred[i]:
            if not ((S>>j)&1): ok=False;break
            if c[j]>base: base=c[j]
        if not ok: continue
        for k in range(len(A)):
            st=max(A[k],base)
            na=list(A); na[k]=st+p[i]; na=tuple(sorted(na))
            nc=list(c); nc[i]=st+p[i]
            key=(S|(1<<i),na,tuple(nc))
            if key not in d: d[key]=(i,k,key[0],na,key[2],st+p[i])
    return list(d.values())

def find_dfs(inst,H,use_avail=True,cap=3_000_000):
    n=inst['n']; full=(1<<n)-1
    ref={}
    nodes=[0]; packs=[0]
    class Cap(Exception): pass
    L0root=E.lower_L0(inst,0,(0,0),(-1,)*n)
    if L0root>H: return None,0,0,True
    def rec(S,A,c,F,est,q,win):
        nodes[0]+=1
        if nodes[0]>cap: raise Cap
        C=max(A)
        if C>H: return None
        if S==full: return C
        key=(S,A,c)
        if ref.get(key,-1)>=H: return None
        if use_avail and win:
            packs[0]+=0
            if E.infeasible_at(inst,S,A,c,H,est,q,win):
                ref[key]=H; return None
        ch=ch_list(inst,S,A,c)
        # order: LST = p+q desc, then earliest completion
        def sco(t):
            i,k,S2,A2,c2,C2=t
            return (-(inst['p'][i]+q[i]), C2, i, k)
        ch.sort(key=sco)
        for (i,k,S2,A2,c2,C2) in ch:
            if C2>H: continue
            l2=E.lower_L0(inst,S2,A2,c2)
            if l2>H: continue
            F2=max(F,l2)
            if F2>H: continue
            if use_avail:
                est2,q2=E.heads_tails(inst,S2,c2)
                win2=E.make_windows(inst,S2,A2,c2,H+1)[0]
            else:
                est2,q2,win2=None,None,None
            r=rec(S2,A2,c2,F2,est2,q2,win2)
            if r is not None: return r
        ref[key]=H
        return None
    est,q=E.heads_tails(inst,0,(-1,)*n)
    win=E.make_windows(inst,0,(0,0),(-1,)*n,H+1)[0] if use_avail else None
    try:
        r=rec(0,(0,0),(-1,)*n,L0root,est,q,win)
        return r,nodes[0],packs[0],True
    except Cap:
        return None,nodes[0],0,False

def find_beam(inst,H,B=8,use_avail=False):
    """layer beam over partial schedules; returns witness C or None, nodes"""
    n=inst['n']; full=(1<<n)-1
    layer={((0,(0,0),(-1,)*n)):None}
    nodes=0
    for depth in range(n):
        nxt={}
        for (S,A,c) in layer:
            nodes+=1
            for (i,k,S2,A2,c2,C2) in ch_list(inst,S,A,c):
                if C2>H: continue
                if E.lower_L0(inst,S2,A2,c2)>H: continue
                if S2==full: return C2,nodes
                key=(S2,A2,c2)
                if key not in nxt: nxt[key]=None
        if not nxt: return None,nodes
        if len(nxt)>B:
            scored=[]
            for (S,A,c) in nxt:
                L=E.lower_L0(inst,S,A,c)
                scored.append((max(A)-L, max(A), (S,A,c)))
            scored.sort()
            nxt={t[2]:None for t in scored[:B]}
        layer=nxt
    return None,nodes

def ladder(inst,use_avail=True,B=0,verbose=False):
    n=inst['n']
    U=E.greedy(inst,0,(0,0),(-1,)*n,'CP')
    for r in ('LPT','MWKR'):
        U=min(U,E.greedy(inst,0,(0,0),(-1,)*n,r))
    L0=E.lower_L0(inst,0,(0,0),(-1,)*n)
    nodes=0; queries=[]
    H=L0
    while H<U:
        w=None
        if B>0:
            w,nb=find_beam(inst,H,B)
            nodes+=nb
            if w is not None: queries.append((H,'beam',nb)); return w,nodes,queries
        w,nd,_,ok=find_dfs(inst,H,use_avail)
        nodes+=nd
        queries.append((H,'dfs' if w is None else 'win',nd))
        if w is not None: return w,nodes,queries
        H+=1
    return U,nodes,queries

if __name__=='__main__':
    rng=random.Random(11)
    rows=[]
    for k in range(40):
        n=rng.choice([8,9,10])
        inst=E.gen_instance(n, rng.choice([0.15,0.2,0.25,0.3,0.35]), rng.choice([8,10,12,15]), rng)
        r=E.run(inst,'AG',budget=800)
        if r['open']!=0: continue
        rows.append((r['steps'],inst,r))
    rows.sort(key=lambda x:-x[0])
    sel=rows[:14]
    t0=time.time()
    for st,inst,r in sel:
        opt=r['U']; L0=r['L0']
        w,nd,q=ladder(inst,use_avail=True,B=0)
        w2,nd2,q2=ladder(inst,use_avail=True,B=6)
        print(f"n={inst['n']} e={sum(len(x) for x in inst['pred'])} AG={st} OPT={opt} L0={L0} gap={opt-L0} | DLdfs={nd} ok={w==opt} | DLbeam={nd2} ok={w2==opt} q={q2}",flush=True)
    print('time',round(time.time()-t0,1))
