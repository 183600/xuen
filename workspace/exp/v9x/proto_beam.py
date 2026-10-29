"""Prototype: trie/beam decrease-and-conquer primal for ICF-PACT."""
import sys, time, json, collections, random
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora, cmax
from po import heads_tails
from rdf import check_schedule, _earliest


def _avail(inst, mask, n):
    return [i for i in range(n) if not (mask>>i)&1 and all((mask>>j)&1 for j in inst['pred'][i])]


def _bound(inst, mask, starts, cmax_sofar, target):
    n=inst['n']; p=inst['p']
    fin=[(starts[i]+p[i]) if (mask>>i)&1 else 0 for i in range(n)]
    est,q=heads_tails(inst, mask, fin)
    lb=cmax_sofar
    for i in range(n):
        if not (mask>>i)&1:
            v=est[i]+p[i]+q[i]
            if v>lb: lb=v
    return lb


def expand(inst, st, target):
    n=inst['n']; p=inst['p']; m=inst['m']
    mask, starts, machs, busy, predfin, cm = st[:6]
    out=[]
    for i in _avail(inst, mask, n):
        base=predfin[i]
        best=None
        for k in inst['elig'][i]:
            t=_earliest(busy[k], base, p[i])
            cand=(t+p[i], t, k)
            if best is None or cand<best: best=cand
        if best is None: continue
        ft,t,k=best
        if ft>target: continue
        nm=mask|(1<<i)
        ns=list(starts); ns[i]=t
        nmach=list(machs); nmach[i]=k
        nb=[list(x) for x in busy]; nb[k].append((t,ft)); nb[k].sort()
        npf=list(predfin)
        for j in inst['succ'][i]:
            if ft>npf[j]: npf[j]=ft
        lb=_bound(inst,nm,ns,max(cm,ft),target)
        if lb>target: continue
        out.append((nm,ns,nmach,nb,npf,max(cm,ft),lb,i))
    return out


def key(st):
    mask,starts,machs,busy,predfin,cm,lb,i=st
    return (mask, tuple(tuple(x) for x in busy), tuple(predfin))


def beam(inst, target, width=100, seed_orders=None, verbose=False):
    n=inst['n']; p=inst['p']
    t0=time.time()
    root=(0,[None]*n,[None]*n,[[] for _ in range(inst['m'])],[0]*n,0)
    # compute root lb
    lb0=_bound(inst,0,[0]*n,0,target)
    if lb0>target: return None,dict(nodes=0,t=0)
    beam=[root+ (lb0,)]
    seen=set()
    nodes=0
    for depth in range(n):
        cand=[]
        for st in beam:
            ch=expand(inst,st,target)
            nodes+=len(ch)
            for c in ch:
                k=key(c)
                if k in seen: continue
                seen.add(k)
                cand.append(c)
        if not cand:
            return None,dict(nodes=nodes,t=round(time.time()-t0,4),depth=depth)
        # score: lower bound, then cmax, then sum starts
        cand.sort(key=lambda s:(s[6],s[5],sum(x for x in s[1] if x is not None),s[0]))
        beam=cand[:width]
        if verbose:
            print('depth',depth,'cand',len(cand),'beam',len(beam),'bestlb',beam[0][6])
    # complete
    for st in beam:
        if st[0]==(1<<n)-1:
            s,m,c=st[1],st[2],st[5]
            if c<=target and check_schedule(inst,c,s,m):
                return (s,m,c),dict(nodes=nodes,t=round(time.time()-t0,4),width=width)
    return None,dict(nodes=nodes,t=round(time.time()-t0,4),width=width)


def main():
    rows=list(corpora())
    sp=json.load(open('exp/v91/bench_sparc.json'))['rows']['strong_pso1_lower']
    # match by corpus/name/idx
    idx={}
    for j,(corpus,name,idx0,inst,known) in enumerate(rows):
        idx[(corpus,name,idx0)]=j
    hard=[]
    for r in sp:
        if r['known']==r['lb0'] and r['ub_pso']>r['lb0']:
            hard.append(r)
    print('hard',len(hard))
    for width in (20,50,100,200,500):
        ok=0; tt=0; nn=0; details=[]
        for r in hard:
            j=idx[(r['corpus'],r['name'],r['idx'])]
            corpus,name,idx0,inst,known=rows[j]
            target=r['lb0']
            sol,st=beam(inst,target,width=width)
            tt+=st['t']; nn+=st['nodes']
            if sol is not None: ok+=1
            details.append((r['corpus'],r['name'],r['idx'],r['known'],target,sol is not None,st))
        print('width',width,'ok',ok,'/',len(hard),'nodes',nn,'t',round(tt,3))
        if width==100:
            for d in details: print(' ',d[:6])

if __name__=='__main__':
    main()
