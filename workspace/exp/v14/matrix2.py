import sys, pickle, time
sys.path.insert(0,'exp/v14')
import sp
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
idxs=[int(x) for x in sys.argv[1:]] or [4]
configs=[('v12',dict()),('time',dict(child='time')),('mix',dict(child='mix')),
 ('finish',dict(child='finish')),('mixf',dict(child='mixf')),
 ('idle',dict(child='idle')),('ratio',dict(child='ratio')),
 ('slackp',dict(child='slackp')),('time_desc',dict(child='time_desc')),
 ('time+crit',dict(child='time',order='crit')),
 ('time+descA',dict(child='time',morder='descA')),
 ('time+ascA',dict(child='time',morder='ascA'))]
for idx in idxs:
    inst,opt,n0=d[idx]
    print('=== inst',idx,'n',inst['n'],'opt',opt,flush=True)
    for name,pol in configs:
        t=time.time(); (ok,s),st=sp.decide(inst,opt-1,mode='sub',nodecap=3_000_000,policy=pol); dt=time.time()-t
        print(f'{name:12s} nodes={st["nodes"]:7d} t={dt:7.3f} tab={st["tables"]:7d} subh={st["sub_front_hits"]:6d} to={st.get("timeout",False)}',flush=True)
