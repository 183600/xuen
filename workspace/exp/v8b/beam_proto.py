import sys,pickle,random,time,heapq
sys.path[:0]=['exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13','exp/v8b']
from rdf import RDF,check_schedule,_heads_latest,_insert,_earliest
from qnc import Budget
from ce_proto import rootz,load_hard

def beam(inst,h,beamw=16,seed=0,score_mode='lb'):
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q,latest=_heads_latest(inst,h)
    # state: starts,machs,busy,rem,predfin,done,score
    starts=[None]*n;machs=[None]*n;busy=[[] for _ in range(m)]
    rem=[len(inst['pred'][i]) for i in range(n)];predfin=[0]*n;done=[False]*n
    def score(starts,machs,busy,rem,predfin,done):
        # lower bound on makespan
        lb=0
        for i in range(n):
            if done[i]:
                lb=max(lb,starts[i]+p[i]+q[i])
            else:
                lb=max(lb,max(est[i],predfin[i])+p[i]+q[i])
        # load lower bound
        loads=sum(p[i] for i in range(n) if not done[i])
        lb=max(lb,(loads+sum(1 for b in busy if b)+m-1)//m)
        return lb
    import copy
    states=[(score(starts,machs,busy,rem,predfin,done),0,starts,machs,busy,rem,predfin,done)]
    nodes=0
    for depth in range(n):
        new=[]
        for sc,_,starts,machs,busy,rem,predfin,done in states:
            av=[i for i in range(n) if not done[i] and rem[i]==0]
            for i in av:
                base=max(est[i],predfin[i])
                opts=[]
                for k in inst['elig'][i]:
                    tt=_earliest(busy[k],base,p[i])
                    if tt<=latest[i]:
                        opts.append((tt,k))
                # dedup by (tt,k) and maybe by tt representative machine
                seen=set()
                for tt,k in sorted(opts):
                    if (tt,k) in seen: continue
                    seen.add((tt,k))
                    ns=list(starts);nm=list(machs);nb=[list(x) for x in busy]
                    nr=list(rem);npf=list(predfin);nd=list(done)
                    ns[i]=tt;nm[i]=k;nd[i]=True
                    _insert(nb,k,tt,tt+p[i])
                    for j in inst['succ'][i]:
                        npf[j]=max(npf[j],tt+p[i]);nr[j]-=1
                    nodes+=1
                    nsc=score(ns,nm,nb,nr,npf,nd)
                    new.append((nsc,nodes,ns,nm,nb,nr,npf,nd))
        if not new: return None,nodes
        # dedup by (scheduled set, starts,machs)
        new.sort(key=lambda x:(x[0],x[1]))
        states=[];seen=set()
        for st in new:
            key=tuple((st[2][i],st[3][i]) if st[7][i] else None for i in range(n))
            if key in seen: continue
            seen.add(key);states.append(st)
            if len(states)>=beamw: break
        # check complete
        for st in states:
            if all(st[7]):
                starts2,machs2=st[2],st[3]
                cmax=max(starts2[i]+p[i] for i in range(n))
                if cmax<=h and check_schedule(inst,h,starts2,machs2):
                    return (starts2,machs2,cmax),nodes
    return None,nodes

if __name__=='__main__':
    for name,idx,inst,opt in load_hard():
        t0=time.time(); got,nodes=beam(inst,opt,beamw=16)
        ok=got is not None
        print(name,idx,'ok',ok,'nodes',nodes,'t',round(time.time()-t0,2))
