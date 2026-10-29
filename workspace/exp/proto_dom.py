"""Prototype: quotient (A,est) dominance vs v0.5 c-dominance."""
import sys, time, json, pickle
sys.path.insert(0, '.')
import exp_da as E

def run_q(inst, budget=400, omega=2, Bf=32, Kdom=60, dom_mode='c',
          tent=False, use_est_inherit=False):
    n = inst['n']; full=(1<<n)-1
    def G(S,A,c):
        vals=[E.greedy(inst,S,A,c,r) for r in ('CP','LPT','MWKR')]
        return min(vals)
    S0,A0,c0=0,(0,0),(-1,)*n
    U=G(S0,A0,c0); L0=E.lower_L0(inst,S0,A0,c0)
    Lglob=L0; F0=L0
    root={'S':S0,'A':A0,'c':c0,'F':F0,'f':max(max(A0),F0),'id':0}
    Open=[root]; nxt=1
    Dom={0:[(A0, tuple([0]*n))]}  # for est mode, store (A, est_R full)
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
        kids=E.gen_children(inst,v['S'],v['A'],v['c'])
        for (cs,ca,cc) in kids:
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
            bucket=Dom.setdefault(cs,[])
            if dom_mode=='c':
                dom=any(E.dominates(A2,c2,ca,cc,cs) for (A2,c2) in bucket)
            else:
                est=est0
                dom=False
                for (A2,e2) in bucket:
                    if all(A2[k]<=ca[k] for k in range(len(ca))) and \
                       all(e2[i]<=est[i] for i in range(n) if (cs>>i)&1 == 0):
                        dom=True; break
            if dom: continue
            if dom_mode=='c':
                bucket[:]=[(A2,c2) for (A2,c2) in bucket if not E.dominates(ca,cc,A2,c2,cs)]
                if len(bucket)<Kdom: bucket.append((ca,cc))
            else:
                est=est0
                bucket[:]=[(A2,e2) for (A2,e2) in bucket
                           if not (all(ca[k]<=A2[k] for k in range(len(ca))) and
                                   all(est[i]<=e2[i] for i in range(n) if not ((cs>>i)&1)))]
                if len(bucket)<Kdom: bucket.append((ca,est))
            Open.append({'S':cs,'A':ca,'c':cc,'F':Fw,'f':fw,'id':nxt}); nxt+=1
    L=max(Lglob,min((x['f'] for x in Open),default=Lglob))
    return {'steps':steps,'U':U,'L':L,'anytime':anytime,'time':time.time()-t0,
            'open':len(Open),'L0':L0}

def main():
    pool=pickle.load(open('pool30.pkl','rb'))
    rows=[]
    for k,(inst,opt,nd) in enumerate(pool):
        r1=run_q(inst,budget=600,dom_mode='c')
        r2=run_q(inst,budget=600,dom_mode='est')
        assert r1['U']==opt and r2['U']==opt,(k,r1['U'],r2['U'],opt)
        row=dict(k=k,n=inst['n'],opt=opt,c=r1['steps'],est=r2['steps'],
                 c_t=round(r1['time'],4),est_t=round(r2['time'],4),
                 c_any=r1['anytime'],est_any=r2['anytime'])
        rows.append(row)
        print(k,'c',r1['steps'],'est',r2['steps'],'ratio',round(r2['steps']/max(1,r1['steps']),2),flush=True)
    print('tot c',sum(r['c'] for r in rows),'est',sum(r['est'] for r in rows),
          'wins',sum(1 for r in rows if r['est']<r['c']),
          'ties',sum(1 for r in rows if r['est']==r['c']),
          'loss',sum(1 for r in rows if r['est']>r['c']))
    json.dump(rows,open('proto_dom.json','w'),indent=1)

if __name__=='__main__':
    main()
