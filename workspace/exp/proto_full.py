"""Full-search prototype: root TENT threshold + quotient dominance (+ delta)."""
import sys, time, json, pickle
sys.path.insert(0, '.')
import exp_da as E
from proto_tent import tent_infeasible, tent_windows
from proto_tent_root import tent_thresh

def run_full(inst, budget=800, omega=2, Bf=32, Kdom=60, delta=0,
             root_bound='L0'):
    n=inst['n']; full=(1<<n)-1
    def G(S,A,c):
        return min(E.greedy(inst,S,A,c,r) for r in ('CP','LPT','MWKR'))
    S0,A0,c0=0,(0,0),(-1,)*n
    U=G(S0,A0,c0)
    L0=E.lower_L0(inst,S0,A0,c0)
    if root_bound=='L0':
        Lg=L0
    elif root_bound=='OLD':
        Lg,_=E.thresh(inst,S0,A0,c0,U,L0,'full'); Lg=max(L0,Lg)
    else:
        Lg,_,_=tent_thresh(inst,S0,A0,c0,U,L0); Lg=max(L0,Lg)
    F0=Lg
    root={'S':S0,'A':A0,'c':c0,'F':F0,'f':max(max(A0),F0),'id':0}
    Open=[root]; nxt=1
    Dom={0:[(A0,tuple([0]*n))]}
    steps=0; anytime={}; t0=time.time()
    while Open and steps<budget:
        fmin=min(v['f'] for v in Open)
        if fmin>=U: break
        phi=[v for v in Open if v['f']<=fmin+omega]
        phi.sort(key=lambda v:(v['f'],v['id']))
        cand=phi[:Bf]
        bestv=None; bestg=None
        for v in cand:
            g=G(v['S'],v['A'],v['c'])
            if g<U: U=g
            if bestv is None or (g,v['f'],v['id'])<(bestg,bestv['f'],bestv['id']):
                bestv,bestg=v,g
        v=bestv; Open.remove(v); steps+=1
        if steps in (5,10,20,40,80,160,320): anytime[str(steps)]=U
        for (cs,ca,cc) in E.gen_children(inst,v['S'],v['A'],v['c']):
            if cs==full:
                if max(ca)<U: U=max(ca)
                continue
            l0=E.lower_L0(inst,cs,ca,cc)
            if l0>=U: continue
            wins,est0,q0=E.make_windows(inst,cs,ca,cc,U)
            if wins and E.infeasible_at(inst,cs,ca,cc,U-1,est0,q0,wins): continue
            g=G(cs,ca,cc)
            if g<U: U=g
            Fw=max(v['F'],l0); fw=max(max(ca),Fw)
            if fw>=U: continue
            est=est0
            bucket=Dom.setdefault(cs,[])
            dom=False
            for (A2,e2) in bucket:
                if all(A2[k]<=ca[k]+delta for k in range(len(ca))) and \
                   all(e2[i]<=est[i]+delta for i in range(n) if not ((cs>>i)&1)):
                    dom=True; break
            if dom: continue
            bucket[:]=[(A2,e2) for (A2,e2) in bucket
                       if not (all(ca[k]<=A2[k]+delta for k in range(len(ca))) and
                               all(est[i]<=e2[i]+delta for i in range(n) if not ((cs>>i)&1)))]
            if len(bucket)<Kdom: bucket.append((ca,est))
            Open.append({'S':cs,'A':ca,'c':cc,'F':Fw,'f':fw,'id':nxt}); nxt+=1
    L=max(Lg,min((x['f'] for x in Open),default=Lg))
    return {'steps':steps,'U':U,'L':L,'Lg':Lg,'anytime':anytime,
            'time':time.time()-t0,'open':len(Open),'L0':L0}

def main():
    pool=pickle.load(open('pool30.pkl','rb'))
    rows=[]
    for k,(inst,opt,nd) in enumerate(pool):
        out={}
        for tag,rb in (('L0','L0'),('OLD','OLD'),('TENT','TENT')):
            out[tag]=run_full(inst,budget=800,delta=0,root_bound=rb)
        outd=run_full(inst,budget=800,delta=1,root_bound='TENT')
        assert all(out[t]['U']==opt for t in out) and outd['U']==opt
        row=dict(k=k,opt=opt,L0=out['L0']['L0'],
                 n0=out['L0']['steps'],nold=out['OLD']['steps'],nt=out['TENT']['steps'],
                 nd=outd['steps'],Lg=out['TENT']['Lg'],
                 u=out['TENT']['U'],ud=outd['U'],
                 t0=round(out['L0']['time'],4),told=round(out['OLD']['time'],4),
                 tt=round(out['TENT']['time'],4),td=round(outd['time'],4))
        rows.append(row)
        print(k,'opt',opt,'L0',row['L0'],'Lg',row['Lg'],'n',row['n0'],row['nold'],row['nt'],'d1',row['nd'],flush=True)
    print('tot n',sum(r['n0'] for r in rows),sum(r['nold'] for r in rows),
          sum(r['nt'] for r in rows),sum(r['nd'] for r in rows))
    print('TENT vs L0 wins',sum(1 for r in rows if r['nt']<r['n0']),
          'loss',sum(1 for r in rows if r['nt']>r['n0']))
    print('TENT vs OLD wins',sum(1 for r in rows if r['nt']<r['nold']),
          'loss',sum(1 for r in rows if r['nt']>r['nold']))
    print('delta1 vs TENT wins',sum(1 for r in rows if r['nd']<r['nt']),
          'loss',sum(1 for r in rows if r['nd']>r['nt']))
    print('wall',round(sum(r['tt'] for r in rows),3),round(sum(r['td'] for r in rows),3))
    json.dump(rows,open('proto_full.json','w'),indent=1)

if __name__=='__main__':
    main()
