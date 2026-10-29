"""Prototype: additive eps-dominance (delta=1) on the quotient state."""
import sys, time, json, pickle
sys.path.insert(0, '.')
import exp_da as E

def run_q(inst, budget=600, omega=2, Bf=32, Kdom=60, delta=0):
    n=inst['n']; full=(1<<n)-1
    def G(S,A,c):
        return min(E.greedy(inst,S,A,c,r) for r in ('CP','LPT','MWKR'))
    S0,A0,c0=0,(0,0),(-1,)*n
    U=G(S0,A0,c0); L0=E.lower_L0(inst,S0,A0,c0)
    F0=L0
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
            g=G(cs,ca,cc)
            if g<U: U=g
            Fw=max(v['F'],l0); fw=max(max(ca),Fw)
            if fw>=U: continue
            est,_=E.heads_tails(inst,cs,cc)
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
    L=max(F0,min((x['f'] for x in Open),default=F0))
    return {'steps':steps,'U':U,'L':L,'anytime':anytime,'time':time.time()-t0,
            'open':len(Open),'L0':L0}

def main():
    pool=pickle.load(open('pool30.pkl','rb'))
    rows=[]
    for k,(inst,opt,nd) in enumerate(pool):
        rs={}
        for delta in (0,1,2):
            rs[delta]=run_q(inst,budget=800,delta=delta)
            assert rs[delta]['U']>=opt
        row=dict(k=k,n=inst['n'],opt=opt,L0=rs[0]['L0'],
                 n0=rs[0]['steps'],n1=rs[1]['steps'],n2=rs[2]['steps'],
                 u0=rs[0]['U'],u1=rs[1]['U'],u2=rs[2]['U'],
                 up1=rs[1]['U']-opt,up2=rs[2]['U']-opt,
                 t1=round(rs[1]['time'],4),t2=round(rs[2]['time'],4))
        rows.append(row)
        print(k,'opt',opt,'L0',rs[0]['L0'],'n',rs[0]['steps'],rs[1]['steps'],rs[2]['steps'],
              'up',rs[1]['U']-opt,rs[2]['U']-opt,flush=True)
    print('tot',sum(r['n0'] for r in rows),sum(r['n1'] for r in rows),sum(r['n2'] for r in rows))
    print('delta1 gains',sum(1 for r in rows if r['n1']<r['n0']),
          'loss',sum(1 for r in rows if r['n1']>r['n0']),
          'U>opt',sum(1 for r in rows if r['up1']>0),'max up',max(r['up1'] for r in rows))
    print('delta2 gains',sum(1 for r in rows if r['n2']<r['n0']),
          'loss',sum(1 for r in rows if r['n2']>r['n0']),
          'U>opt',sum(1 for r in rows if r['up2']>0),'max up',max(r['up2'] for r in rows))
    json.dump(rows,open('proto_eps.json','w'),indent=1)

if __name__=='__main__':
    main()
