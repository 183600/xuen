import sys,time
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from po import heads_tails
from rdf import check_schedule
from pysat.solvers import Glucose3, Cadical153
from pysat.card import CardEnc, EncType

def sat_schedule(inst,h,forbid=None,solver='glucose',limit=None):
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q=heads_tails(inst,0,[0]*n)
    forbid=set(forbid or ())
    var={}; top=0; clauses=[]
    by_task=[[] for _ in range(n)]
    covers=[[[] for _ in range(h)] for _ in range(m)]
    for i in range(n):
        for k in inst['elig'][i]:
            for t in range(est[i], h-q[i]-p[i]+1):
                if (i,t) in forbid: continue
                top+=1; var[(i,k,t)]=top; by_task[i].append(top)
                for u in range(t,min(t+p[i],h)):
                    covers[k][u].append(top)
    for i in range(n):
        if not by_task[i]: return dict(verdict=False,why='empty',vars=top)
        # exactly one
        lits=by_task[i]
        clauses.append(lits[:])
        for a in range(len(lits)):
            for b in range(a+1,len(lits)):
                clauses.append([-lits[a],-lits[b]])
    for k in range(m):
        for t in range(h):
            lits=covers[k][t]
            if len(lits)>1:
                # pairwise for now
                for a in range(len(lits)):
                    for b in range(a+1,len(lits)):
                        clauses.append([-lits[a],-lits[b]])
    for i in range(n):
        for j in inst['succ'][i]:
            for (ii,ki,ti),vi in var.items():
                if ii!=i: continue
                for (jj,kj,tj),vj in var.items():
                    if jj!=j: continue
                    if ti+p[i]>tj: clauses.append([-vi,-vj])
    s=(Cadical153 if solver=='cadical' else Glucose3)(bootstrap_with=clauses)
    if limit is not None: s.solve_limited(expect_interrupt=True)
    ok=s.solve()
    if not ok:
        s.delete(); return dict(verdict=False,why='unsat',vars=top,clauses=len(clauses))
    model=s.get_model(); s.delete()
    true=set(x for x in model if x>0)
    starts=[None]*n; mach=[None]*n
    for (i,k,t),v in var.items():
        if v in true: starts[i]=t; mach[i]=k
    cm=max(starts[i]+p[i] for i in range(n)) if all(x is not None for x in starts) else None
    good=all(x is not None for x in starts) and check_schedule(inst,h,starts,mach)
    return dict(verdict=bool(good),starts=starts,machines=mach,cmax=cm,vars=top,clauses=len(clauses))

if __name__=='__main__':
    rows=weak_rows(4)
    for j,(c,name,idx,inst,known,initial) in enumerate(rows[:20]):
        for hh in (known-1,known):
            t=time.time(); r=sat_schedule(inst,hh)
            print(j,c,name,idx,'h',hh,'known',known,'->',r['verdict'],r.get('cmax'),r.get('vars'),r.get('clauses'),'t',round(time.time()-t,3))
