import sys,time,itertools
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from po import heads_tails
from rdf import check_schedule

def sgs(inst,h,weights):
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q=heads_tails(inst,0,[0]*n)
    pred=[set(x) for x in inst['pred']]
    done=set(); starts=[None]*n; mach=[None]*n; avail=[0]*m
    while len(done)<n:
        avail_tasks=[i for i in range(n) if i not in done and pred[i]<=done]
        if not avail_tasks: return None
        cand=[]
        for i in avail_tasks:
            r=est[i]
            for j in pred[i]: r=max(r,starts[j]+p[j])
            best=None
            for k in inst['elig'][i]:
                s=max(r,avail[k])
                if best is None or s<best[0] or (s==best[0] and k<best[1]): best=(s,k)
            s,k=best
            if s+p[i]>h: continue
            f=[-r,-p[i],-len(inst['succ'][i]),len(inst['pred'][i]),-q[i],-s]
            sc=sum(w*v for w,v in zip(weights,f))
            cand.append((sc,-i,i,s,k))
        if not cand: return None
        cand.sort(reverse=True)
        _,_,i,s,k=cand[0]
        starts[i]=s; mach[i]=k; avail[k]=s+p[i]; done.add(i)
    cm=max(starts[i]+p[i] for i in range(n))
    if cm<=h and check_schedule(inst,h,starts,mach): return starts,mach,cm
    return None

if __name__=='__main__':
    rows=weak_rows(4)
    rules=[ws+(0,0) for ws in itertools.product((-1,0,1),repeat=4)]
    for j,(c,name,idx,inst,known,init) in enumerate(rows[:20]):
        succ=0; t=time.time()
        for ws in rules:
            if sgs(inst,known,ws) is not None: succ+=1
        print(j,c,name,idx,'known',known,'successful rules',succ,'/',len(rules),'t',round(time.time()-t,3))
