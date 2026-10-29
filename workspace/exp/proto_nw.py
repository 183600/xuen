import sys, time, random
sys.path.insert(0,'/home/runner/work/xuen/xuen/workspace/exp')
import exp_da as E

def children(inst,S,A,c):
    n,p,pred=inst['n'],inst['p'],inst['pred']
    out=[]
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
            out.append((i,k,S|(1<<i),na,tuple(nc),st+p[i]))
    # dedup by state
    d={}
    for t in out: d[(t[2],t[3],t[4])]=t
    return list(d.values())

def decide(inst,H,order='cp',cap=2_000_000):
    n=inst['n']; full=(1<<n)-1
    ref={}; wit={}
    nodes=[0]
    class Cap(Exception): pass
    def rec(S,A,c,F):
        nodes[0]+=1
        if nodes[0]>cap: raise Cap
        C=max(A)
        if C>H: return None
        if S==full: return C
        L0=E.lower_L0(inst,S,A,c)
        if L0>H: 
            return None
        key=(S,A,c)
        if ref.get(key,-1)>=H: return None
        w=wit.get(key)
        if w is not None and w<=H: return w
        ch=children(inst,S,A,c)
        def sco(t):
            i,k,S2,A2,c2,C2=t
            if order=='cp':
                _,q=E.heads_tails(inst,S2,c2)
                return (C2,-q[i] if i<n else 0,i,k)
            if order=='C':
                return (C2,i,k)
            return (C2,i,k)
        ch.sort(key=sco)
        best=None
        for (i,k,S2,A2,c2,C2) in ch:
            if C2>H: continue
            F2=max(F,E.lower_L0(inst,S2,A2,c2))
            if F2>H: continue
            r=rec(S2,A2,c2,F2)
            if r is not None:
                best=r; break
        if best is None:
            ref[key]=H
            return None
        wit[key]=best
        return best
    t0=time.time()
    try:
        r=rec(0,(0,0),(-1,)*n,E.lower_L0(inst,0,(0,0),(-1,)*n))
        return r,nodes[0],time.time()-t0,True
    except Cap:
        return None,nodes[0],time.time()-t0,False

def ag_prove(inst,opt):
    # AG with U initialized to opt, stop when proven; count steps
    r=E.run(inst,'AG',budget=3000)
    return r

if __name__=='__main__':
    rng=random.Random(3)
    insts=[]
    for k in range(60):
        n=rng.choice([9,10,11])
        inst=E.gen_instance(n, rng.choice([0.15,0.2,0.25,0.3,0.35,0.45]), rng.choice([5,8,10,15]), rng)
        r=E.run(inst,'AG',budget=400)
        insts.append((r['steps'],inst,r))
    insts.sort(key=lambda x:-x[0])
    sel=[t for t in insts if t[0]>=8][:12]
    for st,inst,r in sel:
        opt=r['U']
        o,nodes,ok=E.exact_opt(inst,cap=1_500_000)
        print('n',inst['n'],'e',sum(len(x) for x in inst['pred']),'AGsteps',st,'AGU',r['U'],'OPT',o,ok, flush=True)
        for order in ['C','cp']:
            res,nd,tt,comp=decide(inst,o-1,order=order)
            print('   NW',order,'res',res,'nodes',nd,'comp',comp,'%.3fs'%tt, flush=True)
