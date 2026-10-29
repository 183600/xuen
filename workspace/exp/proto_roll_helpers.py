import sys
sys.path.insert(0,'/home/runner/work/xuen/xuen/workspace/exp')
import exp_da as E
from proto_cert import greedy_lst

def rollout(inst, inner='LST'):
    n,p,pred=inst['n'],inst['p'],inst['pred']
    S,A,c=0,[0,0],[-1]*n
    pv=[]
    while True:
        ready=[i for i in range(n) if not ((S>>i)&1) and all((S>>j)&1 for j in pred[i])]
        if not ready: break
        best=None
        for i in ready:
            base=max([c[j] for j in pred[i]]+[0])
            for k in range(len(A)):
                st=max(A[k],base)
                A2=list(A); A2[k]=st+p[i]
                c2=list(c); c2[i]=st+p[i]
                val=greedy_lst(inst,S|(1<<i),tuple(sorted(A2)),tuple(c2))
                if best is None or (val,i,k)<best: best=(val,i,k)
        val,i,k=best
        base=max([c[j] for j in pred[i]]+[0]); st=max(A[k],base)
        A[k]=st+p[i]; c[i]=st+p[i]; S|=1<<i
        pv.append((i,k))
    return max(A),pv
