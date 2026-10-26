import sys,time
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from pysat.card import CardEnc, EncType
from pysat.solvers import Cadical195
from po import heads_tails

def encode(inst,h,enc=EncType.seqcounter):
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q=heads_tails(inst,0,[0]*n)
    var={}; clauses=[]; top=0
    def nv(): 
        nonlocal top; top+=1; return top
    for i in range(n):
        lo=est[i]; hi=h-q[i]-p[i]
        for t in range(lo,hi+1):
            for k in inst['elig'][i]:
                top+=1; var[(i,k,t)]=top
    # exactly one
    for i in range(n):
        lits=[v for (ii,k,t),v in var.items() if ii==i]
        if not lits:
            return None,None,None,None
        clauses.append(lits[:])
        cnf=CardEnc.atmost(lits, bound=1, top_id=top, encoding=enc)
        clauses.extend(cnf.clauses); top=max(top,cnf.nv)
    # capacity
    for k in range(m):
        for tau in range(h):
            lits=[]
            for (i,kk,t),v in var.items():
                if kk==k and t<=tau<t+p[i]: lits.append(v)
            if len(lits)<=1: continue
            cnf=CardEnc.atmost(lits, bound=1, top_id=top, encoding=enc)
            clauses.extend(cnf.clauses); top=max(top,cnf.nv)
    # precedence
    for i in range(n):
        for j in inst['succ'][i]:
            for (ii,k,t),v in var.items():
                if ii!=i: continue
                for (jj,kk,tt),w in var.items():
                    if jj==j and tt < t+p[i]:
                        clauses.append([-v,-w])
    return var,clauses,top,(est,q)

def solve(inst,h,proof=False):
    t0=time.time()
    var,clauses,top,dom=encode(inst,h)
    te=time.time()-t0
    if var is None: return dict(verdict=False,reason='domain',enc_t=te,solve_t=0,nv=0,nc=0)
    with Cadical195(bootstrap_with=clauses, with_proof=proof) as s:
        sat=s.solve()
        dt=time.time()-t0-te
        pr=s.get_proof() if (proof and not sat) else None
    if sat:
        model=s.get_model() if False else None
    return dict(verdict=bool(sat),enc_t=te,solve_t=dt,nv=top,nc=len(clauses),proof=pr)

if __name__=='__main__':
    from chip import base_corpus
    row=base_corpus()[0]
    name,idx,inst,known=row
    for h in [known-1,known]:
        r=solve(inst,h)
        print(name,idx,'h',h,r['verdict'],'nv',r['nv'],'nc',r['nc'],'enc',round(r['enc_t'],3),'sol',round(r['solve_t'],3))
