"""v8.6 LNS benchmark: CRISP vs CRISP+LNS on the 252 corpus."""
import sys, json, time, argparse
sys.path[:0]=['exp/v8f','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from lns import LNSRISP
from chip import base_corpus, pert_corpus, stress_corpus

def run(inst,known,name,idx,args):
    t0=time.time(); co=LNSRISP(inst,lns_budget=args.budget,lns_kmax=args.kmax,lns_tlim=args.tlim,lns_seed=args.seed,lns_stall=args.stall)
    r=co.optimize(); dt=time.time()-t0
    r.update(name=name,idx=idx,known=known,t=round(dt,4))
    b=getattr(co,'chip',None) or {}; l=getattr(co,'lns',None) or {}
    r['chip_lb']=b.get('lb'); r['chip_ub']=b.get('ub'); r['lns_ub']=r['opt'] if r['opt'] is not None else None
    r['lns_checks']=l.get('checks'); r['lns_t']=l.get('t'); r['lns_stall']=l.get('stall')
    r['ok']=bool(r['certified'] and r['opt']==known and r['audit'] and r['proof'] and r['cert_h']==known-1)
    return r

def agg(rows):
    return dict(n=len(rows),cert=sum(bool(r['certified']) for r in rows),ok=sum(bool(r['ok']) for r in rows),
                q=sum(r['queries'] for r in rows),lp=sum(r['lp'] for r in rows),yn=sum(r['yes_nodes'] for r in rows),
                mc=sum(r['mc_evals'] for r in rows),t=round(sum(r['t'] for r in rows),3),
                lns_checks=sum((r['lns_checks'] or 0) for r in rows),lns_t=round(sum((r['lns_t'] or 0) for r in rows),3),
                q0=sum(1 for r in rows if r['queries']==0),q1=sum(1 for r in rows if r['queries']==1),qgt=sum(1 for r in rows if r['queries']>1))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--budget',type=int,default=40); ap.add_argument('--kmax',type=int,default=14)
    ap.add_argument('--tlim',type=float,default=0.4); ap.add_argument('--seed',type=int,default=0); ap.add_argument('--stall',type=int,default=8); ap.add_argument('--only',default='')
    ap.add_argument('--out',default=''); args=ap.parse_args(); filt=set(x for x in args.only.split(',') if x)
    out={}
    for tag,corp in [('base',base_corpus()),('pert',pert_corpus()),('stress',stress_corpus())]:
        if filt and tag not in filt: continue
        t0=time.time(); rows=[]
        for ci,rec in enumerate(corp):
            if tag in ('base','pert'): name,idx,inst,known=rec
            else: idx,known,inst=rec; name='stress'
            r=run(inst,known,name,idx,args); rows.append(r)
            if ci%20==0: print(tag,ci,r['queries'],r['opt'],r['known'],round(r['t'],2),flush=True)
        out[tag]=rows
        print(tag,'time',round(time.time()-t0,2),json.dumps(agg(rows)),flush=True)
    if args.out: json.dump(out,open(args.out,'w'),indent=1)
    allrows=[r for tag in out for r in out[tag]]
    print('\n== total'); print(json.dumps(agg(allrows),indent=1))

if __name__=='__main__': main()
