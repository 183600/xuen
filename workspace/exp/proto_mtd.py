import sys, time, pickle
sys.path.insert(0,'/home/runner/work/xuen/xuen/workspace/exp')
import exp_da as E

class FailTable:
    def __init__(self):
        self.d={}
    def dominated(self,S,A,c,H):
        for (A2,c2,h) in self.d.get(S,()):
            if h>=H and all(x<=y for x,y in zip(A2,A)) and all(c2[i]<=c[i] for i in range(len(c)) if (S>>i)&1):
                return True
        return False
    def add(self,S,A,c,H):
        lst=self.d.setdefault(S,[])
        for (A2,c2,h) in lst:
            if h>=H and all(x<=y for x,y in zip(A2,A)) and all(c2[i]<=c[i] for i in range(len(c)) if (S>>i)&1):
                return
        lst[:]=[(A2,c2,h) for (A2,c2,h) in lst if not (h<=H and all(x<=y for x,y in zip(A,A2)) and all(c[i]<=c2[i] for i in range(len(c)) if (S>>i)&1))]
        lst.append((A,c,H))

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

def decide(inst,H,fail,use_avail=True,cap=3_000_000):
    n=inst['n']; full=(1<<n)-1
    ref={}; wit={}
    nodes=[0]
    class Cap(Exception): pass
    L0root=E.lower_L0(inst,0,(0,0),(-1,)*n)
    if L0root>H: return None,0,True
    def rec(S,A,c,F,est,q,win):
        nodes[0]+=1
        if nodes[0]>cap: raise Cap
        C=max(A)
        if C>H: return None
        if S==full: return C
        if fail.dominated(S,A,c,H): return None
        key=(S,A,c)
        if ref.get(key,-1)>=H: return None
        w=wit.get(key)
        if w is not None and w<=H: return w
        if use_avail and win and E.infeasible_at(inst,S,A,c,H,est,q,win):
            ref[key]=H; fail.add(S,A,c,H); return None
        ch=ch_list(inst,S,A,c)
        ch.sort(key=lambda t:(-(inst['p'][t[0]]+q[t[0]]), t[5], t[0], t[1]))
        for (i,k,S2,A2,c2,C2) in ch:
            if C2>H: continue
            l2=E.lower_L0(inst,S2,A2,c2)
            if l2>H: continue
            F2=max(F,l2)
            if F2>H: continue
            est2,q2=E.heads_tails(inst,S2,c2)
            win2=E.make_windows(inst,S2,A2,c2,H+1)[0] if use_avail else None
            r=rec(S2,A2,c2,F2,est2,q2,win2)
            if r is not None: return r
        ref[key]=H; fail.add(S,A,c,H)
        return None
    est,q=E.heads_tails(inst,0,(-1,)*n)
    win=E.make_windows(inst,0,(0,0),(-1,)*n,H+1)[0] if use_avail else None
    try:
        r=rec(0,(0,0),(-1,)*n,L0root,est,q,win)
        return r,nodes[0],True
    except Cap:
        return None,nodes[0],False

def mtd(inst,use_avail=True,guide='classic'):
    n=inst['n']
    U=min(E.greedy(inst,0,(0,0),(-1,)*n,r) for r in ('CP','LPT','MWKR'))
    L0=E.lower_L0(inst,0,(0,0),(-1,)*n)
    fail=FailTable(); nodes=0; qs=[]
    while U>L0:
        H=U-1
        w,nd,ok=decide(inst,H,fail,use_avail)
        nodes+=nd; qs.append((H,w,nd))
        if not ok: return None,nodes,qs
        if w is None: return U,nodes,qs
        if w>=U: return U,nodes,qs
        U=w
    return U,nodes,qs

if __name__=='__main__':
    hard=pickle.load(open('exp/hard17.pkl','rb'))
    tot_ag=tot_mtd=0
    for st,inst,r in hard:
        opt=r['U']; t0=time.time()
        u,nd,qs=mtd(inst)
        tot_ag+=st; tot_mtd+=nd
        print(f"AG={st:4d} OPT={opt:3d} L0={r['L0']:3d} | MTD={nd:5d} ok={u==opt} q={[(h,w if w is None else w) for h,w,_ in qs]} {time.time()-t0:.2f}s",flush=True)
    print('TOTAL AG',tot_ag,'MTD',tot_mtd)
