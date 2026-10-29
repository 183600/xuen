import sys,pickle,time
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
import numpy as np, scipy.sparse as sp
from scipy.optimize import linprog
from qnc import QNC
from cert import DENS, verify, _row_meta

def farkas_obj(lp, forbid, dens=DENS):
    A,hi=lp.matrix(); n_eq=lp.n_eq; N=lp.base.N; n=lp.n
    r=A.shape[0]-n_eq
    present=np.array([cc for cc,key in enumerate(lp.cols) if (key[0],key[-1]) not in forbid],dtype=np.int64)
    if len(present)==0: return None,None
    B=sp.hstack([A[:n_eq].T,A[n_eq:].T]).tocsr()[present]
    b=np.concatenate([np.ones(n_eq), hi[n_eq:]])
    res=linprog(np.zeros(n_eq+r), A_ub=-B, b_ub=np.zeros(len(present)),
                A_eq=[b], b_eq=[-1.0],
                bounds=[(None,None)]*n_eq+[(0,None)]*r, method='highs')
    if res.status!=0: return None,res
    for D in dens:
        y=np.rint(res.x*D).astype(np.int64)
        s=np.asarray(A.T.dot(y)).ravel(); bt=int(b.dot(y))
        if s[present].min()>=0 and bt<0:
            meta=_row_meta(lp.base)+[('dom',i,j,t) for (i,j,t) in lp.cuts]
            yb=y[n:]
            cert=dict(kind='packing',scale=D,
                beta=[(m[1],m[2],int(yb[k])) for k,m in enumerate(meta) if m[0]=='cap' and yb[k]],
                dom=[(m[1],m[2],m[3],int(yb[k])) for k,m in enumerate(meta) if m[0]=='dom' and yb[k]],
                exp=[(m[1],m[2],int(yb[k])) for k,m in enumerate(meta) if m[0]=='exp' and yb[k]],
                alpha=[int(v) for v in y[:n]], obj=bt, farkas=res.fun,
                cuts=[meta[k] for k in range(len(meta)) if yb[k]])
            return cert,s
    return None,res

def load(f):
 d=pickle.load(open(f,'rb')); return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]

def run(inst,h,max_outer=20,max_inner=50,verbose=True):
    q=QNC(inst,h); q.budget=100000
    force={}  # job -> set allowed
    root_bounds=[(0,1)]*q.lp.base.N
    stats=dict(lp=0,outer=0,inner=0,clauses=[],forces=[],why=None)
    t0=time.time()
    def apply(bounds,force):
        b=list(bounds)
        for c,key in enumerate(q.lp.cols):
            if key[0] in force and key[-1] not in force[key[0]]:
                b[c]=(0,0)
        return b
    for outer in range(max_outer):
        bounds=apply(root_bounds,force)
        res,z=q._solve(bounds,60,100); stats['lp']+=1; stats['outer']+=1
        if res.status==2:
            stats['why']='root-no'; return stats
        if res.status!=0 or z is None: stats['why']='other'; return stats
        frac=[c for c in range(q.lp.base.N) if 1e-7<z[c]<1-1e-7]
        if not frac:
            stats['why']='yes'; return stats
        deleted=set()
        for inner in range(max_inner):
            supp=[c for c in range(q.lp.base.N) if z[c]>1e-7 and bounds[c]!=(0,0)]
            if not supp: stats['why']='nosupp'; return stats
            for c in supp: deleted.add(c)
            b2=list(bounds)
            for c in deleted: b2[c]=(0,0)
            res2,z2=q._solve(b2,60,100); stats['lp']+=1; stats['inner']+=1
            if res2.status==2:
                F={q.lp.cols[c] for c in deleted}
                cert,s=farkas_obj(q.lp,F)
                if cert is None:
                    stats['why']='certfail'; stats['deleted']=len(deleted); return stats
                E=frozenset(key for cc,key in enumerate(q.lp.cols) if key in F and s[cc]<0)
                ok=verify(inst,h,cert,forbid=E,elig_aware=q.elig)
                jobs={i for i,t in E}
                stats['clauses'].append(dict(outer=outer,inner=inner,deleted=len(deleted),E=len(E),jobs=len(jobs),verify=ok))
                if verbose: print(' outer',outer,'inner',inner,'deleted',len(deleted),'E',len(E),'jobs',jobs,'ok',ok,'E',sorted(E)[:12])
                if len(jobs)==1:
                    i=next(iter(jobs)); S=frozenset(t for j,t in E)
                    new=S & force.get(i,set(q._dom[i]))
                    force[i]=new; stats['forces'].append((i,sorted(new)))
                    if not new: stats['why']='force-empty'; return stats
                    break  # restart outer
                else:
                    stats['why']='multi-clause'; return stats
            if res2.status!=0 or z2 is None: stats['why']='other2'; return stats
            z=z2
        else:
            stats['why']='inner-cap'; return stats
    stats['why']='outer-cap'; stats['force']={i:sorted(s) for i,s in force.items()}
    return stats

if __name__=='__main__':
    cases=[('holdout50',5),('holdout50',47)]
    for name,idx in cases:
        inst,opt=load({'holdout50':'exp/v20/holdout_cases50.pkl'}[name])[idx]; h=opt-1
        print('\n===',name,idx,'n',inst['n'],'h',h)
        st=run(inst,h)
        print({k:v for k,v in st.items()})
