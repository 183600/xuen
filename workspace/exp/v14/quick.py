import sys, pickle, time
sys.path.insert(0,'exp/v14')
import sp
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
idxs=[int(x) for x in sys.argv[1:]] or [10]
configs=[
 ('v12',dict()),
 ('est0',dict(est_zero=True)),
 ('etail',dict(etail=True)),
 ('both',dict(est_zero=True,etail=True)),
 ('both+lpt',dict(est_zero=True,etail=True,order='lpt')),
 ('both+crit',dict(est_zero=True,etail=True,order='crit')),
 ('both+descA',dict(est_zero=True,etail=True,morder='descA')),
 ('both+late',dict(est_zero=True,etail=True,child='late')),
 ('both+time',dict(est_zero=True,etail=True,child='time')),
 ('both+p',dict(est_zero=True,etail=True,child='p')),
]
for idx in idxs:
    inst,opt,n0=d[idx]
    print('=== inst',idx,'n',inst['n'],'opt',opt)
    for name,pol in configs:
        t=time.time()
        (ok,s),st=sp.decide(inst,opt-1,mode='sub',nodecap=2_500_000,policy=pol)
        dt=time.time()-t
        print(f'{name:12s} ok={ok} nodes={st["nodes"]:7d} t={dt:7.3f} tab={st["tables"]:7d} memo={st["memo_hits"]:6d} subh={st["sub_front_hits"]:6d} dead={st["dead"]:6d} ez={st["estc_zeroed"]}/{st["estc_total"]}')
