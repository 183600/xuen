import sys, time, json, pickle
sys.path.insert(0,'.')
import exp_da as E
from proto_full import run_full
from proto_tent import tent_infeasible, tent_windows
from proto_tent_root import tent_thresh

def run_tp(inst, budget=900, delta=0, root_bound='TENT', tent_point=True):
    n=inst['n']; full=(1<<n)-1
    def G(S,A,c): return min(E.greedy(inst,S,A,c,r) for r in ('CP','LPT','MWKR'))
    S0,A0,c0=0,(0,0),(-1,)*n
    U=G(S0,A0,c0); L0=E.lower_L0(inst,S0,A0,c0)
    if root_bound=='TENT':
        Lg,_,_=tent_thresh(inst,S0,A0,c0,U,L0); Lg=max(L0,Lg)
    else: Lg=L0
    F0=Lg; root={'S':S0,'A':A0,'c':c0,'F':F0,'f':max(max(A0),F0),'id':0}
    Open=[root]; nxt=1; Dom={0:[(A0,est0:=tuple([0]*n))]}
    steps=0; t0=time.time(); tpack=0.0
    while Open and steps<budget:
        fmin=min(v['f'] for v in Open)
        if fmin>=U: break
        phi=[v for v in Open if v['f']<=fmin+2]; phi.sort(key=lambda v:(v['f'],v['id']))
        cand=phi[:32]; bestv=None; bestg=None
        for v in cand:
            g=G(v['S'],v['A'],v['c'])
            if g<U: U=g
            if bestv is None or (g,v['f'],v['id'])<(bestg,bestv['f'],bestv['id']): bestv,bestg=v,g
        v=bestv; Open.remove(v); steps+=1
        for (cs,ca,cc) in E.gen_children(inst,v['S'],v['A'],v['c']):
            if cs==full:
                if max(ca)<U: U=max(ca)
                continue
            l0=E.lower_L0(inst,cs,ca,cc)
            if l0>=U: continue
            wins,est0,q0=E.make_windows(inst,cs,ca,cc,U)
            if wins and E.infeasible_at(inst,cs,ca,cc,U-1,est0,q0,wins): continue
            if tent_point:
                tp=time.time()
                H=U-1
                tw=tent_windows(inst,cs,ca,cc,H,est0,q0)
                hit=any(tent_infeasible(inst,cs,ca,cc,H,a,b,est0,q0) for (a,b) in tw)
                tpack+=time.time()-tp
                if hit: continue
            g=G(cs,ca,cc)
            if g<U: U=g
            Fw=max(v['F'],l0); fw=max(max(ca),Fw)
            if fw>=U: continue
            bucket=Dom.setdefault(cs,[])
            dom=False
            for (A2,e2) in bucket:
                if all(A2[k]<=ca[k]+delta for k in range(len(ca))) and all(e2[i]<=est0[i]+delta for i in range(n) if not ((cs>>i)&1)):
                    dom=True; break
            if dom: continue
            bucket[:]=[(A2,e2) for (A2,e2) in bucket if not (all(ca[k]<=A2[k]+delta for k in range(len(ca))) and all(est0[i]<=e2[i]+delta for i in range(n) if not ((cs>>i)&1)))]
            if len(bucket)<60: bucket.append((ca,est0))
            Open.append({'S':cs,'A':ca,'c':cc,'F':Fw,'f':fw,'id':nxt}); nxt+=1
    return {'steps':steps,'U':U,'time':time.time()-t0,'tpack':tpack,'open':len(Open)}

def main():
    pool=pickle.load(open('pool30.pkl','rb'))
    tot=0; rows=[]
    for k,(inst,opt,nd) in enumerate(pool):
        a=run_full(inst,budget=900,root_bound='TENT',delta=0)
        b=run_tp(inst,budget=900,root_bound='TENT',delta=0,tent_point=True)
        assert a['U']==opt and b['U']==opt
        tot+=b['steps']; rows.append((k,a['steps'],b['steps'],b['tpack']))
        print(k,'base',a['steps'],'tentpoint',b['steps'],'tpack',round(b['tpack'],3),flush=True)
    print('tot base',sum(r[1] for r in rows),'tentpoint',tot)
    json.dump(rows,open('proto_tentpoint.json','w'))
if __name__=='__main__': main()
