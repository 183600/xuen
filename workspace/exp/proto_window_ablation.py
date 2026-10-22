import sys, json, pickle
sys.path.insert(0,'.')
import exp_da as E
from proto_tent import tent_infeasible, tent_windows
from proto_tent_root import tent_thresh

def tent_thresh_wins(inst,S,A,c,U,L0,wins):
    est,q=E.heads_tails(inst,S,c)
    best=None
    for (a,b,ub) in wins:
        lo,hi=L0,U-1; hh=None
        while lo<=hi:
            mid=(lo+hi)//2
            if tent_infeasible(inst,S,A,c,mid,a,b,est,q):
                hh=mid; lo=mid+1
            else: hi=mid-1
        if hh is not None and (best is None or hh>best): best=hh
    return (best+1 if best is not None else L0)

def main():
    pool=pickle.load(open('pool30.pkl','rb'))
    rows=[]
    for k,(inst,opt,nd) in enumerate(pool):
        S0,A0,c0=0,(0,0),(-1,)*inst['n']
        L0=E.lower_L0(inst,S0,A0,c0); U=E.guide(inst,S0,A0,c0)
        wins,_,_=E.make_windows(inst,S0,A0,c0,U)
        oldfam=tent_thresh_wins(inst,S0,A0,c0,U,L0,wins)
        full,_,_=tent_thresh(inst,S0,A0,c0,U,L0)
        row=dict(k=k,opt=opt,L0=L0,U=U,oldfam=oldfam,full=full,
                 wins=len(wins),fullwins=len(tent_windows(inst,S0,A0,c0,U-1,E.heads_tails(inst,S0,c0)[0],E.heads_tails(inst,S0,c0)[1])))
        rows.append(row)
        print(k,'L0',L0,'oldfam',oldfam,'full',full,'nw',row['wins'],row['fullwins'],flush=True)
    print('full>oldfam',sum(r['full']>r['oldfam'] for r in rows),
          'oldfam>full',sum(r['oldfam']>r['full'] for r in rows),
          'sum',sum(r['oldfam'] for r in rows),sum(r['full'] for r in rows))
    json.dump(rows,open('proto_window_ablation.json','w'),indent=1)
if __name__=='__main__': main()
