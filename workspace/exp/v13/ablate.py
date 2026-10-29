import sys, pickle, time, json
sys.path.insert(0,'v13')
import po
d=pickle.load(open('v13/hard3.pkl','rb'))
res=[]
for idx,(inst,opt,nodes0) in enumerate(d):
    row={'n':inst['n'],'opt':opt,'bench':{}}
    print('inst',idx,'n',inst['n'],flush=True)
    for mode,label,K in [('canon','canon',48),('front','canon+packfront',48),
                         ('subonly','canon+subfront',48),('sub','canon+both',48),
                         ('sub','canon+both K=8',8),('sub','canon+both K=2',2),
                         ('sub','canon+both K=1',1)]:
        t=time.time(); (ok,_),st=po.decide(inst,opt-1,mode=mode,nodecap=2_500_000,K=K); dt=time.time()-t
        row['bench'][label]=dict(nodes=st['nodes'],t=round(dt,4),tables=st['tables'],
                                 packfh=st['pack_front_hits'],subfh=st['sub_front_hits'],
                                 fmax=max(st['front_sizes']) if st['front_sizes'] else 0)
        print('  ',label,st['nodes'],round(dt,3),flush=True)
    res.append(row)
    json.dump(res,open('v13/ablate.json','w'),indent=1)
print('saved')
