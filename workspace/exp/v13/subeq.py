import sys,pickle,time,json
sys.path.insert(0,'v13')
import po
d=pickle.load(open('v13/hard3.pkl','rb'))
res=[]
for i,(inst,opt,_) in enumerate(d):
    row={}
    for mode in ['sub','subeq']:
        t=time.time(); (ok,_),st=po.decide(inst,opt-1,mode=mode,nodecap=2_500_000); dt=time.time()-t
        row[mode]=dict(nodes=st['nodes'],t=round(dt,4),subfh=st['sub_front_hits'])
    res.append(row); print(i,row,flush=True)
json.dump(res,open('v13/subeq.json','w'),indent=1)
