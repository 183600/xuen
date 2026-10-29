"""Negative results: (1) general pair probing is unsound; (2) order/restarts."""
import sys,pickle,json,random,time
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v21']
import po,pace_v20,pace_v21
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def load(path):
    d=pickle.load(open(path,'rb')); return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def run(mod,inst,h,**kw): return mod.decide(inst,h,odom=False,dcd=True,hpack_on=True,omd=fe(inst),**CFG,**kw)
out={}
# ---- (1) minimal counterexample ----
inst=po.make_inst([1,1,1,1],2,[[],[],[],[]])
for tag,kw in [('v20',dict(dhd=True)),('v21_rigid',dict(dhd=True,dpl=True)),
               ('v21_general',dict(dhd=True,dpl=True,dpl_general=True))]:
    (b,o),st=run(pace_v20 if tag=='v20' else pace_v21,inst,2,**kw)
    print('cex h=2',tag,'answer',b,'nodes',st['nodes']); out['cex_'+tag]=b
# sanity: rigid must say YES
assert out['cex_v20'] is True and out['cex_v21_rigid'] is True
# ---- (2) tempting gains of the unsound rule ----
D=pickle.load(open('exp/v18/deep.pkl','rb'))
g_tot=0; g_yesbad=0; g_nodes=[]
for idx,(inst,opt,*_) in enumerate(D):
    (b,_),st=run(pace_v21,inst,opt-1,dhd=True,dpl=True,dpl_general=True)
    g_tot+=st['nodes']; g_nodes.append(st['nodes'])
    (ok,_),_=run(pace_v21,inst,opt,dhd=True,dpl=True,dpl_general=True)
    if not ok: g_yesbad+=1
print('general deep h=OPT-1 nodes',g_tot,'YES failures at h=OPT',g_yesbad)
out['general_deep']=dict(nodes=g_tot,per=g_nodes,yes_fail=g_yesbad)
H=load('exp/v13/hard3.pkl'); g_tot=0; g_yesbad=0
for idx,r in enumerate(H):
    inst,opt=r['inst'],r['opt']
    (b,_),st=run(pace_v21,inst,opt-1,dhd=True,dpl=True,dpl_general=True)
    g_tot+=st['nodes']
    (ok,_),_=run(pace_v21,inst,opt,dhd=True,dpl=True,dpl_general=True)
    if not ok: g_yesbad+=1
print('general hard3 h=OPT-1 nodes',g_tot,'YES failures',g_yesbad)
out['general_hard3']=dict(nodes=g_tot,yes_fail=g_yesbad)
# ---- (3) order invariance on NO ----
# regenerate the 50 held-out instances exactly as v20 did
def gen(rng,n,m):
    p=[rng.randint(2,9) for _ in range(n)]; pred=[[] for _ in range(n)]
    ep=rng.choice([0.18,0.22,0.28,0.35])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j]: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)
import pace_q
rng=random.Random(424242); held=[]; tried=0
while len(held)<50 and tried<3000:
    tried+=1; n=rng.randint(12,16); inst=gen(rng,n,3)
    est,q=po.heads_tails(inst,0,[0]*n)
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3)
    opt=None
    for h in range(lo,lo+18):
        (ok,_),_=pace_q.decide(inst,h,odom=False,hpack_on=False,omd=True,**CFG)
        if ok: opt=h; break
    if opt is None: continue
    (b,_),sb=pace_q.decide(inst,opt-1,odom=False,hpack_on=False,omd=True,**CFG)
    if sb['nodes']<15: continue
    held.append((inst,opt))
res={}
for order in ['slack','late','loss','astar']:
    tot=0; per=[]
    for inst,opt in held:
        (b,_),st=run(pace_v20,inst,opt-1,dhd=True,order=order)
        assert b is False; tot+=st['nodes']; per.append(st['nodes'])
    res[order]=tot; print('order',order,'NO nodes',tot)
out['order_invariance']=res
json.dump(out,open('exp/v21/res_neg.json','w'),indent=1)
