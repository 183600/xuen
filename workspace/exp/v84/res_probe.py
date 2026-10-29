import sys, pickle
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC

class CQ(QNC):
    def __init__(self,*a,**k): super().__init__(*a,**k); self.es=[]
    def _learn(self,F):
        c,E=super()._learn(F)
        if E: self.es.append(E)
        return c,E

def norm(E):
    d={}
    for i,t in E: d.setdefault(i,set()).add(t)
    return {i:frozenset(S) for i,S in d.items()}

def key(C): return tuple(sorted((i,tuple(sorted(S))) for i,S in C.items()))

def subsumes(A,B):
    return set(A)<=set(B) and all(A[i]<=B[i] for i in A)

def resolve(A,B,i):
    if i not in A or i not in B: return None
    out={}
    for C in (A,B):
        for j,S in C.items():
            if j==i: continue
            out[j]=out.get(j,frozenset())|S
    inter=A[i]&B[i]
    if inter: out[i]=inter
    return out

def closure(clauses, maxc=2000, maxsteps=50000):
    db=[]; keys=set(); steps=0
    def add(C):
        nonlocal db,keys
        if not C: return 'empty'
        k=key(C)
        if k in keys: return None
        if any(subsumes(D,C) for D in db): return None
        db=[D for D in db if not subsumes(C,D)]
        keys={key(D) for D in db}
        db.append(C); keys.add(k)
        return 'added'
    for E in clauses:
        r=add(norm(E))
        if r=='empty': return 'empty',0,[]
    changed=True
    while changed and steps<maxsteps:
        changed=False
        cur=list(db)
        for a in range(len(cur)):
            for b in range(a+1,len(cur)):
                A,B=cur[a],cur[b]
                for i in sorted(set(A)&set(B)):
                    if i not in A or i not in B: continue
                    R=resolve(A,B,i); steps+=1
                    r=add(R)
                    if r=='empty': return 'empty',steps,db
                    if r=='added': changed=True
                    if len(db)>=maxc or steps>=maxsteps: return 'cap',steps,db
    units=[D for D in db if len(D)==1]
    return 'open',steps,units

def show(C): return sorted((i,sorted(S)) for i,S in C.items())

def run(label,inst,h):
    q=CQ(inst,h); v,st=q.decide()
    print('\n',label,'verdict',v,'lp',st['lp_solves'],'nodes',st['nodes'],'leaves',len(q.es))
    for k,E in enumerate(q.es): print(' leaf',k,show(norm(E)))
    r,steps,info=closure(q.es)
    print(' closure:',r,'steps',steps,'db',len(info) if isinstance(info,list) else 0)
    if r!='empty' and r!='cap':
        print(' units',[show(D) for D in info])

def load(f):
    d=pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]

cases=[]
for name,f in [('holdout50','exp/v20/holdout_cases50.pkl'),('synth45','exp/v28/synth2_45.pkl')]:
    for idx,(inst,opt) in enumerate(load(f)): cases.append((name,idx,inst,opt-1))
for name,idx,inst,h in cases:
    q=CQ(inst,h); v,st=q.decide()
    if st['nodes']>1 or (name=='holdout50' and idx in (5,47)):
        run(f'{name}#{idx}',inst,h)
for (name,k,inst,opt,an,al) in pickle.load(open('exp/v71/perturb60.pkl','rb')):
    q=CQ(inst,opt-1); v,st=q.decide()
    if st['nodes']>1: run(f'pert-{name}-{k}',inst,opt-1)
