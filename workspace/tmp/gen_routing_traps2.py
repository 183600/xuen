import sys, itertools, random, json, time
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from pdicf import run_pdicf
from eba import run_eba
from lpr import sgs
from hap import init_weak

def make(n,m,p,elig,pred):
    succ=[[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]: succ[i].append(j)
    return dict(n=n,m=m,p=p,est=[0]*n,pred=pred,succ=succ,elig=elig,
                pmask=[sum(1<<k for k in elig[i]) for i in range(n)],
                desc=[0]*n,full=(1<<n)-1)

def topo_orders(inst):
    n=inst['n']; out=[]
    def rec(order,done):
        if len(order)==n:
            out.append(tuple(order)); return
        for i in range(n):
            if i in done: continue
            if all(j in done for j in inst['pred'][i]):
                done.add(i); order.append(i)
                rec(order,done)
                order.pop(); done.remove(i)
    rec([],set()); return out

def sched_fixed(inst,order,route):
    n=inst['n']; starts=[0]*n; busy=[[] for _ in range(inst['m'])]
    for i in order:
        base=max([starts[j]+inst['p'][j] for j in inst['pred'][i]] or [0])
        k=route[i]; t=base
        for a,b in busy[k]:
            if t+inst['p'][i]<=a: break
            if t<b: t=b
        ft=t+inst['p'][i]; starts[i]=t; busy[k].append((t,ft)); busy[k].sort()
    return max(starts[i]+inst['p'][i] for i in range(n))

def exact_opt(inst,orders):
    best=10**9; bo=None; br=None
    for o in orders:
        for route in itertools.product(*[inst['elig'][i] for i in range(inst['n'])]):
            c=sched_fixed(inst,o,route)
            if c<best: best=c; bo=o; br=route
    return best,bo,br

def min_order_greedy(inst,orders):
    best=10**9; bo=None
    for o in orders:
        z=sgs(inst,list(o),None)
        if z and z[2]<best: best=z[2]; bo=o
    return best,bo

random.seed(11)
traps=[]; tries=0; t0=time.time()
base_p=[1,2,2,6]; base_elig=[[0],[0,1],[1],[0,1]]; base_pred=[[],[0],[1],[]]
while len(traps)<20 and tries<3000 and time.time()-t0<300:
    tries+=1
    k=random.randint(2,3); n=4+k; m=2
    p=list(base_p)+[random.randint(1,6) for _ in range(k)]
    elig=[list(e) for e in base_elig]
    for _ in range(k):
        r=random.random()
        elig.append([0] if r<0.34 else ([1] if r<0.68 else [0,1]))
    pred=[list(x) for x in base_pred]
    for j in range(4,n):
        pred.append([i for i in range(j) if random.random()<0.15])
    inst=make(n,m,p,elig,pred)
    orders=topo_orders(inst)
    if len(orders)>6000: continue
    opt,bo,br=exact_opt(inst,orders)
    g,go=min_order_greedy(inst,orders)
    if g<=opt: continue
    try:
        init=init_weak(inst)
        rp=run_pdicf(inst,opt,'trap',len(traps),initial=init,seed=0)
        re=run_eba(inst,opt,'trap',len(traps),initial=init,seed=0,
                   lds_nodes=1500,lds_time=0.02,do_ea=False,do_route=True)
    except Exception as ex:
        print('run err',type(ex).__name__,ex); continue
    if rp['probes']<=0: continue
    traps.append(dict(n=n,m=m,p=p,elig=elig,pred=pred,opt=opt,
                      min_order=g,best_order=list(bo),best_route=list(br),
                      pd_probes=rp['probes'],pd_ok=rp['ok'],
                      eba_probes=re['probes'],eba_ok=re['ok'],
                      eba_steps=re['steps'][:3],
                      pd_steps=rp['steps'][:3]))
    print(len(traps),'n',n,'opt',opt,'greedy',g,'pd',rp['probes'],
          'eba',re['probes'], (re['steps'][0][3] if re['steps'] and len(re['steps'][0])>3 else re['steps'][0][0] if re['steps'] else None), flush=True)
print('tries',tries,'sec',round(time.time()-t0,1))
json.dump(traps,open('exp/v8u/routing_traps.json','w'),indent=1)
