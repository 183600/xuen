import sys, pickle, time
sys.path.insert(0,'exp/v14')
import sp
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
idxs=[int(x) for x in sys.argv[1:]] or [10]
configs=[('v12',dict()),('c1',dict(closure=1)),('c2',dict(closure=2)),
 ('time',dict(child='time')),('time+c1',dict(child='time',closure=1)),
 ('idle+c1',dict(child='idle',closure=1)),('time+c2',dict(child='time',closure=2))]
for idx in idxs:
    inst,opt,n0=d[idx]
    print('=== inst',idx,'n',inst['n'],'opt',opt,flush=True)
    for name,pol in configs:
        t=time.time(); (ok,s),st=sp.decide(inst,opt-1,mode='sub',nodecap=3_000_000,policy=pol); dt=time.time()-t
        print(f'{name:12s} nodes={st["nodes"]:7d} t={dt:7.3f} tab={st["tables"]:7d} subh={st["sub_front_hits"]:6d} ins={st["inserts"]:7d}',flush=True)
