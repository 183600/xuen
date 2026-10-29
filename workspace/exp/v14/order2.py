import sys, pickle, time
sys.path.insert(0,'exp/v14')
import sp
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
idxs=[int(x) for x in sys.argv[1:]] or [10]
configs=[('v12',dict()),('time',dict(child='time')),('idle',dict(child='idle')),
 ('sumA',dict(child='sumA')),('maxA',dict(child='maxA')),('lexA',dict(child='lexA')),
 ('lexAasc',dict(child='lexAasc')),('lexA+crit',dict(child='lexA',order='crit')),
 ('sumA+crit',dict(child='sumA',order='crit'))]
for idx in idxs:
    inst,opt,n0=d[idx]
    print('=== inst',idx,'n',inst['n'],'opt',opt,flush=True)
    for name,pol in configs:
        t=time.time(); (ok,s),st=sp.decide(inst,opt-1,mode='sub',nodecap=3_000_000,policy=pol); dt=time.time()-t
        print(f'{name:12s} nodes={st["nodes"]:7d} t={dt:7.3f} tab={st["tables"]:7d} subh={st["sub_front_hits"]:6d}',flush=True)
