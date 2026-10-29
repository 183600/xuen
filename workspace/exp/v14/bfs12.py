import sys, pickle, time, json
sys.path.insert(0,'exp/v14')
import bfs, sp
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
rows=[]; tot=[0,0.0]
for idx,(inst,opt,n0) in enumerate(d):
    t=time.time(); (ok,_),st=bfs.decide_bfs(inst,opt-1,nodecap=3_000_000); dt=time.time()-t
    tot[0]+=st['labels']; tot[1]+=dt
    print(idx,'n',inst['n'],'opt',opt,'ok',ok,'labels',st['labels'],'exp',st['expanded'],'packs',st['packs'],'pruned',st['pruned'],'t',round(dt,3),'maxfront',max(st['front_sizes']) if st['front_sizes'] else 0,flush=True)
    rows.append(dict(idx=idx,n=inst['n'],opt=opt,ok=ok,labels=st['labels'],expanded=st['expanded'],packs=st['packs'],pruned=st['pruned'],t=round(dt,4),front=st['front_sizes']))
    json.dump(rows,open('exp/v14/bfs12.json','w'),indent=1)
print('tot labels',tot[0],'time',round(tot[1],3))
print('v12 nodes 69690 time 1.184 -> label ratio',round(tot[0]/69690,3),'time ratio',round(tot[1]/1.184,3))
