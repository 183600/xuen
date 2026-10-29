import itertools, random, sys
sys.path[:0]=['exp/v8u']
from lpr import sgs, topo_order

def make_inst(n,m,p,elig,pred=None):
    pred=pred or [[] for _ in range(n)]
    succ=[[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]: succ[i].append(j)
    return dict(n=n,m=m,p=p,est=[0]*n,pred=pred,succ=succ,elig=elig)

def greedy_order_cmax(inst, order):
    r=sgs(inst,order,None)
    return None if r is None else r[2]

def exact_opt(inst):
    n=inst['n']; best=10**9; bestx=None
    for order in itertools.permutations(range(n)):
        # check topo
        pos={v:k for k,v in enumerate(order)}
        ok=all(pos[i]<pos[j] for j in range(n) for i in inst['pred'][j])
        if not ok: continue
        # assignments
        for route in itertools.product(*[inst['elig'][i] for i in range(n)]):
            starts=[0]*n; busy=[[] for _ in range(inst['m'])]; ok=True
            for i in order:
                base=max([starts[j]+inst['p'][j] for j in inst['pred'][i]] or [0])
                k=route[i]; t=base
                for a,b in busy[k]:
                    if t+inst['p'][i]<=a: break
                    if t<b: t=b
                ft=t+inst['p'][i]
                starts[i]=t; busy[k].append((t,ft)); busy[k].sort()
            c=max(starts[i]+inst['p'][i] for i in range(n))
            if c<best: best=c; bestx=(order,route)
    return best,bestx

def min_order_greedy(inst):
    n=inst['n']; best=10**9; bo=None
    for order in itertools.permutations(range(n)):
        pos={v:k for k,v in enumerate(order)}
        if not all(pos[i]<pos[j] for j in range(n) for i in inst['pred'][j]): continue
        c=greedy_order_cmax(inst,list(order))
        if c is not None and c<best: best=c; bo=order
    return best,bo

random.seed(1)
for n,m in [(4,2),(5,2),(5,3),(6,2)]:
    for trial in range(20000):
        p=[random.randint(1,6) for _ in range(n)]
        elig=[]
        for i in range(n):
            k=random.randint(1,m)
            elig.append(sorted(random.sample(range(m),k)))
        # random precedence DAG
        pred=[[] for _ in range(n)]
        for j in range(n):
            for i in range(j):
                if random.random()<0.25: pred[j].append(i)
        inst=make_inst(n,m,p,elig,pred)
        opt,x=exact_opt(inst)
        g,bo=min_order_greedy(inst)
        if g>opt:
            print('FOUND',n,m,'p',p,'elig',elig,'pred',pred,'opt',opt,'greedy',g)
            print('opt witness',x)
            print('best order',bo)
            sys.exit(0)
    print('done',n,m)
print('none')
