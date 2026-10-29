import sys, time, pickle
sys.path.insert(0,'/home/runner/work/xuen/xuen/workspace/exp')
import exp_da as E

INF=float('inf')
class Node:
    __slots__=('S','A','c','F','ch','pn','dn','exp','wit')
    def __init__(self,S,A,c,F):
        self.S=S; self.A=A; self.c=c; self.F=F
        self.ch=None; self.pn=1; self.dn=1; self.exp=False; self.wit=None

def pns(inst,H,use_avail=True,cap=2_000_000):
    n=inst['n']; full=(1<<n)-1
    proved={}   # (S,A,c)->H proved
    dom={}      # S -> list (A,c,H)
    nodes=[0]
    class Cap(Exception): pass

    def is_proved(S,A,c):
        if proved.get((S,A,c),-1)>=H: return True
        for (A2,c2,h) in dom.get(S,()):
            if h>=H and all(x<=y for x,y in zip(A2,A)) and all(c2[i]<=c[i] for i in range(n) if (S>>i)&1):
                return True
        return False
    def add_proved(S,A,c):
        proved[(S,A,c)]=H
        lst=dom.setdefault(S,[])
        for (A2,c2,h) in lst:
            if h>=H and all(x<=y for x,y in zip(A2,A)) and all(c2[i]<=c[i] for i in range(n) if (S>>i)&1):
                return
        lst[:]=[(A2,c2,h) for (A2,c2,h) in lst if not (h<=H and all(x<=y for x,y in zip(A,A2)) and all(c[i]<=c2[i] for i in range(n) if (S>>i)&1))]
        lst.append((A,c,H))

    def children(nd):
        S,A,c,F=nd.S,nd.A,nd.c,nd.F
        out=[]
        p=inst['p']; pred=inst['pred']
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

    root=Node(0,(0,0),(-1,)*n,E.lower_L0(inst,0,(0,0),(-1,)*n))
    if root.F>H: return None,0,True
    try:
        while True:
            # descend by min pn; expand first unexpanded
            path=[root]; nd=root
            while nd.exp and nd.pn>0 and nd.dn>0:
                nxt=None
                for ch in nd.ch:
                    if ch.pn==0 or ch.dn==0: 
                        if ch.dn==0: nxt=None; break
                        continue
                    if nxt is None or ch.pn<nxt.pn: nxt=ch
                if nxt is None: break
                path.append(nxt); nd=nxt
            if nd.exp and (nd.pn==0 or nd.dn==0): 
                # root solved
                if root.pn==0: return None,nodes[0],True
                if root.dn==0: return root.wit,nodes[0],True
            if nd.exp:
                # shouldn't happen
                break
            nodes[0]+=1
            if nodes[0]>cap: raise Cap
            nd.exp=True
            ch=[]
            for (i,k,S2,A2,c2,C2) in children(nd):
                if C2>H: continue
                if S2==full:
                    ch.append(_leaf(A2,C2)); continue
                l2=E.lower_L0(inst,S2,A2,c2)
                if l2>H: continue
                F2=max(nd.F,l2)
                if F2>H: continue
                if is_proved(S2,A2,c2):
                    ch.append(_leaf(None,None,proved=True)); continue
                ch.append(Node(S2,A2,c2,F2))
            nd.ch=ch
            _upd(nd)
            # update ancestors bottom-up
            for x in reversed(path[:-1]):
                _upd(x)
            if root.pn==0: return None,nodes[0],True
            if root.dn==0: return root.wit,nodes[0],True
    except Cap:
        return None,nodes[0],False

class _leaf:
    __slots__=('pn','dn','exp','wit','ch')
    def __init__(self,A,C=None,proved=False):
        self.ch=None; self.exp=True
        if proved: self.pn=0; self.dn=INF; self.wit=None
        else: self.pn=INF; self.dn=0; self.wit=C

def _upd(nd):
    if not nd.ch:
        nd.pn=INF; nd.dn=0 if False else INF
        # no children at all -> cannot proceed? treat as proved (all actions pruned)
        nd.pn=0; nd.dn=INF
        return
    pn=0; dn=INF; w=None
    for ch in nd.ch:
        pn+=ch.pn
        if ch.dn<dn: dn=ch.dn; w=ch.wit
        if ch.dn==0 and w is None: w=ch.wit
    nd.pn=pn; nd.dn=dn; nd.wit=w

if __name__=='__main__':
    hard=pickle.load(open('exp/hard17.pkl','rb'))
    tot=0
    for st,inst,r in hard:
        opt=r['U']; t0=time.time()
        w,nd,ok=pns(inst,opt-1)
        tot+=nd
        print(f"AG={st:4d} OPT={opt} L0={r['L0']} | PNS refute={nd:5d} ok={ok and w is None} {time.time()-t0:.2f}s",flush=True)
    print('TOTAL PNS',tot)
