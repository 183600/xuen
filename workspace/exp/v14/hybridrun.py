import sys, pickle, time, random
sys.path.insert(0,'exp/v14')
import sp, lls, hybrid
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
print('=== 12 hard UNSAT (h=OPT-1) ===')
tot={'dfs':0,'lls':0,'hyb':0,'dl':0,'ll':0}
for idx,(inst,opt,n0) in enumerate(d):
    t=time.time(); (ok,_),st=sp.decide(inst,opt-1,mode='sub'); td=time.time()-t
    t=time.time(); (ok2,_),st2=lls.decide_lls(inst,opt-1); tl=time.time()-t
    hy=hybrid.solve(inst,opt-1)
    tot['dfs']+=td; tot['lls']+=tl; tot['hyb']+=hy['t']; tot['dl']+=st['nodes']; tot['ll']+=st2['labels']
    print(idx,'DFSn',st['nodes'],'LLSlab',st2['labels'],'hyb',hy['engine'],'dfs_n',hy['dfs_nodes'],'t',round(td,3),round(tl,3),round(hy['t'],3),flush=True)
print('TOT dfs',round(tot['dfs'],3),'lls',round(tot['lls'],3),'hyb',round(tot['hyb'],3),'nodes',tot['dl'],'labels',tot['ll'])
print('=== 12 hard at h=OPT (SAT) ===')
for idx,(inst,opt,n0) in enumerate(d):
    t=time.time(); (ok,_),st=sp.decide(inst,opt,mode='sub',nodecap=500000); td=time.time()-t
    t=time.time(); (ok2,_),st2=lls.decide_lls(inst,opt,labelcap=300000); tl=time.time()-t
    hy=hybrid.solve(inst,opt)
    print(idx,'DFS',ok,st['nodes'],round(td,4),'LLS',ok2,st2['labels'],round(tl,3),'hyb',hy['engine'],hy['ok'],round(hy['t'],4),flush=True)
