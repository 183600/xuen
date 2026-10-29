"""Root-level comparison: v0.5 THRESH (forced-set packing) vs TENT threshold."""
import sys, time, json, pickle
sys.path.insert(0, '.')
import exp_da as E
from proto_tent import tent_items, tent_windows, tent_infeasible

def tent_thresh(inst, S, A, c, U, L0, use_grid=False):
    n=inst['n']
    est,q=E.heads_tails(inst,S,c)
    if use_grid:
        H=U-1
        wins=[(a,b) for a in range(0,H) for b in range(a+1,H+1)]
    else:
        wins=tent_windows(inst,S,A,c,U-1,est,q)
    best=None
    tests=0
    for (a,b) in wins:
        # monotone in H; binary search [L0, U-1]
        lo,hi=L0,U-1
        hh=None
        while lo<=hi:
            mid=(lo+hi)//2
            tests+=1
            if tent_infeasible(inst,S,A,c,mid,a,b,est,q):
                hh=mid; lo=mid+1
            else:
                hi=mid-1
        if hh is not None and (best is None or hh>best):
            best=hh
    return (best+1 if best is not None else L0), tests, len(wins)

def main():
    pool=pickle.load(open('pool30.pkl','rb'))
    rows=[]
    t0=time.time()
    for k,(inst,opt,nd) in enumerate(pool):
        S0,A0,c0=0,(0,0),(-1,)*inst['n']
        L0=E.lower_L0(inst,S0,A0,c0)
        U=E.guide(inst,S0,A0,c0)
        old, nf=E.thresh(inst,S0,A0,c0,U,L0,'full')
        new,nt,nw=tent_thresh(inst,S0,A0,c0,U,L0)
        row=dict(k=k,opt=opt,L0=L0,U=U,old=old,new=new,gap_old=old-L0,gap_new=new-L0,
                 nf=nf,nt=nt,nw=nw)
        rows.append(row)
        print(k,'opt',opt,'L0',L0,'U',U,'old',old,'new',new,'nf',nf,'nt',nt,flush=True)
    print('elapsed',round(time.time()-t0,2))
    print('old>L0',sum(1 for r in rows if r['old']>r['L0']),
          'new>L0',sum(1 for r in rows if r['new']>r['L0']),
          'new>old',sum(1 for r in rows if r['new']>r['old']),
          'old>new',sum(1 for r in rows if r['old']>r['new']),
          'new==opt',sum(1 for r in rows if r['new']==r['opt']),
          'old==opt',sum(1 for r in rows if r['old']==r['opt']))
    print('sum gains old',sum(r['old']-r['L0'] for r in rows),
          'new',sum(r['new']-r['L0'] for r in rows))
    json.dump(rows,open('proto_tent_root.json','w'),indent=1)

if __name__=='__main__':
    main()
