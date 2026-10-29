import sys
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20']
import po

def inc_graph(inst, rem, est, q, h):
    n=inst['n']; p=inst['p']; pm=inst['pmask']; elig=inst['elig']
    tasks=[i for i in range(n) if (rem>>i)&1]
    adj={i:0 for i in tasks}
    for ai in range(len(tasks)):
        i=tasks[ai]
        for bj in range(ai+1,len(tasks)):
            j=tasks[bj]
            if not (set(elig[i]) & set(elig[j])):
                bad=True
            else:
                def one(a,b):
                    # a before b on one machine
                    if (pm[b]>>a)&1: return False
                    ca=est[a]+p[a]
                    if ca>h-q[a]: return False
                    sb=max(ca,est[b]); cb=sb+p[b]
                    return cb<=h-q[b]
                bad = not (one(i,j) or one(j,i))
            if bad:
                adj[i]|=1<<j; adj[j]|=1<<i
    return tasks,adj

def max_clique(tasks,adj,cap=10):
    # Tomita-style bitset B&B with greedy coloring bound, stop if size>cap? cap = m
    best=[]; bestn=0
    # greedy incumbent
    order=sorted(tasks,key=lambda v:-adj[v].bit_count())
    greedy=[]
    for v in order:
        if all((adj[v]>>u)&1 for u in greedy): greedy.append(v)
    if len(greedy)>bestn: best=greedy[:]; bestn=len(greedy)
    def color_sort(P):
        # greedy coloring, return vertices in color order and bounds
        U=P; order=[]; bounds=[]
        color=0
        while U:
            color+=1
            Q=U
            while Q:
                v=(Q & -Q).bit_length()-1
                Q &= ~(1<<v)
                U &= ~(1<<v)
                order.append(v); bounds.append(color)
        return order,bounds
    def expand(P, cur):
        nonlocal best,bestn
        if not P:
            if len(cur)>bestn: best=cur[:]; bestn=len(cur)
            return
        order,bounds=color_sort(P)
        for idx in range(len(order)-1,-1,-1):
            v=order[idx]
            if len(cur)+bounds[idx]<=bestn: return
            if len(cur)+1>bestn:
                best=cur+[v]; bestn=len(cur)+1
            expand(P & adj[v], cur+[v])
            P &= ~(1<<v)
    P=0
    for i in tasks: P|=1<<i
    expand(P, [])
    return best

if __name__=='__main__':
    import pickle,time
    SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
          ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
    for tag,path in SETS:
        d=pickle.load(open(path,'rb'))
        for k,x in enumerate(d):
            inst=x['inst'] if isinstance(x,dict) else x[0]; opt=x['opt'] if isinstance(x,dict) else x[1]
            h=opt-1; n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
            t=time.time(); tasks,adj=inc_graph(inst,inst['full'],est,q,h); c=max_clique(tasks,adj)
            print(tag,k,'n',n,'m',inst['m'],'clique',len(c),c,'t',round(time.time()-t,4))
