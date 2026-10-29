import sys, pickle, time
sys.path.insert(0,'exp/v14')
import sp, lls, hybrid
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
for B in [256,512,1024,2048,4096]:
    tu=0.0; ts=0.0; nlls=0
    for idx,(inst,opt,n0) in enumerate(d):
        hy=hybrid.solve(inst,opt-1,dfs_budget=B); tu+=hy['t']; nlls+= (hy['engine']=='lls')
    for idx,(inst,opt,n0) in enumerate(d):
        hy=hybrid.solve(inst,opt,dfs_budget=B); ts+=hy['t']
    print('B',B,'UNSAT t',round(tu,3),'LLS fallbacks',nlls,'SAT t',round(ts,3),flush=True)
# pure baselines
tu=sum(sp.decide(inst,opt-1,mode='sub')[1]['nodes']*0 for inst,opt,_ in d)
