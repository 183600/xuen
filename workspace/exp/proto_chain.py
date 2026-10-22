"""Chain-capacity tent certificate: sum of mandatory pieces on a precedence chain <= b-a."""
import sys, json, pickle
sys.path.insert(0,'.')
import exp_da as E
from proto_tent import tent_items, tent_windows, tent_infeasible
from proto_tent_root import tent_thresh

def chain_longest(inst,S,e):
    n,p,succ=inst['n'],inst['p'],inst['succ']
    f=[0]*n
    for i in range(n-1,-1,-1):
        if (S>>i)&1: continue
        b=0
        for j in succ[i]:
            if not ((S>>j)&1) and f[j]>b: b=f[j]
        f[i]=e[i]+b
    return max(f) if f else 0

def chain_infeasible(inst,S,A,c,H,a,b,est,q):
    items=tent_items(inst,S,A,c,H,a,b,est,q)
    if not items: return False
    e=[0]*inst['n']
    for idx,i in enumerate([x for x in range(inst['n']) if not ((S>>x)&1)]):
        pass
    # rebuild e by task
    n,p=inst['n'],inst['p']
    for i in range(n):
        if (S>>i)&1: continue
        u=max(0,a-est[i]); v=max(0,H-q[i]-b)
        ei=p[i]-u-v
        if ei>0: e[i]=ei
    return chain_longest(inst,S,e) > (b-a)

def chain_thresh(inst,S,A,c,U,L0):
    est,q=E.heads_tails(inst,S,c)
    wins=tent_windows(inst,S,A,c,U-1,est,q)
    best=None
    for (a,b) in wins:
        lo,hi=L0,U-1; hh=None
        while lo<=hi:
            mid=(lo+hi)//2
            if chain_infeasible(inst,S,A,c,mid,a,b,est,q):
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
        old,_=E.thresh(inst,S0,A0,c0,U,L0,'full')
        pack,_,_=tent_thresh(inst,S0,A0,c0,U,L0)
        chain=chain_thresh(inst,S0,A0,c0,U,L0)
        row=dict(k=k,opt=opt,L0=L0,U=U,old=old,pack=pack,chain=chain,
                 best=max(pack,chain))
        rows.append(row)
        print(k,'opt',opt,'L0',L0,'U',U,'old',old,'pack',pack,'chain',chain,'best',row['best'],flush=True)
    print('old>L0',sum(r['old']>r['L0'] for r in rows),
          'pack>L0',sum(r['pack']>r['L0'] for r in rows),
          'chain>L0',sum(r['chain']>r['L0'] for r in rows),
          'best>pack',sum(r['best']>r['pack'] for r in rows),
          'best==opt',sum(r['best']==r['opt'] for r in rows))
    print('sum L0',sum(r['L0'] for r in rows),'old',sum(r['old'] for r in rows),
          'pack',sum(r['pack'] for r in rows),'chain',sum(r['chain'] for r in rows),
          'best',sum(r['best'] for r in rows))
    json.dump(rows,open('proto_chain.json','w'),indent=1)

if __name__=='__main__': main()
