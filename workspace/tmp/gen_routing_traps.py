import sys, itertools, random, json, time
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from pact import pact_decide, PACT
from pdicf import run_pdicf
from eba import run_eba
from lpr import sgs

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
            out.append(list(order)); return
        for i in range(n):
            if i in done: continue
            if all(j in done for j in inst['pred'][i]):
                done.add(i); order.append(i)
                rec(order,done)
                order.pop(); done.remove(i)
    rec([],set()); return out

def min_order_greedy(inst):
    best=10**9; bo=None
    for o in topo_orders(inst):
        z=sgs(inst,o,None)
        if z and z[2]<best: best=z[2]; bo=o
    return best,bo

def find_opt(inst):
    lo=max(inst['p']); hi=sum(inst['p'])
    for h in range(lo,hi+1):
        r=pact_decide(inst,h,depthcap=None,nodecap=None)
        if r['verdict'] is True: return h
    return None

random.seed(7)
traps=[]; tries=0
base_p=[1,2,2,6]; base_elig=[[0],[0,1],[1],[0,1]]; base_pred=[[],[0],[1],[]]
while len(traps)<20 and tries<5000:
    tries+=1
    k=random.randint(2,4); n=4+k; m=2
    p=list(base_p)+[random.randint(1,6) for _ in range(k)]
    elig=[list(e) for e in base_elig]
    for _ in range(k):
        if random.random()<0.5: elig.append([0])
        elif random.random()<0.5: elig.append([1])
        else: elig.append([0,1])
    pred=[list(x) for x in base_pred]
    for j in range(4,n):
        cand=[i for i in range(j) if random.random()<0.18]
        pred.append(cand)
    inst=make(n,m,p,elig,pred)
    opt=find_opt(inst)
    if opt is None: continue
    g,bo=min_order_greedy(inst)
    if g<=opt: continue
    # ensure the trap is the reason: routing-aware witness exists at opt
    # run PD/EBA
    try:
        rp=run_pdicf(inst,opt,'trap',len(traps),seed=0)
        re=run_eba(inst,opt,'trap',len(traps),seed=0,lds_nodes=1500,
                   lds_time=0.02,do_ea=False,do_route=True)
    except Exception as ex:
        print('run err',ex); continue
    traps.append(dict(n=n,m=m,p=p,elig=elig,pred=pred,opt=opt,
                      min_order=g,best_order=bo,
                      pd_probes=rp['probes'],pd_ok=rp['ok'],
                      eba_probes=re['probes'],eba_ok=re['ok'],
                      eba_steps=re['steps'][:3],eba_kind=re['steps'][0][3] if re['steps'] else None,
                      pd_steps=rp['steps'][:3]))
    print(len(traps),'n',n,'opt',opt,'greedy',g,'pd',rp['probes'],'eba',re['probes'],
          re['steps'][0][3] if re['steps'] else None)
print('tries',tries)
json.dump(traps,open('exp/v8u/routing_traps.json','w'),indent=1)
