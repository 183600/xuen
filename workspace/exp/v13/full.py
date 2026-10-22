import sys,pickle,time,json
sys.path.insert(0,'v13')
import po
d=pickle.load(open('v13/hard3.pkl','rb'))
res=[]
for i,(inst,opt,_) in enumerate(d):
    t=time.time(); (ok,_),st=po.decide(inst,opt-1,mode='full',nodecap=2_500_000); dt=time.time()-t
    res.append(dict(nodes=st['nodes'],t=round(dt,4),tables=st['tables'],
                    packfh=st['pack_front_hits'],subfh=st['sub_front_hits'],
                    greedy=st['greedy_yes'],dff=st['dff_no']))
    print(i,res[-1],flush=True)
json.dump(res,open('v13/full.json','w'),indent=1)
print('totals',sum(r['nodes'] for r in res),round(sum(r['t'] for r in res),2),sum(r['tables'] for r in res))
