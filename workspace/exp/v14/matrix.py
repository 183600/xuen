import sys, pickle, time, json
sys.path.insert(0,'exp/v14')
import sp
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
idxs=[int(x) for x in sys.argv[1:]] or [10]
def C(**kw): return kw
configs=[
 ('v12',C()),
 ('time',C(child='time')),
 ('late',C(child='late')),
 ('tight',C(child='tight')),
 ('cp',C(child='p')),
 ('load',C(child='load')),
 ('crit',C(order='crit')),
 ('idx',C(order='idx')),
 ('spt',C(order='spt')),
 ('succ',C(order='succ')),
 ('est',C(order='est')),
 ('lpts',C(order='lpt_slack')),
 ('time+etail',C(child='time',etail=True)),
 ('time+est0',C(child='time',est_zero=True)),
 ('tight+etail',C(child='tight',etail=True)),
 ('descA',C(morder='descA')),
]
for idx in idxs:
    inst,opt,n0=d[idx]
    print('=== inst',idx,'n',inst['n'],'opt',opt,'v12nodes',n0,flush=True)
    for name,pol in configs:
        t=time.time()
        (ok,s),st=sp.decide(inst,opt-1,mode='sub',nodecap=2_500_000,policy=pol)
        dt=time.time()-t
        print(f'{name:12s} nodes={st["nodes"]:7d} t={dt:7.3f} tab={st["tables"]:7d} subh={st["sub_front_hits"]:6d}',flush=True)
