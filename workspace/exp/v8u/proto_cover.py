import sys, time, random
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from po import heads_tails
from cert import integer_certificate, verify
from rdf import check_schedule
from pact import _assign_machines
from pysat.solvers import Glucose3
from pysat.card import CardEnc, EncType

def domains(inst,h):
    est,q=heads_tails(inst,0,[0]*inst['n'])
    return [(est[i], h-q[i]-inst['p'][i]) for i in range(inst['n'])]

def cube_sat(inst,h,cover):
    est,q=heads_tails(inst,0,[0]*inst['n'])
    ds=[(est[i], h-q[i]-inst['p'][i]) for i in range(inst['n'])]
    if any(lo>hi for lo,hi in ds): return None  # trivially no assignment
    var={}; clauses=[]; top=0
    for i,(lo,hi) in enumerate(ds):
        lits=[]
        for t in range(lo,hi+1):
            top+=1; var[(i,t)]=top; lits.append(top)
        # exactly one
        clauses.append(lits[:])
        for a in range(len(lits)):
            for b in range(a+1,len(lits)):
                clauses.append([-lits[a],-lits[b]])
    for F in cover:
        cl=[var[(i,t)] for i,(lo,hi) in enumerate(ds) for t in range(lo,hi+1) if (i,t) not in F]
        if not cl:
            # box covers everything
            return None
        clauses.append(cl)
    s=Glucose3(bootstrap_with=clauses)
    ok=s.solve()
    if not ok:
        s.delete(); return False,None
    m=s.get_model(); s.delete()
    true=set(x for x in m if x>0)
    a={}
    for (i,t),v in var.items():
        if v in true: a[i]=t
    return True,a

def box_from_assign(inst,h,a):
    est,q=heads_tails(inst,0,[0]*inst['n'])
    F=set()
    for i in range(inst['n']):
        lo,hi=est[i],h-q[i]-inst['p'][i]
        for t in range(lo,hi+1):
            if t!=a[i]: F.add((i,t))
    return frozenset(F)

def expand_box(inst,h,F,cert):
    # greedily allow forbidden pairs while the same cert stays valid
    F=set(F)
    # order: allow earlier/later? random fixed seed
    cand=list(F)
    random.Random(0).shuffle(cand)
    for (i,t) in cand:
        F2=F-{(i,t)}
        if verify(inst,h,cert,forbid=F2):
            F=F2
    return frozenset(F)

def schedule_from_assign(inst,h,a):
    starts=[a[i] for i in range(inst['n'])]
    mach=_assign_machines(inst,starts)
    if mach is None: return None
    if check_schedule(inst,h,starts,mach):
        return starts,mach
    return None

def cover_synth(inst,known,U,budget=200,verbose=False):
    h=U-1
    cover=[]
    certs=[]
    t0=time.time(); sat_calls=0; lp_calls=0
    while len(cover)<budget:
        r=cube_sat(inst,h,cover); sat_calls+=1
        if r is None:
            return dict(ok=True,cert=None,reason='empty-domain',cover=0,t=time.time()-t0)
        sat,a=r
        if sat is False:
            return dict(ok=True,cert=cover,sat_calls=sat_calls,lp_calls=lp_calls,
                        cover=len(cover),t=time.time()-t0,why='unsat')
        # a is candidate schedule
        sch=schedule_from_assign(inst,h,a)
        if sch is not None:
            return dict(ok=False,schedule=sch,sat_calls=sat_calls,lp_calls=lp_calls,
                        cover=len(cover),t=time.time()-t0,why='feasible')
        F=box_from_assign(inst,h,a)
        cert=integer_certificate(inst,h,forbid=F); lp_calls+=1
        if cert is None:
            # singleton not LP-infeasible: try no expand
            return dict(ok=False,reason='no-cert-singleton',sat_calls=sat_calls,lp_calls=lp_calls,
                        cover=len(cover),t=time.time()-t0,a=a)
        F2=expand_box(inst,h,F,cert)
        if not verify(inst,h,cert,forbid=F2):
            return dict(ok=False,reason='bad-expand')
        cover.append(F2); certs.append(cert)
    return dict(ok=False,reason='budget',cover=len(cover),sat_calls=sat_calls,lp_calls=lp_calls,t=time.time()-t0)

if __name__=='__main__':
    rows=weak_rows(4)
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--n',type=int,default=10); ap.add_argument('--start',type=int,default=0)
    args=ap.parse_args()
    for j,(c,name,idx,inst,known,initial) in enumerate(rows[args.start:args.start+args.n]):
        L,U=initial[0],initial[1]
        t=time.time(); r=cover_synth(inst,known,U)
        print(j+args.start,c,name,idx,'OPT',known,'init',L,U,'->',{k:v for k,v in r.items() if k not in ('cert','schedule')},'wall',round(time.time()-t,3))
