import sys, time, json, pickle
sys.path.insert(0,'.')
import exp_da as E
from proto_full import run_full
from proto_tent_root import tent_thresh

def run_periodic(inst, budget=800, delta=0, T_scan=40, K_cert=4, root_bound='TENT'):
    # copy of run_full with periodic tent on open nodes
    n=inst['n']; full=(1<<n)-1
    def G(S,A,c): return min(E.greedy(inst,S,A,c,r) for r in ('CP','LPT','MWKR'))
    S0,A0,c0=0,(0,0),(-1,)*n
    U=G(S0,A0,c0); L0=E.lower_L0(inst,S0,A0,c0)
    if root_bound=='TENT':
        Lg,_,_=tent_thresh(inst,S0,A0,c0,U,L0); Lg=max(L0,Lg)
    else:
        Lg=L0
    F0=Lg
    root={'S':S0,'A':A0,'c':c0,'F':F0,'f':max(max(A0),F0),'id':0}
    Open=[root]; nxt=1; Dom={0:[(A0,tuple([0]*n))]}
    steps=0; scans=0; gains=0; t0=time.time()
    while Open and steps<budget:
        fmin=min(v['f'] for v in Open)
        if fmin>=U: break
        phi=[v for v in Open if v['f']<=fmin+2]
        phi.sort(key=lambda v:(v['f'],v['id']))
        cand=phi[:32]; bestv=None; bestg=None
        for v in cand:
            g=G(v['S'],v['A'],v['c'])
            if g<U: U=g
            if bestv is None or (g,v['f'],v['id'])<(bestg,bestv['f'],bestv['id']):
                bestv,bestg=v,g
        v=bestv; Open.remove(v); steps+=1
        if steps%T_scan==0 and Open:
            scans+=1
            # nodes with largest U-f (most likely to be pruned)
            picks=sorted(Open,key=lambda x:(-(U-x['f']),x['id']))[:K_cert]
            for x in picks:
                lx=E.lower_L0(inst,x['S'],x['A'],x['c'])
                if lx>=U: continue
                tx,_,_=tent_thresh(inst,x['S'],x['A'],x['c'],U,lx)
                if tx>x['F']:
                    x['F']=tx; x['f']=max(max(x['A']),tx); gains+=1
            Open=[x for x in Open if x['f']<U]
            if not Open: break
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
            est=est0; bucket=Dom.setdefault(cs,[])
            dom=False
            for (A2,e2) in bucket:
                if all(A2[k]<=ca[k]+delta for k in range(len(ca))) and all(e2[i]<=est[i]+delta for i in range(n) if not ((cs>>i)&1)):
                    dom=True; break
            if dom: continue
            bucket[:]=[(A2,e2) for (A2,e2) in bucket if not (all(ca[k]<=A2[k]+delta for k in range(len(ca))) and all(est[i]<=e2[i]+delta for i in range(n) if not ((cs>>i)&1)))]
            if len(bucket)<60: bucket.append((ca,est))
            Open.append({'S':cs,'A':ca,'c':cc,'F':Fw,'f':fw,'id':nxt}); nxt+=1
    return {'steps':steps,'U':U,'scans':scans,'gains':gains,'time':time.time()-t0,'open':len(Open)}

def main():
    pool=pickle.load(open('pool30.pkl','rb'))
    hard=[6,11,13,14,19,27,29]
    for k in hard:
        inst,opt,nd=pool[k]
        a=run_full(inst,budget=800,delta=0,root_bound='TENT')
        b=run_periodic(inst,budget=800,delta=0,T_scan=40,K_cert=4)
        print(k,'opt',opt,'base',a['steps'],a['U'],'periodic',b['steps'],b['U'],'scans',b['scans'],'gains',b['gains'],flush=True)
if __name__=='__main__': main()
