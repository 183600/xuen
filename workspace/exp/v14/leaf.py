import sys, pickle, time
sys.path.insert(0,'exp/v14')
import sp
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
idxs=[int(x) for x in sys.argv[1:]] or [10]
configs=[('v12',dict()),('leaf',dict(leaf_insert=True)),
 ('time',dict(child='time')),('time+leaf',dict(child='time',leaf_insert=True)),
 ('leaf+est0',dict(leaf_insert=True,est_zero=True)),
 ('time+leaf+est0',dict(child='time',leaf_insert=True,est_zero=True)),
 ('time+leaf+K8',dict(child='time',leaf_insert=True,K=8)),
 ('time+leaf+K16',dict(child='time',leaf_insert=True,K=16))]
for idx in idxs:
    inst,opt,n0=d[idx]
    print('=== inst',idx,'n',inst['n'],'opt',opt,flush=True)
    for name,pol in configs:
        t=time.time(); (ok,s),st=sp.decide(inst,opt-1,mode='sub',nodecap=3_000_000,policy=pol); dt=time.time()-t
        fs=st['front_sizes']; fmax=max(fs) if fs else 0
        print(f'{name:16s} nodes={st["nodes"]:7d} t={dt:7.3f} tab={st["tables"]:7d} subh={st["sub_front_hits"]:6d} ins={st["inserts"]:6d} fmax={fmax}',flush=True)
