import sys, json, time
sys.path[:0] = ['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from hap import weak_rows
from pdicf import _pin_weak, _guide_at
from lpr import marginals, topo_order, quantile, sgs
from pact import PACT
from po import heads_tails
d=json.load(open('exp/v8u/bench_pdicf_final_pd.json'))
def get(which,name,idx):
    if which=='main':
        for c,n,i,inst,known in corpora():
            if n==name and i==idx:
                co=PACT(inst,pact_mode='complete',use_ga=False)
                L,U,s,m=co.initial_bounds(); L,U=int(L),int(U)
                ps,g,e=_guide_at(co,L) if L<U else (None,None,0)
                return c,inst,known,int(L),int(U),ps,g
    else:
        for c,n,i,inst,known,init in weak_rows(4):
            if n==name and i==idx:
                L0,U0,s0,m0,p0=init
                co,L,U,s,m,proof,pinlp=_pin_weak(inst,L0,U0,s0,m0,p0)
                ps,g,e=_guide_at(co,L) if L<U else (None,None,0)
                return c,inst,known,int(L),int(U),ps,g
def lds_order(inst,H,key,maxd=4,node_cap=60000,tcap=0.08):
    n=inst['n']; p=inst['p']; pred=inst['pred']; succ=inst['succ']; elig=inst['elig']
    t0=time.time(); nodes=0; found=None; starts=[0]*n; mach=[-1]*n; busy=[[] for _ in range(inst['m'])]
    indeg=[len(pred[i]) for i in range(n)]; ready0=frozenset(i for i in range(n) if indeg[i]==0)
    def rec(ready,indeg,disc,cm):
        nonlocal nodes,found
        if found is not None: return
        nodes+=1
        if nodes>node_cap or time.time()-t0>tcap: return
        if not ready:
            if cm<=H: found=(list(starts),list(mach),cm)
            return
        order=sorted(ready,key=lambda i:(key(i),i)); ref=order[0]
        for i in order:
            nd=disc+(0 if i==ref else 1)
            if nd>maxd: continue
            base=max([starts[j]+p[j] for j in pred[i]] or [0]); best=None
            for k in elig[i]:
                t=base
                for a,b in busy[k]:
                    if t+p[i]<=a: break
                    if t<b: t=b
                c=(t+p[i],t,k)
                if best is None or c<best: best=c
            ft,t,k=best
            if ft>H: continue
            old=list(busy[k]); busy[k].append((t,ft)); busy[k].sort(); starts[i]=t; mach[i]=k
            nr=frozenset(j for j in ready if j!=i); ni=list(indeg)
            for j in succ[i]:
                ni[j]-=1
                if ni[j]==0: nr=nr|{j}
            rec(nr,ni,nd,max(cm,ft))
            busy[k]=old; starts[i]=0; mach[i]=-1
            if found is not None: return
    rec(ready0,indeg,0,0)
    return found,nodes,time.time()-t0
if __name__=='__main__':
    targets=[('main',r) for r in d['main']['pd'] if r['probes']>0 and any(st[0]=='YES' for st in r['steps'])]
    targets+=[('weak',r) for r in d['weak']['pd'] if r['probes']>0 and any(st[0]=='YES' for st in r['steps'])]
    for which,r in targets:
        c,inst,known,L,U,ps,g=get(which,r['name'],r['idx'])
        print('\n',which,r['name'],r['idx'],'L',L)
        if ps is None: print(' no'); continue
        mrg=marginals(inst,ps,g); mean=[m for m,_ in mrg]
        est,tail=heads_tails(inst,0,[0]*inst['n'])
        ks={'mean':lambda i: mean[i]+i*1e-6,'tail':lambda i:-tail[i]+i*1e-6}
        for q in (0.02,0.1,0.25,0.5,0.75,0.9,0.98): ks['q%g'%q]=lambda i,q=q: quantile(mrg[i][1],q)+i*1e-6
        for tag,key in ks.items():
            res=None
            for dd in range(0,7):
                f,nodes,t=lds_order(inst,L,key,maxd=dd,node_cap=40000,tcap=0.05)
                if f is not None: res=(dd,nodes,round(t,3)); break
            print(' ',tag,res)
